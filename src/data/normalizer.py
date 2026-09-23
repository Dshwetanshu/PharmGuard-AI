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

        @staticmethod
        def extract(query, choices, scorer=None, score_cutoff=0, limit=5):
            scored = [(c, (scorer or _FuzzShim.WRatio)(query, c), i) for i, c in enumerate(choices)]
            scored = [x for x in scored if x[1] >= score_cutoff]
            return sorted(scored, key=lambda x: -x[1])[:limit]

    fuzz = _FuzzShim()
    process = _ProcessShim()

from src.config import Config, config as default_config

# A fuzzy match is accepted only if the next *different* drug scores at least this
# much lower (WRatio points). Real misspellings clear it easily (metfromin -> metformin
# leads the next drug by 11); "insulin" (inulin 92 vs insulin products 90) doesn't.
FUZZY_AMBIGUITY_MARGIN = 5.0


@dataclass
class ResolvedDrug:
    query: str                    # original user input
    generic_name: Optional[str]   # canonical generic name
    rxcui: Optional[str]          # RxNorm concept unique identifier
    drugbank_id: Optional[str]    # DrugBank ID if available
    confidence: float             # 0-100 for local matches; raw RxNorm score for "rxnorm_api"
    resolved: bool                # True if confidence ≥ threshold
    method: str                   # "exact" | "fuzzy" | "rxnorm_api" | "rxnorm_not_in_local_vocab" |
                                  # "combination_product" | "unresolved"
    note: Optional[str] = None    # shown with an unresolved input, e.g. a combination's ingredients


class DrugNormalizer:
    """Resolves free-form drug names to canonical identifiers.

    Resolution order:
      1. Exact match against the local vocabulary
      2. Fuzzy match against the local vocabulary (rapidfuzz / difflib)
      3. RxNorm REST API fallback (when enabled): a confident RxNorm match is
         accepted only if the name RxNorm returns (ingredient first, then the
         concept name) maps back to an entry in the local vocabulary. A drug
         RxNorm knows but the local data doesn't is still unresolved, because
         there is nothing to retrieve for it.
      4. "unresolved"
    """

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or default_config
        # name -> (generic_name, rxcui, drugbank_id)
        self._lookup: Dict[str, tuple] = {}
        self._all_names: List[str] = []
        self._combinations: Dict[str, str] = {}   # combination product name -> "a + b"
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
        combos_path = self.cfg.paths.processed_dir / "combination_products.parquet"
        combos = read_table(combos_path) if table_exists(combos_path) else None
        return self.load_from_dataframe(df, combos)

    def load_from_dataframe(self, df: pd.DataFrame, combinations: Optional[pd.DataFrame] = None) -> "DrugNormalizer":
        """Load directly from in-memory dataframes (tests, sample mode)."""
        self._build_lookup(df)
        if combinations is not None:
            self._combinations = dict(zip(combinations["name_lower"], combinations["ingredients"]))
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
            self._api_resolver = RxNormApiResolver(
                enabled=True, min_score=self.cfg.retrieval.min_confidence
            )
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

        # Combination products stay unresolved: name the ingredients instead of picking one.
        if q in self._combinations:
            return ResolvedDrug(query, None, None, None, 0.0, False, "combination_product",
                                note=f"combination product: {self._combinations[q]}; enter them separately")

        # 2. Fuzzy match against local vocabulary. If a *different* drug scores within
        # FUZZY_AMBIGUITY_MARGIN of the best, don't guess: with the real vocabulary,
        # "insulin" scored 92 for inulin and 90 for several insulins.
        hits = process.extract(q, self._all_names, scorer=fuzz.WRatio,
                               score_cutoff=self.cfg.retrieval.name_match_threshold, limit=10)
        best_by_generic: Dict[str, float] = {}
        for name, score, _ in hits:
            generic = self._lookup[name][0]
            best_by_generic[generic] = max(best_by_generic.get(generic, 0.0), float(score))
        ranked = sorted(best_by_generic.items(), key=lambda x: -x[1])
        if len(ranked) >= 2 and ranked[0][1] - ranked[1][1] < FUZZY_AMBIGUITY_MARGIN:
            names = " / ".join(g for g, _ in ranked[:4])   # RxNorm names can contain commas
            return ResolvedDrug(query, None, None, None, ranked[0][1], False, "fuzzy_ambiguous",
                                note=f"ambiguous name; closest matches: {names}; enter the specific drug")
        if ranked:
            generic = ranked[0][0]
            name = next(n for n, _, _ in hits if self._lookup[n][0] == generic)
            _, rxcui, dbid = self._lookup[name]
            return ResolvedDrug(query, generic, rxcui, dbid, ranked[0][1], True, "fuzzy")

        # 3. RxNorm REST API fallback, mapped back through the local vocabulary
        api = self._ensure_api_resolver()
        if api is not None:
            match = api.resolve(q)
            if match:
                for name in (match.ingredient, match.name):
                    if name and name in self._lookup:
                        generic, rxcui, dbid = self._lookup[name]
                        return ResolvedDrug(query, generic, rxcui, dbid, match.score, True, "rxnorm_api")
                return ResolvedDrug(
                    query, None, match.rxcui, None, match.score, False, "rxnorm_not_in_local_vocab"
                )

        return ResolvedDrug(query, None, None, None, 0.0, False, "unresolved")

    def aliases_for(self, generics) -> Dict[str, str]:
        """{alias: generic} for every local-vocabulary alias of the given generics."""
        wanted = {str(g).lower() for g in generics if g}
        return {alias: str(v[0]).lower() for alias, v in self._lookup.items()
                if v[0] is not None and str(v[0]).lower() in wanted}

    def resolve_many(self, queries: List[str]) -> List[ResolvedDrug]:
        return [self.resolve(q) for q in queries]
