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

import hashlib
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

import pandas as pd


def _content_ids(df: pd.DataFrame, prefix: str) -> List[str]:
    """Deterministic record IDs derived from row content, e.g. "TS-3f9a0c1b2d".

    The ID hashes every column except record_id (in sorted column order), so it
    does not change when rows are reordered or other rows are filtered out.
    Exact duplicate rows get "-2", "-3" suffixes; they are indistinguishable,
    so which copy gets which suffix does not matter. Sample CSVs keep their own
    hand-assigned IDs (e.g. TS-00000006) because they already carry record_id.
    """
    cols = sorted(c for c in df.columns if c != "record_id")
    keys = pd.Series("", index=df.index)
    for c in cols:  # explicit str() so missing values hash the same on pandas 2 and 3
        keys = keys + "\x1f" + df[c].map(lambda v: "" if pd.isna(v) else str(v))
    digests = keys.map(lambda k: hashlib.sha1(k.encode("utf-8")).hexdigest()[:10])
    nth = digests.groupby(digests).cumcount()
    return [f"{prefix}-{d}" if n == 0 else f"{prefix}-{d}-{n + 1}" for d, n in zip(digests, nth)]


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
    "drug_1_rxnorn_id": "drug_a_rxcui",     # sic: the published header has this typo
    "drug_1_rxnorm_id": "drug_a_rxcui",
    "drug_1_concept_name": "drug_a_name",
    "drug_2_rxnorm_id": "drug_b_rxcui",
    "drug_2_concept_name": "drug_b_name",
    "condition_meddra_id": "condition_id",
    "condition_concept_name": "condition_name",
    "PRR": "prr",
    "A": "reports",
    "mean_reporting_frequency": "frequency",
}

# MedDRA terms that describe reporting or administration, not an adverse event
# (reviewed list; lowercase). Dropped by load_twosides_filtered.
TWOSIDES_ADMIN_TERMS = {
    "drug ineffective", "off label use", "drug interaction", "product use issue", "no adverse event",
    "medication error", "drug administration error", "incorrect dose administered", "drug dose omission",
    "wrong technique in product usage process", "inappropriate schedule of product administration",
    "intentional product misuse", "product quality issue", "exposure during pregnancy",
    "drug exposure during pregnancy",
}


def load_twosides(path: Path, min_prr: float = 2.0) -> pd.DataFrame:
    """Load TWOSIDES interaction data and normalize to canonical schema.

    Returns columns:
      drug_a_rxcui, drug_a_name, drug_b_rxcui, drug_b_name,
      condition_id, condition_name, prr, frequency, severity, source, record_id
    """
    df = pd.read_csv(path, low_memory=False)

    # Rename available columns, tolerating missing ones
    present = {src: dst for src, dst in TWOSIDES_COLUMN_MAP.items() if src in df.columns and dst != "reports"}
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
    df["record_id"] = _content_ids(df, "TS")
    return df.reset_index(drop=True)


