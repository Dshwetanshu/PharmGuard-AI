"""Schema-aware loaders for each dataset.

Every loader:
  1. Reads the raw file from data/raw/
  2. Normalizes into a canonical schema used downstream
  3. Returns a DataFrame (processed parquet is written by ingestion.py)

The schemas below match the actual publicly-released formats. If you have a
variant (e.g. a filtered TWOSIDES subset), the column maps at the top of each
loader are the only thing you'd adjust.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


# ============================================================
# TWOSIDES (Tatonetti et al.) — primary DDI source
# ============================================================
# Reference: https://tatonettilab.org/resources/tatonetti-stm.html
# Columns (public release): drug_1_rxnorm_id, drug_1_concept_name,
#   drug_2_rxnorm_id, drug_2_concept_name, condition_meddra_id,
#   condition_concept_name, A, B, C, D, PRR, PRR_error, mean_reporting_frequency
#
# Semantics:
#   - Each row = one drug pair → one adverse condition with signal statistics
#   - PRR = proportional reporting ratio; higher = stronger signal
#   - mean_reporting_frequency = fraction of pair reports mentioning condition
TWOSIDES_COLUMN_MAP = {
    "drug_1_rxnorm_id": "drug_a_rxcui",
    "drug_1_concept_name": "drug_a_name",
    "drug_2_rxnorm_id": "drug_b_rxcui",
    "drug_2_concept_name": "drug_b_name",
    "condition_meddra_id": "condition_id",
    "condition_concept_name": "condition_name",
    "PRR": "prr",
    "mean_reporting_frequency": "frequency",
}


def load_twosides(path: Path, min_prr: float = 2.0) -> pd.DataFrame:
    """Load TWOSIDES interaction data and normalize to canonical schema.

    Returns columns:
      drug_a_rxcui, drug_a_name, drug_b_rxcui, drug_b_name,
      condition_id, condition_name, prr, frequency, severity, source, record_id
    """
    df = pd.read_csv(path, low_memory=False)

    # Rename available columns, tolerating missing ones
    present = {src: dst for src, dst in TWOSIDES_COLUMN_MAP.items() if src in df.columns}
    df = df.rename(columns=present)[list(present.values())]

    # Significance filter
    if "prr" in df.columns:
        df = df[df["prr"].fillna(0) >= min_prr].copy()

    # Lowercase names for matching
    for col in ("drug_a_name", "drug_b_name"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.lower().str.strip()

    # Synthesize a severity tier from PRR (TWOSIDES has no native severity field)
    df["severity"] = df["prr"].apply(_prr_to_severity) if "prr" in df.columns else "Unknown"
    df["source"] = "TWOSIDES"
    df["record_id"] = [f"TS-{i:08d}" for i in range(len(df))]
    return df.reset_index(drop=True)


def _prr_to_severity(prr: float) -> str:
    if prr is None or pd.isna(prr):
        return "Unknown"
    if prr >= 10:
        return "Major"
    if prr >= 4:
        return "Moderate"
    return "Minor"


# ============================================================
# DrugBank — drug metadata and mechanisms
# ============================================================
# DrugBank's open vocabulary CSV columns:
#   DrugBank ID, Accession Numbers, Common name, CAS, UNII, Synonyms,
#   Standard InChI Key
DRUGBANK_COLUMN_MAP = {
    "DrugBank ID": "drugbank_id",
    "Common name": "generic_name",
    "Synonyms": "synonyms",
    "CAS": "cas",
}


def load_drugbank_vocabulary(path: Path) -> pd.DataFrame:
    """Load the DrugBank open-access vocabulary CSV.

    Returns columns: drugbank_id, generic_name, synonyms (list), cas
    """
    df = pd.read_csv(path)
    present = {src: dst for src, dst in DRUGBANK_COLUMN_MAP.items() if src in df.columns}
    df = df.rename(columns=present)

    if "generic_name" in df.columns:
        df["generic_name"] = df["generic_name"].astype(str).str.lower().str.strip()
    if "synonyms" in df.columns:
        df["synonyms"] = df["synonyms"].fillna("").apply(
            lambda s: [x.strip().lower() for x in str(s).split("|") if x.strip()]
        )
    else:
        df["synonyms"] = [[] for _ in range(len(df))]

    keep = [c for c in ("drugbank_id", "generic_name", "synonyms", "cas") if c in df.columns]
    return df[keep].reset_index(drop=True)


# ============================================================
# SIDER — side effects
# ============================================================
# SIDER meddra_all_se.tsv columns (no header):
#   stitch_flat_id, stitch_stereo_id, umls_cui_label, meddra_concept_type,
#   umls_cui_meddra, side_effect_name
#
# We pull the flat STITCH id (CID...... form) which maps to PubChem CID.
SIDER_SE_COLUMNS = [
    "stitch_flat", "stitch_stereo", "umls_label",
    "meddra_type", "umls_meddra", "side_effect_name",
]


def load_sider_side_effects(path: Path) -> pd.DataFrame:
    """Load SIDER meddra_all_se.tsv.

    Returns columns: stitch_id, side_effect_name, umls_cui, source, record_id
    """
    df = pd.read_csv(path, sep="\t", header=None, names=SIDER_SE_COLUMNS, low_memory=False)
    # Keep only preferred terms to avoid duplication from lower-level terms
    df = df[df["meddra_type"] == "PT"].copy() if "meddra_type" in df.columns else df

    out = pd.DataFrame({
        "stitch_id": df["stitch_flat"],
        "side_effect_name": df["side_effect_name"].astype(str).str.lower().str.strip(),
        "umls_cui": df["umls_meddra"],
    })
    out["source"] = "SIDER"
    out["record_id"] = [f"SIDER-{i:08d}" for i in range(len(out))]
    return out.reset_index(drop=True)


# ============================================================
# RxNorm — drug name normalization backbone
# ============================================================
# RXNCONSO.RRF is pipe-delimited with a fixed 18-column schema.
# Columns of interest:
#   RXCUI (0), LAT (1), TS (2), TTY (12), SAB (11), STR (14), SUPPRESS (16)
# TTY = term type: IN (ingredient), BN (brand), SCD (clinical drug), etc.
RXNCONSO_COLUMNS = [
    "RXCUI", "LAT", "TS", "LUI", "STT", "SUI", "ISPREF", "RXAUI",
    "SAUI", "SCUI", "SDUI", "SAB", "TTY", "CODE", "STR", "SRL",
    "SUPPRESS", "CVF",
]


def load_rxnorm(path: Path, keep_tty: Optional[list] = None) -> pd.DataFrame:
    """Load RxNorm RXNCONSO.RRF and produce a compact name → RXCUI table.

    Returns columns: rxcui, name_lower, tty
    """
    keep_tty = keep_tty or ["IN", "PIN", "BN", "SCD", "SBD"]

    df = pd.read_csv(
        path,
        sep="|",
        header=None,
        names=RXNCONSO_COLUMNS + ["_"],  # trailing delimiter
        dtype=str,
        na_filter=False,
        low_memory=False,
    )
    df = df[(df["LAT"] == "ENG") & (df["SUPPRESS"] != "Y") & (df["TTY"].isin(keep_tty))]
    out = pd.DataFrame({
        "rxcui": df["RXCUI"],
        "name_lower": df["STR"].str.lower().str.strip(),
        "tty": df["TTY"],
    })
    return out.drop_duplicates(subset=["rxcui", "name_lower"]).reset_index(drop=True)


# ============================================================
# WebMD Drug Reviews — patient experience retrieval
# ============================================================
# Kaggle columns: Drug, Condition, Reviews, Sides, EaseofUse, Effectiveness,
#                 Satisfaction, UsefulCount, Age, Sex, Date
WEBMD_COLUMN_MAP = {
    "Drug": "drug_name",
    "Condition": "condition",
    "Reviews": "review_text",
    "Sides": "reported_side_effects",
    "Effectiveness": "effectiveness",
    "Satisfaction": "satisfaction",
}


def load_webmd_reviews(path: Path, max_rows: Optional[int] = None) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    if max_rows:
        df = df.head(max_rows)
    present = {src: dst for src, dst in WEBMD_COLUMN_MAP.items() if src in df.columns}
    df = df.rename(columns=present)
    keep = [c for c in present.values() if c in df.columns]
    df = df[keep].copy()
    if "drug_name" in df.columns:
        df["drug_name"] = df["drug_name"].astype(str).str.lower().str.strip()
    df["source"] = "WebMD"
    df["record_id"] = [f"WMD-{i:08d}" for i in range(len(df))]
    return df.reset_index(drop=True)


# ============================================================
# Medical Recommendation / Medical Prescription (Kaggle)
# ============================================================
# Schemas vary by uploader; we do a permissive load and let the user adjust.
def load_generic_csv(path: Path, **kwargs) -> pd.DataFrame:
    """Fallback loader for auxiliary CSV datasets."""
    return pd.read_csv(path, low_memory=False, **kwargs)


# ============================================================
# DDInter 2.0 (Tian et al. 2025) — curated interactions with severity
# ============================================================
# Reference: https://ddinter2.scbdd.com
# Public release columns (CSV, one file per ATC class merged):
#   DDInterID_A, Drug_A, DDInterID_B, Drug_B, Level, Mechanism
# Level ∈ {Major, Moderate, Minor, Unknown}
# Mechanism = short natural-language description
#
# Why this is secondary to TWOSIDES in our pipeline: DDInter provides curated
# severity labels and mechanism prose; TWOSIDES provides signal statistics (PRR).
# When both are loaded the retriever can cross-validate severity.
DDINTER_COLUMN_MAP = {
    "DDInterID_A": "ddinter_id_a",
    "Drug_A": "drug_a_name",
    "DDInterID_B": "ddinter_id_b",
    "Drug_B": "drug_b_name",
    "Level": "severity",
    "Mechanism": "mechanism",
}


def load_ddinter(path: Path) -> pd.DataFrame:
    """Load DDInter 2.0 interaction data.

    Returns columns:
      drug_a_name, drug_b_name, severity, mechanism, condition_name,
      source, record_id, (drug_a_rxcui, drug_b_rxcui, prr, frequency set to None)
    """
    df = pd.read_csv(path, low_memory=False)
    present = {src: dst for src, dst in DDINTER_COLUMN_MAP.items() if src in df.columns}
    df = df.rename(columns=present)

    for col in ("drug_a_name", "drug_b_name"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.lower().str.strip()

    # Normalize severity to the Major/Moderate/Minor/Unknown vocabulary used downstream
    if "severity" in df.columns:
        df["severity"] = df["severity"].fillna("Unknown").astype(str).str.strip()
        df.loc[~df["severity"].isin(["Major", "Moderate", "Minor"]), "severity"] = "Unknown"

    # DDInter has no per-condition row; use the mechanism as the condition label
    df["condition_name"] = df.get("mechanism", "interaction").fillna("interaction").astype(str).str.lower()
    df["condition_id"] = None

    # Align schema with TWOSIDES so both flow through the same retriever
    for col in ("drug_a_rxcui", "drug_b_rxcui", "prr", "frequency"):
        if col not in df.columns:
            df[col] = None

    df["source"] = "DDInter"
    df["record_id"] = [f"DDI-{i:08d}" for i in range(len(df))]

    keep = [c for c in (
        "drug_a_name", "drug_b_name", "drug_a_rxcui", "drug_b_rxcui",
        "condition_name", "condition_id", "severity", "mechanism",
        "prr", "frequency", "source", "record_id",
    ) if c in df.columns]
    return df[keep].reset_index(drop=True)


# ============================================================
# UCI Drug Review Dataset (Gräßer et al.)
# ============================================================
# Reference: https://kaggle.com/datasets/jessicali9530/kuc-hackathon-winter-2018
# Columns: uniqueID, drugName, condition, review, rating, date, usefulCount
UCI_COLUMN_MAP = {
    "drugName": "drug_name",
    "condition": "condition",
    "review": "review_text",
    "rating": "rating",
}


def load_uci_reviews(path: Path, max_rows: Optional[int] = 30_000) -> pd.DataFrame:
    """Load UCI Drug Review dataset.

    Returns columns compatible with WebMD reviews so they merge in the same store:
      drug_name, condition, review_text, rating (0–10), source, record_id
    """
    # UCI ships as train/test TSVs; this loader accepts either
    sep = "\t" if str(path).lower().endswith(".tsv") else ","
    df = pd.read_csv(path, sep=sep, low_memory=False)
    if max_rows:
        df = df.head(max_rows)
    present = {src: dst for src, dst in UCI_COLUMN_MAP.items() if src in df.columns}
    df = df.rename(columns=present)
    keep = [c for c in present.values() if c in df.columns]
    df = df[keep].copy()

    if "drug_name" in df.columns:
        df["drug_name"] = df["drug_name"].astype(str).str.lower().str.strip()
    if "review_text" in df.columns:
        df["review_text"] = df["review_text"].astype(str)

    df["source"] = "UCI"
    df["record_id"] = [f"UCI-{i:08d}" for i in range(len(df))]
    return df.reset_index(drop=True)


# ============================================================
# ADE-Corpus-V2 (Gurulingappa et al.)
# ============================================================
# Reference: https://huggingface.co/datasets/ade_corpus_v2
# HuggingFace release has three configs; we consume "Ade_corpus_v2_drug_ade_relation"
# which has columns: text, drug, effect
# Each row = one sentence asserting that a drug produces an adverse effect.
#
# Role in PharmGuard: per-drug adverse-event context (complements SIDER).
ADE_COLUMN_MAP = {
    "text": "sentence",
    "drug": "drug_name",
    "effect": "adverse_effect",
}


def load_ade_corpus(path: Path) -> pd.DataFrame:
    """Load ADE-Corpus-V2 drug-adverse-effect relation file.

    Accepts either CSV or HuggingFace JSONL. Returns columns:
      drug_name, adverse_effect, sentence, source, record_id
    """
    p = str(path).lower()
    if p.endswith(".jsonl") or p.endswith(".json"):
        df = pd.read_json(path, lines=p.endswith(".jsonl"))
    else:
        df = pd.read_csv(path, low_memory=False)

    present = {src: dst for src, dst in ADE_COLUMN_MAP.items() if src in df.columns}
    df = df.rename(columns=present)

    if "drug_name" in df.columns:
        df["drug_name"] = df["drug_name"].astype(str).str.lower().str.strip()
    if "adverse_effect" in df.columns:
        df["adverse_effect"] = df["adverse_effect"].astype(str).str.lower().str.strip()

    keep = [c for c in ("drug_name", "adverse_effect", "sentence") if c in df.columns]
    df = df[keep].copy()

    df["source"] = "ADE"
    df["record_id"] = [f"ADE-{i:08d}" for i in range(len(df))]
    return df.reset_index(drop=True)
