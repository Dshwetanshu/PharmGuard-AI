"""OpenFDA FAERS live-query fallback.

For drug pairs not found in the local TWOSIDES/DDInter indexes, this retriever
queries the FDA Adverse Event Reporting System (FAERS) via OpenFDA's public
API. This directly addresses the proposal's stretch goal of surfacing FDA
adverse-event signals that predate official labeling.

Design notes:
  - Requires network access (opt-in; disabled by default)
  - Respects OpenFDA's unauthenticated rate limit (1000 req/day, 40 req/min)
  - Each returned record gets a FAERS-<hash> record_id that cites back to the
    OpenFDA query URL so clinicians can verify
  - Timeouts are short and errors are swallowed — FAERS is a nice-to-have, not
    a correctness requirement

API docs: https://open.fda.gov/apis/drug/event/
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import List, Optional
from urllib.parse import quote_plus

try:
    import urllib.request as urllib_request
    from urllib.error import URLError, HTTPError
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False


FAERS_ENDPOINT = "https://api.fda.gov/drug/event.json"


@dataclass
class FaersRecord:
    record_id: str
    drug_a: str
    drug_b: str
    condition: str      # most-reported reaction
    report_count: int   # number of FAERS reports mentioning both drugs
    severity: str       # heuristic tier based on report count
    source: str = "FAERS"
    source_url: str = ""

    def citation(self) -> str:
        return f"[{self.source}:{self.record_id}]"

    def to_dict(self) -> dict:
        return asdict(self)


class FaersRetriever:
    """Queries OpenFDA FAERS for co-reported adverse events on drug pairs."""

    def __init__(self, enabled: bool = False, timeout_s: float = 6.0,
                 min_reports: int = 3, max_reactions: int = 3):
        self.enabled = enabled and _HAS_URLLIB
        self.timeout_s = timeout_s
        self.min_reports = min_reports
        self.max_reactions = max_reactions
        # Simple in-memory cache so repeated queries in one session are free
        self._cache: dict = {}
        # Rate-limit tracking (rudimentary; resets on process restart)
        self._last_call_ts = 0.0
        self._min_interval = 1.5   # seconds between calls — stays well under 40/min

    # ---------- public API ----------

    def retrieve_pair(self, drug_a: str, drug_b: str) -> List[FaersRecord]:
        if not self.enabled:
            return []

        a = (drug_a or "").strip().lower()
        b = (drug_b or "").strip().lower()
        if not a or not b:
            return []

        key = tuple(sorted([a, b]))
        if key in self._cache:
            return self._cache[key]

        try:
            self._throttle()
            reactions = self._query_faers(key[0], key[1])
        except Exception:
            # FAERS is best-effort — never crash the pipeline on network failure
            self._cache[key] = []
            return []

        if not reactions:
            self._cache[key] = []
            return []

        records = []
        for reaction_name, count in reactions[: self.max_reactions]:
            if count < self.min_reports:
                continue
            digest = hashlib.sha1(
                f"{key[0]}|{key[1]}|{reaction_name}".encode()
            ).hexdigest()[:10]
            records.append(FaersRecord(
                record_id=f"FAERS-{digest}",
                drug_a=key[0],
                drug_b=key[1],
                condition=reaction_name,
                report_count=int(count),
                severity=self._count_to_severity(count),
                source_url=self._public_query_url(key[0], key[1]),
            ))

        self._cache[key] = records
        return records

    # ---------- internals ----------

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_call_ts
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_ts = time.time()

    def _query_faers(self, drug_a: str, drug_b: str) -> List[tuple]:
        """Return [(reaction_name, report_count), ...] sorted desc by count."""
        # Search for reports mentioning BOTH drugs, count by reaction term.
        search = (
            f'(patient.drug.medicinalproduct:"{drug_a}"+AND+'
            f'patient.drug.medicinalproduct:"{drug_b}")'
        )
        url = (
            f"{FAERS_ENDPOINT}?search={search}"
            f"&count=patient.reaction.reactionmeddrapt.exact&limit=10"
        )

        req = urllib_request.Request(url, headers={"User-Agent": "PharmGuard/1.0"})
        try:
            with urllib_request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            # 404 from OpenFDA just means "no matching reports" — not an error
            if e.code == 404:
                return []
            raise

        results = payload.get("results") or []
        return [(r.get("term", "").lower(), int(r.get("count", 0))) for r in results]

    @staticmethod
    def _public_query_url(drug_a: str, drug_b: str) -> str:
        """Return a URL a clinician can paste into a browser to reproduce the query."""
        search = (
            f'(patient.drug.medicinalproduct:"{drug_a}"+AND+'
            f'patient.drug.medicinalproduct:"{drug_b}")'
        )
        return f"{FAERS_ENDPOINT}?search={search}&count=patient.reaction.reactionmeddrapt.exact"

    @staticmethod
    def _count_to_severity(count: int) -> str:
        """Map FAERS report counts to the project's severity vocabulary.

        These thresholds are deliberately conservative — FAERS counts are raw
        reports, not rate-adjusted. A high count is a loud signal; a low count
        is not necessarily a quiet one.
        """
        if count >= 500:
            return "Major"
        if count >= 100:
            return "Moderate"
        return "Minor"