def load_twosides_filtered(path: Path, name_to_generic: Dict[str, str], rxcui_to_generic: Dict[str, str],
                           min_prr: float = 2.0, min_reports: int = 5, top_events: int = 5,
                           exclude_terms=TWOSIDES_ADMIN_TERMS, chunksize: int = 500_000
                           ) -> Tuple[pd.DataFrame, Dict]:
    """Stream the full TWOSIDES file (~43M rows) in chunks and keep a filtered subset.

    Per row: PRR >= min_prr, A >= min_reports co-reports, event not administrative,
    and both drugs map to a canonical vocabulary name (by RxCUI, else by name).
    Per canonical pair: one row per event (the higher-PRR orientation), then the
    top_events events by PRR (ties by A). Unmatched drug names are counted, not
    silently dropped. Returns (dataframe, stats).

    Memory: each chunk is pruned to its own top_events per pair before the final
    cut. That gives the same result as one global cut: a row in the global top k
    is the best for its event and outranks all but < k events, so it is also in
    its chunk's top k (dedupe happens first, with the same tie-break).
    """
    stats = Counter()
    unmatched: Counter = Counter()
    names_seen: set = set()
    kept = []
    wanted = set(TWOSIDES_COLUMN_MAP)
    for chunk in pd.read_csv(path, chunksize=chunksize, dtype=str, compression="infer",
                             usecols=lambda col: col in wanted):
        present = {src: dst for src, dst in TWOSIDES_COLUMN_MAP.items() if src in chunk.columns}
        c = chunk.rename(columns=present)
        stats["rows_read"] += len(c)
        prr = pd.to_numeric(c["prr"], errors="coerce").fillna(0.0)
        reports = pd.to_numeric(c["reports"], errors="coerce").fillna(0).astype(int)
        m = prr >= min_prr
        stats["dropped_prr"] += int((~m).sum())
        m2 = m & (reports >= min_reports)
        stats["dropped_min_reports"] += int((m & ~m2).sum())
        cond = c["condition_name"].astype(str).str.strip().str.lower()
        m3 = m2 & ~cond.isin(exclude_terms)
        stats["dropped_administrative"] += int((m2 & ~m3).sum())
        c = c[m3].assign(prr=prr[m3], reports=reports[m3], condition_name=cond[m3])

        def canon(side):
            by_id = c[f"drug_{side}_rxcui"].astype(str).str.strip().map(rxcui_to_generic)
            by_name = c[f"drug_{side}_name"].astype(str).str.strip().str.lower().map(name_to_generic)
            return by_id.fillna(by_name)

        ga, gb = canon("a"), canon("b")
        for side in ("a", "b"):
            names_seen.update(c[f"drug_{side}_name"].astype(str).str.strip().str.lower().unique())
        miss = ga.isna() | gb.isna()
        for side, g in (("a", ga), ("b", gb)):
            for name, n in c.loc[g.isna(), f"drug_{side}_name"].astype(str).str.strip().str.lower().value_counts().items():
                unmatched[name] += int(n)
        stats["dropped_unmatched_drug"] += int(miss.sum())
        c, ga, gb = c[~miss], ga[~miss], gb[~miss]
        same = ga == gb
        stats["dropped_self_pair"] += int(same.sum())
        c, ga, gb = c[~same], ga[~same], gb[~same]
        swap = ga > gb
        out = pd.DataFrame({
            "drug_a_name": ga.where(~swap, gb), "drug_b_name": gb.where(~swap, ga),
            "drug_a_rxcui": c["drug_a_rxcui"].where(~swap, c["drug_b_rxcui"]),
            "drug_b_rxcui": c["drug_b_rxcui"].where(~swap, c["drug_a_rxcui"]),
            "condition_id": c["condition_id"], "condition_name": c["condition_name"],
            "prr": c["prr"], "reports": c["reports"],
            "frequency": pd.to_numeric(c["frequency"], errors="coerce"),
            # identity of the source row, for stable content-derived IDs
            "_raw": c["drug_a_rxcui"].astype(str) + "|" + c["drug_b_rxcui"].astype(str) + "|"
                    + c["condition_id"].astype(str) + "|" + c["prr"].astype(str) + "|" + c["reports"].astype(str),
        })
        out, dups, cut = _dedupe_top_events(out, top_events)
        stats["dropped_orientation_duplicates"] += dups
        stats["dropped_top_k"] += cut
        kept.append(out)
    df = pd.concat(kept, ignore_index=True) if kept else pd.DataFrame(columns=[
        "drug_a_name", "drug_b_name", "drug_a_rxcui", "drug_b_rxcui", "condition_id", "condition_name", "prr",
        "reports", "frequency", "_raw"])
    df, dups, cut = _dedupe_top_events(df, top_events)
    stats["dropped_orientation_duplicates"] += dups
    stats["dropped_top_k"] += cut
    df["record_id"] = _content_ids(df[["_raw"]], "TS")
    df = df.drop(columns=["_raw"])
    df["severity"] = df["prr"].apply(_prr_to_severity)
    df["source"], df["mechanism"] = "TWOSIDES", None
    stats["rows_kept"] = len(df)
    stats["pairs_kept"] = int(df.groupby(["drug_a_name", "drug_b_name"]).ngroups) if len(df) else 0
    out = dict(stats)
    out["unmatched_names"] = dict(unmatched)
    out["distinct_names_seen"] = len(names_seen)          # after the PRR / A / administrative filters
    out["distinct_names_matched"] = len(names_seen - set(unmatched))
    out["filters"] = {"min_prr": min_prr, "min_reports": min_reports, "top_events_per_pair": top_events,
                      "excluded_terms": sorted(exclude_terms)}
    return df.reset_index(drop=True), out


def _dedupe_top_events(df: pd.DataFrame, k: int) -> Tuple[pd.DataFrame, int, int]:
    """One row per (pair, event) with the highest PRR (ties: reports, then source row),
    then the k highest-PRR events per pair. Returns (df, duplicates dropped, rows cut)."""
    n0 = len(df)
    df = df.sort_values(["drug_a_name", "drug_b_name", "condition_id", "prr", "reports", "_raw"],
                        ascending=[True, True, True, False, False, True])
    df = df.drop_duplicates(["drug_a_name", "drug_b_name", "condition_id"], keep="first")
    n1 = len(df)
    df = df.sort_values(["drug_a_name", "drug_b_name", "prr", "reports", "_raw"],
                        ascending=[True, True, False, False, True])
    df = df.groupby(["drug_a_name", "drug_b_name"], sort=False).head(k)
    return df, n0 - n1, n1 - len(df)


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
    "UNII": "unii",
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

    keep = [c for c in ("drugbank_id", "generic_name", "synonyms", "cas", "unii") if c in df.columns]
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


