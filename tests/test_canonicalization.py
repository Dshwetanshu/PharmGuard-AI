"""Canonical drug keys: the normalizer and every data table must agree."""
from __future__ import annotations

import pandas as pd

from src.data.canonical import (
    build_alias_map,
    canonicalize_columns,
    ensure_self_aliases,
    find_join_integrity_issues,
)


def _vocab(rows):
    return pd.DataFrame(rows, columns=["name_lower", "generic_name", "rxcui", "drugbank_id"])


def test_lithium_hydrochlorothiazide_major_interaction_is_retrieved(sample_pipeline):
    # Regression: vocab maps lithium -> "lithium carbonate" while the tables used
    # "lithium", so this Major pair was reported as "no data".
    result = sample_pipeline.run(["lithium", "hydrochlorothiazide"], use_llm=False)
    assert result.retrieval.no_data_pairs == []
    records = [r for recs in result.retrieval.interactions.values() for r in recs]
    assert {r.record_id for r in records} >= {"TS-00000031", "DDI-00000016"}
    assert any(r.severity == "Major" for r in records)


def test_sample_ingest_has_no_join_integrity_issues(sample_ingest_report):
    assert sample_ingest_report["join_integrity"]["issues"] == []


def test_every_generic_resolves_to_itself(sample_pipeline):
    vocab = pd.read_parquet(sample_pipeline.cfg.paths.processed_dir / "drug_vocabulary.parquet")
    for generic in vocab["generic_name"].unique():
        r = sample_pipeline.normalizer.resolve(generic)
        assert (r.method, r.generic_name) == ("exact", generic)


def test_integrity_check_reports_names_missing_from_vocab():
    alias = build_alias_map(_vocab([["lithium", "lithium carbonate", "42351", None]]))
    df = pd.DataFrame({"drug_a_name": ["lithium", "zzz"], "drug_b_name": ["lithium carbonate", "lithium carbonate"]})
    issues = find_join_integrity_issues({"interactions": (df, ["drug_a_name", "drug_b_name"])}, alias)
    # "lithium" is an alias (not canonical); "zzz" is unknown; "lithium carbonate"
    # is canonical but only resolves to itself once self-aliases are ensured.
    assert {(i.name, i.resolves_to) for i in issues} == {
        ("lithium", "lithium carbonate"), ("zzz", None), ("lithium carbonate", None),
    }


def test_canonicalization_uses_vocab_not_string_rules():
    vocab = ensure_self_aliases(_vocab([
        ["lithium", "lithium carbonate", "42351", None],
        ["potassium chloride", "potassium chloride", "8591", None],
        ["sodium bicarbonate", "sodium bicarbonate", "36676", None],
    ]))
    alias = build_alias_map(vocab)
    df = pd.DataFrame({"drug_name": ["lithium", "potassium chloride", "sodium bicarbonate", "unknown drug"]})
    out = canonicalize_columns(df, ["drug_name"], alias)
    # Salts that are active ingredients stay intact; unknown names are left
    # unchanged so the integrity check can report them.
    assert out["drug_name"].tolist() == ["lithium carbonate", "potassium chloride", "sodium bicarbonate", "unknown drug"]
    assert find_join_integrity_issues({"se": (out, ["drug_name"])}, alias)[0].name == "unknown drug"
