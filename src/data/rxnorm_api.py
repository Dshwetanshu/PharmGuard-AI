"""RxNorm live-API fallback.

When a user types a drug name that isn't in the local vocabulary (which is
necessarily a small curated subset), this module queries the public RxNorm
API to resolve it. Same pattern as the FAERS fallback: opt-in via the
normalizer, in-memory caching, short timeouts, graceful failure.

API docs: https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html

Endpoints used:
  - /REST/rxcui.json?name=<drug>   → resolve free text to an RXCUI
  - /REST/rxcui/<RXCUI>/property.json?propName=RxNormName  → canonical ingredient

Design notes:
  - 4 s timeout per call (fast-fail)
  - In-memory cache keyed by lowercased query
  - Returns None on any error — caller falls back to "unresolved"
  - Only candidates that carry an RxNorm-sourced name and score at least
    ``min_score`` are accepted. The returned name (never the user's query) is
    what the normalizer maps back through the local vocabulary.

approximateTerm scores are unnormalised and do NOT separate good matches from
garbage on their own. Observed 2026-09-22: "coumadin" 13.6, "xanax" 13.6,
"warfarin" 12.1, "insulin" 10.9, "lisonopril" 8.0 — but
"definitely_not_a_drug_xyz" 10.5 and "fictional_drug_xyz" 8.4. The threshold
is a first filter; mapping the RxNorm name back to local data is the real guard.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus

try:
    import urllib.request as urllib_request
    from urllib.error import URLError, HTTPError
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False


RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"


@dataclass(frozen=True)
class RxNormMatch:
    rxcui: str
    name: str                  # RxNorm's name for the matched concept (lowercased)
    ingredient: Optional[str]  # ingredient (TTY=IN) name, if RxNorm returned one
    score: float               # raw approximateTerm score (unnormalised)


class RxNormApiResolver:
    """Resolves free-form drug names to an RxNorm concept via the RxNorm REST API."""

    def __init__(self, enabled: bool = True, timeout_s: float = 4.0, min_score: float = 10.0):
        self.enabled = enabled and _HAS_URLLIB
        self.timeout_s = timeout_s
        self.min_score = min_score
        self._cache: dict = {}   # query (lower) -> RxNormMatch or None

    def resolve(self, query: str) -> Optional[RxNormMatch]:
        """Return the best confident RxNorm match, or None."""
        if not self.enabled or not query:
            return None

        key = query.strip().lower()
        if key in self._cache:
            return self._cache[key]

        try:
            best = self._best_candidate(key)
            result = None
            if best is not None:
                rxcui, name, score = best
                result = RxNormMatch(rxcui, name, self._ingredient_for(rxcui), score)
            self._cache[key] = result
            return result
        except Exception:
            # Network failure, malformed response, etc. — never crash the pipeline
            self._cache[key] = None
            return None

    # ---------- HTTP helpers ----------

    def _fetch(self, url: str) -> dict:
        req = urllib_request.Request(url, headers={"User-Agent": "PharmGuard/1.0"})
        with urllib_request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _best_candidate(self, name: str) -> Optional[tuple]:
        """Return (rxcui, rxnorm_name, score) for the highest-scoring candidate that
        has an RxNorm-sourced name and clears min_score, else None.

        approximateTerm is the right endpoint for noisy input (misspellings,
        brand names), but it always returns *something*, so candidates are
        filtered rather than trusting the top hit.
        """
        url = (
            f"{RXNORM_BASE}/approximateTerm.json"
            f"?term={quote_plus(name)}&maxEntries=5"
        )
        payload = self._fetch(url)
        candidates = payload.get("approximateGroup", {}).get("candidate", []) or []
        best = None
        for c in candidates:
            rxcui, cname = c.get("rxcui"), (c.get("name") or "").strip()
            if c.get("source") != "RXNORM" or not rxcui or not cname:
                continue
            try:
                score = float(c.get("score"))
            except (TypeError, ValueError):
                continue
            if score >= self.min_score and (best is None or score > best[2]):
                best = (str(rxcui), cname.lower(), score)
        return best

    def _ingredient_for(self, rxcui: str) -> Optional[str]:
        """Resolve an RXCUI to its canonical ingredient (generic) name."""
        # 1. Ask for "IN" (ingredient) related concepts
        url = (
            f"{RXNORM_BASE}/rxcui/{rxcui}/related.json?tty=IN"
        )
        try:
            payload = self._fetch(url)
        except Exception:
            payload = {}

        groups = payload.get("relatedGroup", {}).get("conceptGroup", []) or []
        for group in groups:
            for concept in group.get("conceptProperties", []) or []:
                nm = concept.get("name")
                if nm:
                    return nm.lower().strip()

        # 2. Fall back to the concept's own name
        try:
            url = f"{RXNORM_BASE}/rxcui/{rxcui}/property.json?propName=RxNormName"
            payload = self._fetch(url)
            props = payload.get("propConceptGroup", {}).get("propConcept", []) or []
            if props:
                return str(props[0].get("propValue", "")).lower().strip() or None
        except Exception:
            pass

        return None