def load_sider(se_path: Path, names_path: Path) -> pd.DataFrame:
    """Load SIDER side effects with drug names joined from drug_names.tsv.

    Keeps MedDRA preferred terms (PT) and one row per (drug, side effect).
    Returns: stitch_id, drug_name, side_effect_name, umls_cui, source, record_id
    (drug_name is None for a STITCH id with no entry in drug_names.tsv).
    """
    df = pd.read_csv(se_path, sep="\t", header=None, names=SIDER_SE_COLUMNS, dtype=str, compression="infer")
    df = df[df["meddra_type"] == "PT"]
    names = pd.read_csv(names_path, sep="\t", header=None, names=["stitch_flat", "drug_name"], dtype=str)
    name_of = dict(zip(names.stitch_flat, names.drug_name.str.strip().str.lower()))
    out = pd.DataFrame({
        "stitch_id": df["stitch_flat"].values,
        "drug_name": df["stitch_flat"].map(name_of).values,
        "side_effect_name": df["side_effect_name"].astype(str).str.lower().str.strip().values,
        "umls_cui": df["umls_meddra"].values,
    }).drop_duplicates(["stitch_id", "side_effect_name"]).sort_values(["stitch_id", "side_effect_name"])
    out["source"] = "SIDER"
    out["record_id"] = _content_ids(out, "SIDER")
    return out.reset_index(drop=True)


def load_sider_side_effects(path: Path) -> pd.DataFrame:
    """Load SIDER meddra_all_se.tsv without names (kept for the record-ID tests; use load_sider).

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
    out["record_id"] = _content_ids(out, "SIDER")
    return out.reset_index(drop=True)


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


def load_ddinter(paths: Union[Path, Iterable[Path]]) -> pd.DataFrame:
    """Load DDInter 2.0 bulk CSVs (one per ATC class) into one de-duplicated table.

    The 2024-05-21 bulk files have columns DDInterID_A, Drug_A, DDInterID_B,
    Drug_B, Level and NO mechanism text (mechanisms are only on the website).
    A pair can appear in several ATC files and in either order, so rows are
    oriented by DDInter ID and exact duplicates dropped. Level is kept as the
    curated severity (Major/Moderate/Minor, else Unknown). A Mechanism column is
    used if a file has one (the synthetic sample format).
    """
    paths = [paths] if isinstance(paths, (str, Path)) else list(paths)
    df = pd.concat([pd.read_csv(p, dtype=str) for p in paths], ignore_index=True)
    present = {src: dst for src, dst in DDINTER_COLUMN_MAP.items() if src in df.columns}
    df = df.rename(columns=present)
    if "ddinter_id_a" in df.columns:
        swap = df["ddinter_id_a"] > df["ddinter_id_b"]
        for x, y in (("ddinter_id_a", "ddinter_id_b"), ("drug_a_name", "drug_b_name")):
            df.loc[swap, [x, y]] = df.loc[swap, [y, x]].values
    for col in ("drug_a_name", "drug_b_name"):
        df[col] = df[col].astype(str).str.lower().str.strip()
    df["severity"] = df["severity"].fillna("Unknown").astype(str).str.strip()
    df.loc[~df["severity"].isin(["Major", "Moderate", "Minor"]), "severity"] = "Unknown"
    if "mechanism" in df.columns:
        df["condition_name"] = df["mechanism"].fillna("interaction").astype(str).str.lower()
    else:
        df["mechanism"] = None
        df["condition_name"] = "interaction"   # no event text in the bulk files
    key = [c for c in ("ddinter_id_a", "ddinter_id_b") if c in df.columns] or ["drug_a_name", "drug_b_name"]
    df = df.drop_duplicates(key + ["severity"]).sort_values(key + ["severity"])
    df["condition_id"] = None
    for col in ("drug_a_rxcui", "drug_b_rxcui", "prr", "frequency"):
        if col not in df.columns:
            df[col] = None
    df["source"] = "DDInter"
    df["record_id"] = _content_ids(df, "DDI")
    keep = [c for c in (
        "ddinter_id_a", "ddinter_id_b", "drug_a_name", "drug_b_name", "drug_a_rxcui", "drug_b_rxcui",
        "condition_name", "condition_id", "severity", "mechanism",
        "prr", "frequency", "source", "record_id",
    ) if c in df.columns]
    return df[keep].reset_index(drop=True)
