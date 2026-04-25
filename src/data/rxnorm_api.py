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
"""
from __future__ import annotations

import json
from typing import Optional, Tuple
from urllib.parse import quote_plus

try:
    import urllib.request as urllib_request
    from urllib.error import URLError, HTTPError
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False


RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"


class RxNormApiResolver:
    """Resolves free-form drug names to (generic_name, rxcui) via RxNorm REST API."""

    def __init__(self, enabled: bool = True, timeout_s: float = 4.0):
        self.enabled = enabled and _HAS_URLLIB
        self.timeout_s = timeout_s
        self._cache: dict = {}   # query (lower) -> (generic_name, rxcui) or None

    def resolve(self, query: str) -> Optional[Tuple[str, str]]:
        """Return (generic_name, rxcui) or None if not resolvable."""
        if not self.enabled or not query:
            return None

        key = query.strip().lower()
        if key in self._cache:
            return self._cache[key]

        try:
            rxcui = self._approximate_rxcui(key)
            if not rxcui:
                self._cache[key] = None
                return None

            # Prefer the ingredient (generic) form for the resolved RXCUI
            ingredient = self._ingredient_for(rxcui)
            name = (ingredient or key).lower()
            result = (name, str(rxcui))
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

    def _approximate_rxcui(self, name: str) -> Optional[str]:
        """Resolve free text → RXCUI using RxNorm's approximate match endpoint.

        This is the right endpoint for noisy user input: it handles
        misspellings, brand names, and variant forms.
        """
        url = (
            f"{RXNORM_BASE}/approximateTerm.json"
            f"?term={quote_plus(name)}&maxEntries=1"
        )
        payload = self._fetch(url)
        candidates = (
            payload.get("approximateGroup", {}).get("candidate", [])
        )
        if not candidates:
            return None
        top = candidates[0]
        rxcui = top.get("rxcui")
        # RxNorm returns strings; coerce to str just in case
        return str(rxcui) if rxcui else None

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
