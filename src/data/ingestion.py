"""Data ingestion: raw → processed.

Runs once after datasets are placed in data/raw/. Produces:
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
from src.data.loaders import (
    load_twosides,
    load_ddinter,
    load_drugbank_vocabulary,
    load_sider_side_effects,
    load_rxnorm,
    load_webmd_reviews,
    load_uci_reviews,
    load_ade_corpus,
)


RAW_FILE_HINTS = {
    "twosides": "twosides.csv",
    "ddinter": "ddinter.csv",
    "drugbank": "drugbank_vocabulary.csv",
    "sider_se": "meddra_all_se.tsv",
    "rxnorm": "rxnorm_RXNCONSO.RRF",
    "webmd": "webmd.csv",
    "uci": "uci_drug_reviews.csv",
    "ade": "ade_corpus.csv",
}


class Ingester:
    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or default_config
        self.cfg.paths.processed_dir.mkdir(parents=True, exist_ok=True)

    # ---------- full-mode ingestion ----------

    def ingest_full(self) -> dict:
        """Ingest all datasets from data/raw/. Missing files are skipped with a note."""
        report = {}
        raw = self.cfg.paths.raw_dir

        # 1. RxNorm + DrugBank → drug_vocabulary
        rxnorm_df = self._maybe_load(raw / RAW_FILE_HINTS["rxnorm"], load_rxnorm)
        drugbank_df = self._maybe_load(raw / RAW_FILE_HINTS["drugbank"], load_drugbank_vocabulary)
        vocab = self._build_vocabulary(rxnorm_df, drugbank_df)
        if vocab is not None:
            out = write_table(vocab, self.cfg.paths.processed_dir / "drug_vocabulary.parquet")
            report["drug_vocabulary"] = {"rows": len(vocab), "path": str(out)}

        # 2. TWOSIDES + DDInter → unified interactions
        tw = self._maybe_load(
            raw / RAW_FILE_HINTS["twosides"],
            lambda p: load_twosides(p, min_prr=self.cfg.retrieval.twosides_min_prr),
        )
        ddi = self._maybe_load(raw / RAW_FILE_HINTS["ddinter"], load_ddinter)
        merged_interactions = self._merge_interactions(tw, ddi)
        if merged_interactions is not None:
            out = write_table(
                merged_interactions,
                self.cfg.paths.processed_dir / "interactions.parquet",
            )
            by_src = merged_interactions.groupby("source").size().to_dict() if "source" in merged_interactions.columns else {}
            report["interactions"] = {
                "rows": len(merged_interactions),
                "by_source": by_src,
                "path": str(out),
            }

        # 3. SIDER + ADE → side_effects
        sider = self._maybe_load(raw / RAW_FILE_HINTS["sider_se"], load_sider_side_effects)
        ade = self._maybe_load(raw / RAW_FILE_HINTS["ade"], load_ade_corpus)
        merged_se = self._merge_side_effects(sider, ade)
        if merged_se is not None:
            out = write_table(merged_se, self.cfg.paths.processed_dir / "side_effects.parquet")
            by_src = merged_se.groupby("source").size().to_dict() if "source" in merged_se.columns else {}
            report["side_effects"] = {
                "rows": len(merged_se),
                "by_source": by_src,
                "path": str(out),
            }

        # 4. WebMD + UCI → reviews
        webmd = self._maybe_load(
            raw / RAW_FILE_HINTS["webmd"], lambda p: load_webmd_reviews(p, max_rows=50_000)
        )
        uci = self._maybe_load(
            raw / RAW_FILE_HINTS["uci"], lambda p: load_uci_reviews(p, max_rows=30_000)
        )
        merged_reviews = self._merge_reviews(webmd, uci)
        if merged_reviews is not None:
            out = write_table(merged_reviews, self.cfg.paths.processed_dir / "reviews.parquet")
            by_src = merged_reviews.groupby("source").size().to_dict() if "source" in merged_reviews.columns else {}
            report["reviews"] = {
                "rows": len(merged_reviews),
                "by_source": by_src,
                "path": str(out),
            }

        return report

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
        if vocab is not None:
            out = write_table(vocab, self.cfg.paths.processed_dir / "drug_vocabulary.parquet")
            report["drug_vocabulary"] = {"rows": len(vocab), "path": str(out)}

        # 2. interactions = twosides ∪ ddinter
        tw = _read("interactions")
        ddi = _read("ddinter")
        interactions = self._merge_interactions(tw, ddi)
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
        se = self._merge_side_effects(sider, ade)
        if se is not None:
            out = write_table(se, self.cfg.paths.processed_dir / "side_effects.parquet")
            by_src = se.groupby("source").size().to_dict() if "source" in se.columns else {}
            report["side_effects"] = {"rows": len(se), "by_source": by_src, "path": str(out)}

        # 4. reviews = webmd ∪ uci
        webmd = _read("reviews")
        uci = _read("uci_reviews")
        reviews = self._merge_reviews(webmd, uci)
        if reviews is not None:
            out = write_table(reviews, self.cfg.paths.processed_dir / "reviews.parquet")
            by_src = reviews.groupby("source").size().to_dict() if "source" in reviews.columns else {}
            report["reviews"] = {"rows": len(reviews), "by_source": by_src, "path": str(out)}

        return report

    # ---------- helpers ----------

    def _maybe_load(self, path: Path, loader):
        if not path.exists():
            print(f"  [skip] {path.name} not found in {path.parent}")
            return None
        print(f"  [load] {path.name}")
        return loader(path)

    def _build_vocabulary(
        self, rxnorm_df: Optional[pd.DataFrame], drugbank_df: Optional[pd.DataFrame]
    ) -> Optional[pd.DataFrame]:
        frames = []

        if rxnorm_df is not None:
            rx = rxnorm_df.copy()
            # Pick the canonical generic (TTY=IN) per RXCUI when available
            ingredients = rx[rx["tty"].isin(["IN", "PIN"])].groupby("rxcui")["name_lower"].first()
            rx["generic_name"] = rx["rxcui"].map(ingredients)
            rx["generic_name"] = rx["generic_name"].fillna(rx["name_lower"])
            rx["drugbank_id"] = None
            frames.append(rx[["name_lower", "generic_name", "rxcui", "drugbank_id"]])

        if drugbank_df is not None:
            rows = []
            for _, r in drugbank_df.iterrows():
                gn = r.get("generic_name")
                db_id = r.get("drugbank_id")
                if gn:
                    rows.append({"name_lower": gn, "generic_name": gn, "rxcui": None, "drugbank_id": db_id})
                for syn in r.get("synonyms") or []:
                    rows.append({"name_lower": syn, "generic_name": gn, "rxcui": None, "drugbank_id": db_id})
            frames.append(pd.DataFrame(rows))

        if not frames:
            return None

        combined = pd.concat(frames, ignore_index=True)
        combined = combined.dropna(subset=["name_lower"])
        combined["name_lower"] = combined["name_lower"].astype(str).str.lower().str.strip()
        combined = combined[combined["name_lower"] != ""]

        # Keep the row with the most information per name
        combined["_score"] = combined[["rxcui", "drugbank_id"]].notna().sum(axis=1)
        combined = (
            combined.sort_values("_score", ascending=False)
            .drop_duplicates(subset=["name_lower"], keep="first")
            .drop(columns=["_score"])
            .reset_index(drop=True)
        )
        return combined
