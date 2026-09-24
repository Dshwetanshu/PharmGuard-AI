"""Interaction retrieval.

Structured (non-vector) retrieval against the processed TWOSIDES table.
Drug-drug interactions are a case where structured lookup strictly dominates
semantic search: we want the record for exactly this pair, not the record
for a similar pair.

Vector search is reserved for unstructured context (patient reviews, mechanism
descriptions) — handled elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.config import Config, config as default_config


@dataclass
class InteractionRecord:
    record_id: str
    drug_a: str
    drug_b: str
    drug_a_rxcui: Optional[str]
    drug_b_rxcui: Optional[str]
    condition: str
    severity: str
    prr: Optional[float]
    frequency: Optional[float]
    source: str
    mechanism: Optional[str] = None   # source-provided mechanism prose (DDInter), if any
    reports: Optional[int] = None     # co-report count (TWOSIDES "A"), if the source has one

    @property
    def is_statistical(self) -> bool:
        """A disproportionality signal (TWOSIDES and TWOSIDES-shaped sample rows), not a
        curated interaction. Its `severity` is a PRR tier kept for internal use only;
        reports never show it as a clinical severity."""
        return self.source.strip().upper() in STATISTICAL_SOURCES

    def citation(self) -> str:
        return f"[{self.source}:{self.record_id}]"

    def to_dict(self) -> dict:
        return asdict(self)


SEVERITY_RANK = {"Major": 0, "Moderate": 1, "Minor": 2, "Unknown": 3}
STATISTICAL_SOURCES = {"TWOSIDES"}


class InteractionRetriever:
    """Retrieves interaction records for specified drug pairs."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or default_config
        self._df: Optional[pd.DataFrame] = None
        self._index: Dict[str, np.ndarray] = {}   # "a||b" (sorted, lowercase) -> row positions

    def load(self) -> "InteractionRetriever":
        from src.data.storage import read_table, table_exists
        path = self.cfg.paths.processed_dir / "interactions.parquet"
        if not table_exists(path):
            raise FileNotFoundError(
                f"Interactions table not found at {path} (or .csv). Run ingest_data.py first."
            )
        self._df = read_table(path)
        self._build_index()
        return self

    def load_from_dataframe(self, df: pd.DataFrame) -> "InteractionRetriever":
        self._df = df.copy()
        self._build_index()
        return self

    def _build_index(self) -> None:
        """Pair key -> row positions, built once with vectorized string ops.

        Replaces a row-by-row apply plus a full boolean scan per queried pair.
        Positions are in table order, so results match the old scan exactly.
        """
        df = self._df.reset_index(drop=True)
        a = df["drug_a_name"].fillna("").astype(str).str.lower().str.strip()
        b = df["drug_b_name"].fillna("").astype(str).str.lower().str.strip()
        lo, hi = a.where(a <= b, b), b.where(a <= b, a)
        df = df.assign(_key=lo + "||" + hi, _sev=df["severity"].map(SEVERITY_RANK).fillna(3))
        # Pre-sort once: pair, then severity, then PRR desc (NaN last). A stable sort keeps
        # table order for ties, exactly like the old per-query sort.
        df = df.sort_values(["_key", "_sev", "prr"], ascending=[True, True, False], kind="mergesort")
        self._df = df.reset_index(drop=True)
        self._index = {k: np.asarray(v) for k, v in self._df.groupby("_key", sort=False).indices.items()}

    @staticmethod
    def _pair_key(a: Optional[str], b: Optional[str]) -> str:
        a = (a or "").lower().strip()
        b = (b or "").lower().strip()
        return "||".join(sorted([a, b]))

    # ---------- public API ----------

    def retrieve_all(self, drug_a: str, drug_b: str) -> List[InteractionRecord]:
        """Every record for the pair, in severity / PRR order (the report selects from these)."""
        return self.retrieve_pair(drug_a, drug_b, top_k=0)

    def retrieve_pair(self, drug_a: str, drug_b: str, top_k: Optional[int] = None) -> List[InteractionRecord]:
        """Top records for the pair; top_k=None uses the configured top_k, 0 means all."""
        if self._df is None:
            raise RuntimeError("InteractionRetriever.load() must be called first.")

        positions = self._index.get(self._pair_key(drug_a, drug_b))
        if positions is None:
            return []
        # Positions are already in severity / PRR order (see _build_index).
        k = self.cfg.retrieval.top_k if top_k is None else top_k
        hits = self._df.iloc[positions[:k] if k else positions]
        records: List[InteractionRecord] = []
        for r in hits.to_dict("records"):
            records.append(
                InteractionRecord(
                    record_id=str(r["record_id"]),
                    drug_a=str(r.get("drug_a_name") or ""),
                    drug_b=str(r.get("drug_b_name") or ""),
                    drug_a_rxcui=_opt_str(r.get("drug_a_rxcui")),
                    drug_b_rxcui=_opt_str(r.get("drug_b_rxcui")),
                    condition=str(r.get("condition_name") or ""),
                    severity=str(r.get("severity") or "Unknown"),
                    prr=_opt_float(r.get("prr")),
                    frequency=_opt_float(r.get("frequency")),
                    source=str(r.get("source") or "TWOSIDES"),
                    mechanism=_opt_str(r.get("mechanism")),
                    reports=_opt_int(r.get("reports")),
                )
            )
        return records


def _opt_str(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    return str(x)


def _opt_int(x):
    f = _opt_float(x)
    return None if f is None else int(f)


def _opt_float(x):
    try:
        if x is None or pd.isna(x):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None
