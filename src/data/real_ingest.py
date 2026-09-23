"""Real-data ingestion: data/raw/ -> data/profiles/<profile>/processed/.

Profiles (src/data/sources.py):
- "public":   RxNorm Current Prescribable + DrugBank vocabulary (if given) + DDInter 2.0 + SIDER 4.1
- "research": public + TWOSIDES (no stated license; local evaluation only, never published)

Every source's drug names are mapped onto the RxNorm canonical vocabulary by exact
alias. Rows whose drugs don't map are excluded from the tables but never silently:
each source gets a match rate and data/profiles/<profile>/processed/unmatched_<source>.csv.
provenance.json records URL, version, download date, sha256, row counts, filters,
profile and unmatched counts per source.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from src.data.canonical import build_alias_map, ensure_self_aliases, find_join_integrity_issues
from src.data.loaders import load_ddinter, load_drugbank_vocabulary, load_sider, load_twosides_filtered
from src.data.provenance import write_real_provenance
from src.data.rxnorm import REVIEWED_ALIASES, SALT_GROUPS, build_rxnorm_vocabulary, merge_drugbank_synonyms
from src.data.sources import PROFILES
from src.data.storage import write_table

INTERACTION_COLUMNS = ["drug_a_name", "drug_b_name", "drug_a_rxcui", "drug_b_rxcui", "condition_id",
                       "condition_name", "severity", "mechanism", "prr", "reports", "frequency", "source",
                       "record_id"]


def _find(raw: Path, *patterns: str) -> Optional[Path]:
    for pat in patterns:
        hits = sorted(raw.glob(pat))
        if hits:
            return hits[0]
    return None


def _unmatched_report(key: str, names: pd.Series, rows_per_name: Dict[str, int], out_dir: Path,
                      rows_in: int, rows_kept: int) -> dict:
    """Per-source integrity: name match rate, row retention, CSV of unmatched names."""
    distinct = names.nunique()
    unmatched = pd.DataFrame(sorted(rows_per_name.items(), key=lambda x: (-x[1], x[0])),
                             columns=["name", "rows_affected"])
    path = out_dir / f"unmatched_{key}.csv"
    unmatched.to_csv(path, index=False)
    matched = distinct - len(unmatched)
    return {"distinct_names": int(distinct), "matched_names": int(matched),
            "name_match_rate": round(matched / distinct, 4) if distinct else None,
            "rows_in": int(rows_in), "rows_kept": int(rows_kept),
            "row_retention": round(rows_kept / rows_in, 4) if rows_in else None,
            "unmatched_names": int(len(unmatched)), "unmatched_file": path.name,
            "top_unmatched": unmatched.head(15).values.tolist()}


def _canonical_pairs(df: pd.DataFrame, alias: Dict[str, str]):
    ga, gb = df["drug_a_name"].map(alias), df["drug_b_name"].map(alias)
    return ga, gb


def ingest_real(raw_dir: Path, out_dir: Path, profile: str, drugbank_csv: Optional[Path] = None) -> dict:
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {PROFILES}")
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    processed = out_dir / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    report: Dict[str, dict] = {"profile": profile, "timings_s": {}}
    t_all = time.perf_counter()

    # ---- vocabulary
    t = time.perf_counter()
    rx_src = _find(raw_dir, "rxnorm/*.zip") or (raw_dir / "rxnorm")
    vocab = build_rxnorm_vocabulary(rx_src)
    aliases = vocab.aliases
    extra: Dict[str, int] = {}
    if drugbank_csv:
        aliases, extra = merge_drugbank_synonyms(vocab, load_drugbank_vocabulary(Path(drugbank_csv)))
    aliases = ensure_self_aliases(aliases)
    write_table(aliases, processed / "drug_vocabulary.parquet")
    write_table(vocab.combinations, processed / "combination_products.parquet")
    alias = build_alias_map(aliases)
    report["vocabulary"] = {**vocab.stats, **extra, "rows": len(aliases),
                            "salt_groups": dict(SALT_GROUPS), "reviewed_aliases": dict(REVIEWED_ALIASES),
                            "drugbank": "merged" if drugbank_csv else "not available (DrugBank downloads paused)"}
    report["timings_s"]["vocabulary"] = round(time.perf_counter() - t, 1)

    frames, sources = [], {}

    # ---- DDInter (curated severity)
    t = time.perf_counter()
    dd = load_ddinter(sorted(raw_dir.glob("ddinter/*.csv")))
    ga, gb = _canonical_pairs(dd, alias)
    miss = ga.isna() | gb.isna()
    per_name: Dict[str, int] = {}
    for side, g in (("a", ga), ("b", gb)):
        for n, k in dd.loc[g.isna(), f"drug_{side}_name"].value_counts().items():
            per_name[n] = per_name.get(n, 0) + int(k)
    kept = dd[~miss].assign(drug_a_name=ga[~miss], drug_b_name=gb[~miss])
    self_pairs = kept.drug_a_name == kept.drug_b_name
    kept = kept[~self_pairs]
    swap = kept.drug_a_name > kept.drug_b_name
    kept.loc[swap, ["drug_a_name", "drug_b_name"]] = kept.loc[swap, ["drug_b_name", "drug_a_name"]].values
    before = len(kept)
    kept = kept.drop_duplicates(["drug_a_name", "drug_b_name", "severity"])
    names = pd.concat([dd.drug_a_name, dd.drug_b_name])
    sources["ddinter"] = {**_unmatched_report("ddinter", names, per_name, processed, len(dd), len(kept)),
                          "self_pairs_after_mapping": int(self_pairs.sum()),
                          "merged_duplicates_after_mapping": before - len(kept),
                          "filters": {"dedupe": "DDInter ID pair across the 8 ATC files; then canonical pair + level"},
                          "mechanism_text": "none in the bulk files"}
    frames.append(kept.assign(reports=None))
    report["timings_s"]["ddinter"] = round(time.perf_counter() - t, 1)

    # ---- TWOSIDES (research only)
    tw_path = _find(raw_dir, "twosides/TWOSIDES.csv.xz", "twosides/TWOSIDES.csv.gz", "twosides/TWOSIDES.csv")
    if profile == "research":
        if tw_path is None:
            raise FileNotFoundError("research profile needs TWOSIDES: python scripts/fetch_data.py --with-twosides")
        t = time.perf_counter()
        tw, st = load_twosides_filtered(tw_path, alias, vocab.rxcui_to_generic)
        seen = st["distinct_names_seen"]
        sources["twosides"] = {"distinct_names": seen, "matched_names": st["distinct_names_matched"],
                               "name_match_rate": round(st["distinct_names_matched"] / seen, 4) if seen else None,
                               "rows_in": st["rows_read"], "rows_kept": st["rows_kept"],
                               "row_retention": round(st["rows_kept"] / st["rows_read"], 4) if st["rows_read"] else None,
                               "unmatched_names": len(st["unmatched_names"]), "unmatched_file": "unmatched_twosides.csv",
                               "top_unmatched": sorted(st["unmatched_names"].items(), key=lambda x: -x[1])[:15],
                               "pairs_kept": st["pairs_kept"], "filters": st["filters"],
                               "dropped": {k: st[k] for k in st if k.startswith("dropped_")},
                               "scope": "research only: no stated license; not redistributed"}
        pd.DataFrame(sorted(st["unmatched_names"].items(), key=lambda x: (-x[1], x[0])),
                     columns=["name", "rows_affected"]).to_csv(processed / "unmatched_twosides.csv", index=False)
        frames.append(tw)
        report["timings_s"]["twosides"] = round(time.perf_counter() - t, 1)

    interactions = pd.concat([f.reindex(columns=INTERACTION_COLUMNS) for f in frames], ignore_index=True)
    write_table(interactions, processed / "interactions.parquet")

    # ---- SIDER (side effects)
    t = time.perf_counter()
    se_raw = load_sider(raw_dir / "sider" / "meddra_all_se.tsv.gz", raw_dir / "sider" / "drug_names.tsv")
    g = se_raw.drug_name.map(alias)
    per_name = {n: int(k) for n, k in se_raw.loc[g.isna(), "drug_name"].fillna("(no name)").value_counts().items()}
    se = se_raw[g.notna()].assign(drug_name=g[g.notna()]).drop_duplicates(["drug_name", "side_effect_name"])
    sources["sider"] = {**_unmatched_report("sider", se_raw.drug_name.fillna("(no name)"), per_name, processed,
                                            len(se_raw), len(se)),
                        "filters": {"meddra_type": "PT", "dedupe": "canonical drug + side effect"}}
    write_table(se[["drug_name", "side_effect_name", "umls_cui", "source", "record_id"]],
                processed / "side_effects.parquet")
    report["timings_s"]["sider"] = round(time.perf_counter() - t, 1)

    # ---- join integrity on the written tables (every name must resolve to itself)
    issues = find_join_integrity_issues({"interactions": (interactions, ("drug_a_name", "drug_b_name")),
                                         "side_effects": (se, ("drug_name",))}, alias)
    report["join_integrity"] = {"checked": True, "issues": [i.__dict__ for i in issues]}
    report["sources"] = sources
    report["interactions"] = {"rows": len(interactions),
                              "by_source": interactions.groupby("source").size().to_dict()}
    report["side_effects"] = {"rows": len(se)}
    report["timings_s"]["total"] = round(time.perf_counter() - t_all, 1)
    report["provenance"] = str(write_real_provenance(processed, profile, manifest, report))
    return report
