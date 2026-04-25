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
from typing import List, Optional

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

    def citation(self) -> str:
        return f"[{self.source}:{self.record_id}]"

    def to_dict(self) -> dict:
        return asdict(self)


class InteractionRetriever:
    """Retrieves interaction records for specified drug pairs."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or default_config
        self._df: Optional[pd.DataFrame] = None

    def load(self) -> "InteractionRetriever":
        from src.data.storage import read_table, table_exists
        path = self.cfg.paths.processed_dir / "interactions.parquet"
        if not table_exists(path):
            raise FileNotFoundError(
                f"Interactions table not found at {path} (or .csv). Run ingest_data.py first."
            )
        self._df = read_table(path)
        # Build a fast lookup index — lowercase & sorted pair key
        self._df["_pair_key"] = self._df.apply(
            lambda r: self._pair_key(r.get("drug_a_name"), r.get("drug_b_name")), axis=1
        )
        return self

    def load_from_dataframe(self, df: pd.DataFrame) -> "InteractionRetriever":
        self._df = df.copy()
        self._df["_pair_key"] = self._df.apply(
            lambda r: self._pair_key(r.get("drug_a_name"), r.get("drug_b_name")), axis=1
        )
        return self

    @staticmethod
    def _pair_key(a: Optional[str], b: Optional[str]) -> str:
        a = (a or "").lower().strip()
        b = (b or "").lower().strip()
        return "||".join(sorted([a, b]))

    # ---------- public API ----------

    def retrieve_pair(self, drug_a: str, drug_b: str, top_k: Optional[int] = None) -> List[InteractionRecord]:
        if self._df is None:
            raise RuntimeError("InteractionRetriever.load() must be called first.")

        key = self._pair_key(drug_a, drug_b)
        hits = self._df[self._df["_pair_key"] == key]

        if hits.empty:
            return []

        # Severity order: Major > Moderate > Minor > Unknown, then PRR desc
        severity_rank = {"Major": 0, "Moderate": 1, "Minor": 2, "Unknown": 3}
        hits = hits.assign(_sev=hits["severity"].map(severity_rank).fillna(3))
        hits = hits.sort_values(["_sev", "prr"], ascending=[True, False])

        k = top_k or self.cfg.retrieval.top_k
        hits = hits.head(k)

        records: List[InteractionRecord] = []
        for _, r in hits.iterrows():
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
                )
            )
        return records


def _opt_str(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    return str(x)


def _opt_float(x):
    try:
        if x is None or pd.isna(x):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None
