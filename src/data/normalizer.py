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

# Spelling matches use plain Levenshtein similarity (rapidfuzz ratio, 0-100), not WRatio:
# WRatio's partial matching scored "spironolacton" 90 against "iron". Rules, measured on
# look-alike pairs and ordinary misspellings against the public build (see docs/DATASETS.md):
# - accept the best drug only if it scores >= the configured threshold (85) AND no other drug
#   scores within FUZZY_AMBIGUITY_MARGIN of it (rivals below FUZZY_NEIGHBOUR_FLOOR don't count);
# - two different drugs both >= FUZZY_NEIGHBOUR_FLOOR within the margin -> ambiguous
#   (Celebyx: Cerebyx 86 vs Celebrex 80; hydroxalazine: hydralazine 92 vs hydroxyzine 83);
# - an input that is the first word of two or more drugs' names -> ambiguous, listing those
#   drugs ("insulin" -> insulin aspart / insulin degludec / ...), never the closest spelling.
FUZZY_AMBIGUITY_MARGIN = 10.0
FUZZY_NEIGHBOUR_FLOOR = 75.0

UNRESOLVED_NOTE = ("not found: check the spelling or enter the generic name; discontinued brands and "
                   "non-US names may not be recognized")
NOT_IN_DATA_NOTE = "RxNorm knows this name, but the loaded data has no entry for it"


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
    alias_kind: Optional[str] = None   # how an exact/fuzzy match was found: the vocabulary entry's kind
                                       # (e.g. RXNORM:BN, DRUGSATFDA:BRAND, RXNORM:PIN); None if unknown
    matched_name: Optional[str] = None  # the vocabulary name a fuzzy match landed on


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
        self._fuzzy_names: List[str] = []           # fuzzy candidates (see set_fuzzy_targets)
        self._kind: Dict[str, Optional[str]] = {}
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
        self.load_from_dataframe(df, combos)
        # Fuzzy matching may only land on drugs the loaded data has records for, so an
        # obscure vocabulary substance (coumarin, inulin) can't capture a misspelling.
        targets = set()
        for table, cols in (("interactions.parquet", ["drug_a_name", "drug_b_name"]),
                            ("side_effects.parquet", ["drug_name"])):
            tp = self.cfg.paths.processed_dir / table
            if table_exists(tp):
                t = read_table(tp)
                for col in cols:
                    if col in t.columns:
                        targets |= {str(x).strip().lower() for x in t[col].dropna().unique()}
        if targets:
            self.set_fuzzy_targets(targets)
        return self

    def load_from_dataframe(self, df: pd.DataFrame, combinations: Optional[pd.DataFrame] = None) -> "DrugNormalizer":
        """Load directly from in-memory dataframes (tests, sample mode)."""
        self._build_lookup(df)
        if combinations is not None:
            self._combinations = dict(zip(combinations["name_lower"], combinations["ingredients"]))
        self._loaded = True
        return self

    def set_fuzzy_targets(self, generics) -> "DrugNormalizer":
        """Restrict fuzzy matching to names whose canonical drug is in `generics`.
        Exact and alias matching still use the whole vocabulary."""
        wanted = {str(g).strip().lower() for g in generics if g}
        self._fuzzy_names = [n for n in self._all_names if str(self._lookup[n][0]).strip().lower() in wanted]
        return self

    def _family(self, q: str) -> List[str]:
        """Drugs whose names start with the whole word q ("insulin" -> "insulin aspart, ...")."""
        if len(q) < 4 or " " in q:
            return []
        found: Dict[str, int] = {}
        for name in self._fuzzy_names:
            if name.startswith(q) and len(name) > len(q) and not name[len(q)].isalnum():
                g = str(self._lookup[name][0])
                found[g] = min(found.get(g, 10 ** 6), len(name))
        return sorted(found, key=lambda g: (found[g], g))

    def _build_lookup(self, df: pd.DataFrame) -> None:
        self._lookup = {}
        self._kind = {}
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
            kind = row.get("kind")
            self._kind[key] = kind if isinstance(kind, str) and kind else None
            names.append(key)
        self._all_names = sorted(set(names))
        self._fuzzy_names = list(self._all_names)

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
            return ResolvedDrug(query, None, None, None, 0.0, False, "unresolved", note="empty input")

        # 1. Exact match against local vocabulary
        if q in self._lookup:
            generic, rxcui, dbid = self._lookup[q]
            return ResolvedDrug(query, generic, rxcui, dbid, 100.0, True, "exact", alias_kind=self._kind.get(q))

        # Combination products stay unresolved: name the ingredients instead of picking one.
        if q in self._combinations:
            return ResolvedDrug(query, None, None, None, 0.0, False, "combination_product",
                                note=f"combination product: {self._combinations[q]}; enter them separately")

        # 2a. A family word ("insulin"): the first word of two or more drugs' names.
        family = self._family(q)
        if len(family) >= 2:
            names = " / ".join(family[:4])     # RxNorm names can contain commas
            more = f" (and {len(family) - 4} more)" if len(family) > 4 else ""
            return ResolvedDrug(query, None, None, None, 0.0, False, "fuzzy_ambiguous",
                                note=f"ambiguous name; matching drugs: {names}{more}; enter the specific drug")

        # 2b. Spelling match against drugs the loaded data has records for.
        threshold = self.cfg.retrieval.name_match_threshold
        hits = process.extract(q, self._fuzzy_names, scorer=fuzz.ratio,
                               score_cutoff=min(threshold, FUZZY_NEIGHBOUR_FLOOR), limit=100)
        best_by_generic: Dict[str, float] = {}
        best_name: Dict[str, str] = {}
        for name, score, _ in hits:
            generic = self._lookup[name][0]
            if float(score) > best_by_generic.get(generic, -1.0):
                best_by_generic[generic], best_name[generic] = float(score), name
        ranked = sorted(best_by_generic.items(), key=lambda x: (-x[1], str(x[0])))
        best = ranked[0][1] if ranked else 0.0
        rival = ranked[1][1] if len(ranked) > 1 else 0.0
        close_rival = rival >= FUZZY_NEIGHBOUR_FLOOR and best - rival < FUZZY_AMBIGUITY_MARGIN
        if best >= threshold and not close_rival:
            generic = ranked[0][0]
            name = max((n for n, _, _ in hits if self._lookup[n][0] == generic),
                       key=lambda n: fuzz.ratio(q, n))
            _, rxcui, dbid = self._lookup[name]
            return ResolvedDrug(query, generic, rxcui, dbid, best, True, "fuzzy",
                                alias_kind=self._kind.get(name), matched_name=name)
        if close_rival and best >= FUZZY_NEIGHBOUR_FLOOR:
            # Name the alias that matched when it isn't the drug's own name, so the user can
            # see why a candidate is listed ("bevacizumab (matched avastin)").
            names = " / ".join(g if best_name[g] == str(g).lower() else f"{g} (matched {best_name[g]})"
                               for g, sc in ranked[:4] if best - sc < FUZZY_AMBIGUITY_MARGIN)
            return ResolvedDrug(query, None, None, None, best, False, "fuzzy_ambiguous",
                                note=f"ambiguous name; closest matches: {names}; enter the specific drug")

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
                    query, None, match.rxcui, None, match.score, False, "rxnorm_not_in_local_vocab",
                    note=NOT_IN_DATA_NOTE,
                )

        return ResolvedDrug(query, None, None, None, 0.0, False, "unresolved", note=UNRESOLVED_NOTE)

    def aliases_for(self, generics) -> Dict[str, str]:
        """{alias: generic} for every local-vocabulary alias of the given generics."""
        wanted = {str(g).lower() for g in generics if g}
        return {alias: str(v[0]).lower() for alias, v in self._lookup.items()
                if v[0] is not None and str(v[0]).lower() in wanted}

    def resolve_many(self, queries: List[str]) -> List[ResolvedDrug]:
        return [self.resolve(q) for q in queries]
