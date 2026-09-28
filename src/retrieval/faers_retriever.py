"""OpenFDA FAERS live-query fallback, with disproportionality statistics.

For drug pairs with no curated record, this retriever queries the FDA Adverse
Event Reporting System (FAERS) through openFDA, takes the events most often
co-reported with both drugs, and computes PRR, ROR (95% CI) and a Yates
chi-square for each (src/retrieval/faers_stats.py). Only signals that meet the
Evans criteria, have an ROR lower bound above 1, and aren't explained by either
drug alone are surfaced; the others are counted as suppressed.

Design notes:
  - Requires network access (opt-in; disabled by default).
  - openFDA limits (open.fda.gov/apis/authentication, checked 2026-09-22): 240
    requests/minute and 1,000/day per IP without a key. Calls are spaced at
    least 0.3 s apart; a pair costs about 5 + 3 x max_events calls, fewer with
    the cache.
  - Counts come from meta.results.total with limit=1; a 404 means zero reports.
    "A without B" is n(A) - n(A and B), never a NOT query.
  - Responses can be cached on disk (cache_dir), keyed by URL.
  - A 429 or 5xx is retried up to twice (openFDA's count queries sometimes return a
    transient 500), after 1 s and 2 s, or after Retry-After if that is shorter than 5 s.
  - Administrative MedDRA terms ("drug ineffective", "drug interaction", ...) are
    skipped, as for TWOSIDES.
  - Errors are swallowed: FAERS is a nice-to-have, not a correctness requirement.

API docs: https://open.fda.gov/apis/drug/event/
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode

try:
    import urllib.request as urllib_request
    from urllib.error import URLError, HTTPError
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False

from src.data.loaders import TWOSIDES_ADMIN_TERMS as ADMIN_TERMS
from src.retrieval.faers_stats import PairEventCounts, SignalStats, Thresholds, assess

FAERS_ENDPOINT = "https://api.fda.gov/drug/event.json"


@dataclass
class FaersRecord:
    record_id: str
    drug_a: str
    drug_b: str
    condition: str      # the co-reported event (MedDRA preferred term)
    report_count: int   # reports listing both drugs and the event (a)
    severity: str = "not graded"   # FAERS signals are never graded for clinical severity
    source: str = "FAERS"
    source_url: str = ""
    prr: Optional[float] = None
    ror: Optional[float] = None
    ror_ci_low: Optional[float] = None
    ror_ci_high: Optional[float] = None
    chi2: Optional[float] = None

    def citation(self) -> str:
        return f"[{self.source}:{self.record_id}]"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FaersAssessment:
    """What one pair's FAERS lookup found: surfaced signals and the suppressed ones."""
    pair: Tuple[str, str]
    surfaced: List[FaersRecord] = field(default_factory=list)
    suppressed: List[SignalStats] = field(default_factory=list)
    checked_events: int = 0
    assessed: List[SignalStats] = field(default_factory=list)   # every checked event, surfaced or not
    error: Optional[str] = None


def drug_clause(name: str) -> str:
    return 'patient.drug.medicinalproduct:"' + name.replace('"', "") + '"'


def event_clause(term: str) -> str:
    return 'patient.reaction.reactionmeddrapt.exact:"' + term.replace('"', "") + '"'


_MISS = object()


class _Lru(OrderedDict):
    """A dict that keeps only its newest max_items entries (bounded memory in a long-running server)."""

    def __init__(self, max_items: int):
        super().__init__()
        self.max_items = max_items

    def put(self, key, value):
        self[key] = value
        self.move_to_end(key)
        while len(self) > self.max_items:
            self.popitem(last=False)


