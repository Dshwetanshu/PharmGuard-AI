"""SIDER side-effect retrieval.

SIDER records per-drug adverse events (single-drug side effects), not drug-drug
interactions. We use it as *supplementary* context: for each drug in the input,
what are its known top adverse events? This helps the generator explain why an
interaction might be concerning (e.g., "both drugs independently prolong QT").
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional

import pandas as pd

from src.config import Config, config as default_config


@dataclass
class SideEffectRecord:
    record_id: str
    drug_name: str
    side_effect: str
    umls_cui: Optional[str]
    source: str = "SIDER"

    def to_dict(self) -> dict:
        return asdict(self)


class SideEffectRetriever:
    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or default_config
        self._df: Optional[pd.DataFrame] = None

    def load(self) -> "SideEffectRetriever":
        from src.data.storage import read_table, table_exists
        path = self.cfg.paths.processed_dir / "side_effects.parquet"
        if not table_exists(path):
            # SIDER is optional; gracefully return an empty retriever
            self._df = pd.DataFrame()
            return self
        self._df = read_table(path)
        return self

    def load_from_dataframe(self, df: pd.DataFrame) -> "SideEffectRetriever":
        self._df = df.copy()
        return self

    def retrieve_for_drug(self, drug_name: str, top_k: int = 10) -> List[SideEffectRecord]:
        if self._df is None or self._df.empty:
            return []

        name = (drug_name or "").lower().strip()
        # SIDER is keyed by STITCH id, not name. If the sample/processed data
        # already has a drug_name column (common in curated subsets), use it.
        if "drug_name" in self._df.columns:
            hits = self._df[self._df["drug_name"].astype(str).str.lower() == name]
        else:
            return []

        hits = hits.head(top_k)
        return [
            SideEffectRecord(
                record_id=str(r["record_id"]),
                drug_name=str(r["drug_name"]).lower(),
                side_effect=str(r["side_effect_name"]),
                umls_cui=str(r.get("umls_cui")) if pd.notna(r.get("umls_cui")) else None,
            )
            for _, r in hits.iterrows()
        ]
