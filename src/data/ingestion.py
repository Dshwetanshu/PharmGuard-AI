"""Synthetic-sample ingestion: data/sample/ -> data/processed/.

Real data (RxNorm, DDInter, SIDER, TWOSIDES) is ingested by src/data/real_ingest.py.
The sample ingest produces:
  data/processed/drug_vocabulary.parquet     (for normalizer)
  data/processed/interactions.parquet        (for interaction retrieval)
  data/processed/side_effects.parquet        (for SIDER retrieval)
  data/processed/reviews.parquet             (for WebMD context retrieval)
  data/processed/chroma/                     (vector store, built separately)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import Config, config as default_config
from src.data.storage import write_table
from src.data.provenance import write_provenance
from src.data.canonical import (
    build_alias_map,
    canonicalize_columns,
    ensure_self_aliases,
    find_join_integrity_issues,
)


INTERACTION_NAME_COLS = ("drug_a_name", "drug_b_name")
SIDE_EFFECT_NAME_COLS = ("drug_name",)
REVIEW_NAME_COLS = ("drug_name",)

class Ingester:
    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or default_config
        self.cfg.paths.processed_dir.mkdir(parents=True, exist_ok=True)

    # ---------- canonical keys ----------

    @staticmethod
    def _canonical(df: Optional[pd.DataFrame], columns, alias_map) -> Optional[pd.DataFrame]:
        if df is None or alias_map is None:
            return df
        return canonicalize_columns(df, columns, alias_map)

    @staticmethod
    def _join_integrity(interactions, side_effects, alias_map) -> dict:
        """Every drug name in the interaction and side-effect tables must resolve
        to itself through the local vocabulary; report the ones that don't."""
        if alias_map is None:
            return {"checked": False, "reason": "no drug vocabulary ingested", "issues": []}
        issues = find_join_integrity_issues(
            {
                "interactions": (interactions, INTERACTION_NAME_COLS),
                "side_effects": (side_effects, SIDE_EFFECT_NAME_COLS),
            },
            alias_map,
        )
        for i in issues:
            print(f"  [join-integrity] {i.table}.{i.column}: {i.name!r} resolves to {i.resolves_to!r}")
        return {"checked": True, "issues": [i.__dict__ for i in issues]}

    # ---------- dataset merge helpers ----------

    @staticmethod
    def _merge_interactions(tw: Optional[pd.DataFrame], ddi: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        frames = [f for f in (tw, ddi) if f is not None]
        if not frames:
            return None
        # Ensure both frames have the union of columns
        all_cols = set()
        for f in frames:
            all_cols.update(f.columns)
        aligned = []
        for f in frames:
            f = f.copy()
            for c in all_cols:
                if c not in f.columns:
                    f[c] = None
            aligned.append(f[sorted(all_cols)])
        return pd.concat(aligned, ignore_index=True)

    @staticmethod
    def _merge_side_effects(sider: Optional[pd.DataFrame], ade: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        frames = []
        if sider is not None and not sider.empty:
            frames.append(sider[["drug_name", "side_effect_name", "umls_cui", "source", "record_id"]]
                          if "drug_name" in sider.columns
                          else sider.assign(drug_name=None)[["drug_name", "side_effect_name", "umls_cui", "source", "record_id"]])
        if ade is not None and not ade.empty:
            ade_mapped = ade.rename(columns={"adverse_effect": "side_effect_name"}).copy()
            if "umls_cui" not in ade_mapped.columns:
                ade_mapped["umls_cui"] = None
            frames.append(ade_mapped[["drug_name", "side_effect_name", "umls_cui", "source", "record_id"]])
        if not frames:
            return None
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def _merge_reviews(webmd: Optional[pd.DataFrame], uci: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        frames = [f for f in (webmd, uci) if f is not None and not f.empty]
        if not frames:
            return None
        all_cols = set()
        for f in frames:
            all_cols.update(f.columns)
        aligned = []
        for f in frames:
            f = f.copy()
            for c in all_cols:
                if c not in f.columns:
                    f[c] = None
            aligned.append(f[sorted(all_cols)])
        return pd.concat(aligned, ignore_index=True)

    # ---------- sample-mode ingestion ----------

    def ingest_sample(self) -> dict:
        """Ingest from data/sample/ — small curated CSVs that match the processed schema.

        Sample files live in data/sample/ and use the *processed* schema directly,
        so no schema transformation is needed. This lets users demo end-to-end
        without downloading any of the large public datasets.

        Merges:
          interactions = twosides sample ∪ ddinter sample
          side_effects = sider sample ∪ ade sample
          reviews      = webmd sample  ∪ uci sample
        """
        sample = self.cfg.paths.sample_dir
        report = {}

        def _read(name: str) -> Optional[pd.DataFrame]:
            p = sample / f"{name}.csv"
            return pd.read_csv(p) if p.exists() else None

        # 1. drug_vocabulary (single-source)
        vocab = _read("drug_vocabulary")
        alias_map = None
        if vocab is not None:
            vocab = ensure_self_aliases(vocab)
            alias_map = build_alias_map(vocab)
            out = write_table(vocab, self.cfg.paths.processed_dir / "drug_vocabulary.parquet")
            report["drug_vocabulary"] = {"rows": len(vocab), "path": str(out)}

        # 2. interactions = twosides ∪ ddinter
        tw = _read("interactions")
        ddi = _read("ddinter")
        interactions = self._canonical(self._merge_interactions(tw, ddi), INTERACTION_NAME_COLS, alias_map)
        if interactions is not None:
            out = write_table(interactions, self.cfg.paths.processed_dir / "interactions.parquet")
            by_src = interactions.groupby("source").size().to_dict() if "source" in interactions.columns else {}
            report["interactions"] = {"rows": len(interactions), "by_source": by_src, "path": str(out)}

        # 3. side_effects = sider ∪ ade
        sider = _read("side_effects")
        ade = _read("ade_corpus")
        if ade is not None:
            ade = ade.rename(columns={"adverse_effect": "side_effect_name"})
            if "umls_cui" not in ade.columns:
                ade["umls_cui"] = None
        se = self._canonical(self._merge_side_effects(sider, ade), SIDE_EFFECT_NAME_COLS, alias_map)
        if se is not None:
            out = write_table(se, self.cfg.paths.processed_dir / "side_effects.parquet")
            by_src = se.groupby("source").size().to_dict() if "source" in se.columns else {}
            report["side_effects"] = {"rows": len(se), "by_source": by_src, "path": str(out)}

        # 4. reviews = webmd ∪ uci
        webmd = _read("reviews")
        uci = _read("uci_reviews")
        reviews = self._canonical(self._merge_reviews(webmd, uci), REVIEW_NAME_COLS, alias_map)
        if reviews is not None:
            out = write_table(reviews, self.cfg.paths.processed_dir / "reviews.parquet")
            by_src = reviews.groupby("source").size().to_dict() if "source" in reviews.columns else {}
            report["reviews"] = {"rows": len(reviews), "by_source": by_src, "path": str(out)}

        report["join_integrity"] = self._join_integrity(interactions, se, alias_map)
        report["provenance"] = str(write_provenance(self.cfg.paths.processed_dir, "sample", report))
        return report

    # ---------- helpers ----------