class OpenFdaCounts:
    """Report counts from openFDA's drug/event endpoint, throttled and optionally cached on disk.

    fetch(url) -> parsed JSON payload, or None for a 404 (no matching reports).
    deadline() -> a time.monotonic() deadline or None; past it, no further call is made
    (TimeoutError), so a request's FAERS budget holds per call, not just per pair.
    """

    def __init__(self, fetch: Optional[Callable[[str], Optional[dict]]] = None, cache_dir: Optional[Path] = None,
                 min_interval: float = 0.3, timeout_s: float = 6.0, retries: int = 2,
                 sleep: Callable[[float], None] = time.sleep,
                 deadline: Optional[Callable[[], Optional[float]]] = None, max_items: int = 5_000):
        self._fetch = fetch or self._urlopen
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.min_interval, self.timeout_s = min_interval, timeout_s
        self.retries, self._sleep = retries, sleep
        self.deadline = deadline or (lambda: None)
        self._mem = _Lru(max_items)
        self._lock = threading.Lock()
        self._last = 0.0
        self.network_calls = 0

    @staticmethod
    def url(search: Optional[str] = None, count: Optional[str] = None, limit: Optional[int] = None) -> str:
        params = {}
        if search:
            params["search"] = search
        if count:
            params["count"] = count
        if limit is not None:
            params["limit"] = str(limit)
        return f"{FAERS_ENDPOINT}?{urlencode(params)}"

    def total(self, *clauses: str) -> int:
        """Number of reports matching every clause (all reports if none)."""
        payload = self.get(self.url(" AND ".join(clauses) or None, limit=1))
        return int(((payload or {}).get("meta") or {}).get("results", {}).get("total", 0)) if payload else 0

    def top_events(self, *clauses: str, limit: int = 10) -> List[Tuple[str, int]]:
        payload = self.get(self.url(" AND ".join(clauses), count="patient.reaction.reactionmeddrapt.exact",
                                    limit=limit))
        return [(r.get("term", ""), int(r.get("count", 0))) for r in (payload or {}).get("results") or []]

    def get(self, url: str) -> Optional[dict]:
        hit = self._mem.get(url, _MISS)
        if hit is not _MISS:
            return hit
        path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".json") if self.cache_dir else None
        if path is not None and path.exists():
            payload = json.loads(path.read_text())["payload"]
        else:
            with self._lock:     # the API shares one client between threads
                wait = self.min_interval - (time.monotonic() - self._last)
                self._last = time.monotonic() + max(wait, 0)
                self.network_calls += 1
            self._check_deadline(max(wait, 0))
            if wait > 0:
                self._sleep(wait)
            payload = self._fetch(url)
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"url": url, "payload": payload}))
        self._mem.put(url, payload)
        return payload

    def _check_deadline(self, extra: float = 0.0) -> None:
        d = self.deadline()
        if d is not None and time.monotonic() + extra >= d:
            raise TimeoutError("FAERS time budget used up")

    def _urlopen(self, url: str) -> Optional[dict]:
        from src.observability import active
        req = urllib_request.Request(url, headers={"User-Agent": "PharmGuard/1.0"})
        for attempt in range(self.retries + 1):
            with active().http("faers.http", url) as record:   # child span; query hidden when redacting
                try:
                    with urllib_request.urlopen(req, timeout=self.timeout_s) as resp:
                        record({"http.response.status_code": getattr(resp, "status", 200)})
                        return json.loads(resp.read().decode("utf-8"))
                except HTTPError as e:
                    record({"http.response.status_code": e.code})
                    if e.code == 404:     # openFDA: no matching reports
                        return None
                    if attempt == self.retries or not (e.code == 429 or e.code >= 500):
                        raise
                    wait = float(2 ** attempt)
                    retry_after = (e.headers or {}).get("Retry-After") if hasattr(e, "headers") else None
                    if retry_after and str(retry_after).isdigit() and int(retry_after) < 5:
                        wait = float(retry_after)
            self._check_deadline(wait)
            self._sleep(wait)
        raise RuntimeError("unreachable")


