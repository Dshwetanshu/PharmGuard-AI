"""Drug-name normalization.

Accepts free-form user input (brand names, generic names, misspellings, different
capitalizations) and resolves each to a canonical (generic_name, rxcui) pair.

Strategy:
  1. Exact match against the RxNorm concept table (generic + brand names)
  2. Exact match against DrugBank synonyms
  3. Fuzzy match (rapidfuzz) against the union, gated by a confidence threshold

Failed resolutions are reported explicitly rather than silently dropped —
per the proposal's "honest uncertainty" principle.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

try:
    from rapidfuzz import process, fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    # Stdlib fallback — slower, no C extension, but works anywhere.
    from difflib import SequenceMatcher

    _HAS_RAPIDFUZZ = False

    class _FuzzShim:
        @staticmethod
        def WRatio(a: str, b: str) -> float:
            return SequenceMatcher(None, a, b).ratio() * 100.0

    class _ProcessShim:
        @staticmethod
        def extractOne(query, choices, scorer=None, score_cutoff=0):
            best = None
            best_score = -1.0
            for c in choices:
                s = (scorer or _FuzzShim.WRatio)(query, c)
                if s > best_score:
                    best_score = s
                    best = c
            if best is None or best_score < score_cutoff:
                return None
            return (best, best_score, 0)

    fuzz = _FuzzShim()
    process = _ProcessShim()

from src.config import Config, config as default_config


@dataclass
class ResolvedDrug:
    query: str                    # original user input
    generic_name: Optional[str]   # canonical generic name
    rxcui: Optional[str]          # RxNorm concept unique identifier
    drugbank_id: Optional[str]    # DrugBank ID if available
    confidence: float             # 0-100
    resolved: bool                # True if confidence ≥ threshold
    method: str                   # "exact" | "synonym" | "fuzzy" | "unresolved"


class DrugNormalizer:
    """Resolves free-form drug names to canonical identifiers.

    Resolution order:
      1. Exact match against the local vocabulary
      2. Fuzzy match against the local vocabulary (rapidfuzz / difflib)
      3. RxNorm REST API fallback (when enabled) — handles ANY drug known to
         the National Library of Medicine, including misspellings and brand names
      4. "unresolved"
    """

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or default_config
        # name -> (generic_name, rxcui, drugbank_id)
        self._lookup: Dict[str, tuple] = {}
        self._all_names: List[str] = []
        self._loaded = False
        self._api_resolver = None  # lazy — only built if enabled

    # ---------- loading ----------

    def load(self) -> "DrugNormalizer":
        """Load normalization tables from processed directory.

        Expects a processed 'drug_vocabulary.parquet' (or .csv fallback) file with columns:
          name_lower, generic_name, rxcui, drugbank_id, source
        """
        from src.data.storage import read_table, table_exists
        path = self.cfg.paths.processed_dir / "drug_vocabulary.parquet"
        if not table_exists(path):
            raise FileNotFoundError(
                f"Drug vocabulary not found at {path} (or .csv). "
                "Run `python scripts/ingest_data.py` first."
            )
        df = read_table(path)
        self._build_lookup(df)
        self._loaded = True
        return self

    def load_from_dataframe(self, df: pd.DataFrame) -> "DrugNormalizer":
        """Load directly from an in-memory dataframe (used in tests/sample mode)."""
        self._build_lookup(df)
        self._loaded = True
        return self

    def _build_lookup(self, df: pd.DataFrame) -> None:
        self._lookup = {}
        names = []
        for _, row in df.iterrows():
            key = str(row["name_lower"]).strip()
            if not key:
                continue
            self._lookup[key] = (
                row.get("generic_name"),
                row.get("rxcui"),
                row.get("drugbank_id"),
            )
            names.append(key)
        self._all_names = list(set(names))

    # ---------- resolution ----------

    def _ensure_api_resolver(self):
        """Lazily instantiate the RxNorm API resolver if enabled in config."""
        if self._api_resolver is None and self.cfg.retrieval.rxnorm_api_enabled:
            from src.data.rxnorm_api import RxNormApiResolver
            self._api_resolver = RxNormApiResolver(enabled=True)
        return self._api_resolver

    def resolve(self, query: str) -> ResolvedDrug:
        if not self._loaded:
            raise RuntimeError("DrugNormalizer.load() must be called first.")

        q = query.strip().lower()
        if not q:
            return ResolvedDrug(query, None, None, None, 0.0, False, "unresolved")

        # 1. Exact match against local vocabulary
        if q in self._lookup:
            generic, rxcui, dbid = self._lookup[q]
            return ResolvedDrug(query, generic, rxcui, dbid, 100.0, True, "exact")

        # 2. Fuzzy match against local vocabulary
        match = process.extractOne(
            q, self._all_names, scorer=fuzz.WRatio, score_cutoff=self.cfg.retrieval.name_match_threshold
        )
        if match:
            name, score, _ = match
            generic, rxcui, dbid = self._lookup[name]
            return ResolvedDrug(query, generic, rxcui, dbid, float(score), True, "fuzzy")

        # 3. RxNorm REST API fallback — opens the system up to ANY FDA-approved drug
        api = self._ensure_api_resolver()
        if api is not None:
            hit = api.resolve(q)
            if hit:
                generic, rxcui = hit
                # Opportunistically cache so repeat queries in the same session are instant
                self._lookup[q] = (generic, rxcui, None)
                if q not in self._all_names:
                    self._all_names.append(q)
                return ResolvedDrug(query, generic, rxcui, None, 90.0, True, "rxnorm_api")

        return ResolvedDrug(query, None, None, None, 0.0, False, "unresolved")

    def resolve_many(self, queries: List[str]) -> List[ResolvedDrug]:
        return [self.resolve(q) for q in queries]