class FaersRetriever:
    """Queries openFDA FAERS for co-reported events on drug pairs and keeps only statistical signals."""

    def __init__(self, enabled: bool = False, timeout_s: float = 6.0, max_events: int = 3,
                 thresholds: Thresholds = Thresholds(), counts: Optional[OpenFdaCounts] = None,
                 cache_dir: Optional[Path] = None):
        self.enabled = enabled and _HAS_URLLIB
        self.timeout_s = timeout_s
        self.max_events = max_events
        self.thresholds = thresholds
        self.counts = counts or OpenFdaCounts(cache_dir=cache_dir, timeout_s=timeout_s)
        self._cache = _Lru(2_000)

    # ---------- public API ----------

    def retrieve_pair(self, drug_a: str, drug_b: str) -> List[FaersRecord]:
        return self.assess_pair(drug_a, drug_b).surfaced

    def assess_pair(self, drug_a: str, drug_b: str) -> FaersAssessment:
        a = (drug_a or "").strip().lower()
        b = (drug_b or "").strip().lower()
        key = tuple(sorted([a, b]))
        if not self.enabled or not a or not b:
            return FaersAssessment(key)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        try:
            found = self._assess(key)
        except Exception as e:     # best effort: never crash the pipeline on network failure
            return FaersAssessment(key, error=type(e).__name__)     # not cached: a later request may succeed
        self._cache.put(key, found)
        return found

    # ---------- internals ----------

    def _assess(self, key: Tuple[str, str]) -> FaersAssessment:
        a, b = key
        ca, cb = drug_clause(a), drug_clause(b)
        out = FaersAssessment(key)
        top = [(t, n) for t, n in self.counts.top_events(ca, cb, limit=self.max_events + len(ADMIN_TERMS))
               if t.lower() not in ADMIN_TERMS][: self.max_events]
        if not top:
            return out
        total, n_a, n_b, n_ab = self.counts.total(), self.counts.total(ca), self.counts.total(cb), self.counts.total(ca, cb)
        for term, n_abe in top[: self.max_events]:
            ce = event_clause(term)
            c = PairEventCounts(total=total, n_a=n_a, n_b=n_b, n_ab=n_ab, n_e=self.counts.total(ce),
                                n_ae=self.counts.total(ca, ce), n_be=self.counts.total(cb, ce), n_abe=n_abe)
            s = assess(term.lower(), c, self.thresholds, names=key)
            out.checked_events += 1
            out.assessed.append(s)
            if not s.surfaced:
                out.suppressed.append(s)
                continue
            digest = hashlib.sha1(f"{a}|{b}|{term.lower()}".encode()).hexdigest()[:10]
            out.surfaced.append(FaersRecord(
                record_id=f"FAERS-{digest}", drug_a=a, drug_b=b, condition=term.lower(), report_count=s.a,
                source_url=self._public_query_url(a, b), prr=s.prr, ror=s.ror, ror_ci_low=s.ror_ci_low,
                ror_ci_high=s.ror_ci_high, chi2=s.chi2))
        return out

    def _query_faers(self, drug_a: str, drug_b: str) -> List[tuple]:
        """[(reaction_name, report_count), ...] for reports listing both drugs, by count."""
        payload = self.counts._fetch(self._query_url(drug_a, drug_b, limit=10))
        return [(r.get("term", "").lower(), int(r.get("count", 0))) for r in (payload or {}).get("results") or []]

    @staticmethod
    def _query_url(drug_a: str, drug_b: str, limit: Optional[int] = None) -> str:
        """Build the openFDA count query. Every parameter value is URL-encoded, and
        double quotes are removed from names so they cannot end the phrase."""
        return OpenFdaCounts.url(f"{drug_clause(drug_a)} AND {drug_clause(drug_b)}",
                                 count="patient.reaction.reactionmeddrapt.exact", limit=limit)

    @classmethod
    def _public_query_url(cls, drug_a: str, drug_b: str) -> str:
        """Return a URL a clinician can paste into a browser to reproduce the query."""
        return cls._query_url(drug_a, drug_b)
