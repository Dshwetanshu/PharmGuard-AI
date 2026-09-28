"""Holdout graceful-degradation test (src/evaluation/holdout.py) on the synthetic sample."""
from __future__ import annotations

import pandas as pd
import pytest

from src.data.storage import read_table, write_table
from src.evaluation.holdout import (
    classify, ddinter_pairs, run_holdout, select_holdout, write_holdout_build,
)
from src.graph import PharmGuardGraph, Settings


@pytest.fixture(scope="module")
def processed(test_data_dir, sample_ingest_report):
    return test_data_dir / "processed"


def _graph(data_dir):
    return PharmGuardGraph(Settings(data_dir=data_dir, mode="deterministic"))


def test_selection_is_seeded_sized_and_by_pair():
    pairs = [(f"a{i}", f"b{i}") for i in range(200)]
    first = select_holdout(pairs, 0.1, seed=3)
    assert first == select_holdout(list(reversed(pairs)), 0.1, seed=3)
    assert len(first) == 20 and len(set(first)) == 20
    assert first != select_holdout(pairs, 0.1, seed=4)
    with pytest.raises(ValueError):
        select_holdout(pairs, 1.0, seed=3)


def test_ddinter_pairs_keep_the_most_severe_grade():
    df = pd.DataFrame({"drug_a_name": ["b", "a", "c"], "drug_b_name": ["a", "b", "d"],
                       "severity": ["Minor", "Major", "Unknown"], "source": ["DDInter", "DDInter", "TWOSIDES"]})
    assert ddinter_pairs(df) == {("a", "b"): "Major"}


def test_holdout_build_drops_only_the_held_ddinter_rows(processed, tmp_path):
    inter = read_table(processed / "interactions.parquet")
    grades = ddinter_pairs(inter)
    held = select_holdout(grades, 0.2, seed=1)
    dst = write_holdout_build(processed, tmp_path, held)
    out = read_table(dst / "interactions.parquet")
    key = lambda df: {tuple(sorted(p)) for p in zip(df.drug_a_name, df.drug_b_name)}
    assert not key(out[out.source == "DDInter"]) & set(held)
    assert len(out[out.source != "DDInter"]) == len(inter[inter.source != "DDInter"])
    assert len(inter) - len(out) == sum(tuple(sorted(p)) in set(held) for p in
                                        zip(inter[inter.source == "DDInter"].drug_a_name,
                                            inter[inter.source == "DDInter"].drug_b_name))
    assert (dst / "drug_vocabulary.parquet").exists() and (dst / "provenance.json").exists()


def test_sample_holdout_recovers_from_twosides_and_is_never_silent(processed, tmp_path):
    inter = read_table(processed / "interactions.parquet")
    grades = ddinter_pairs(inter)
    held = select_holdout(grades, 0.2, seed=1)
    write_holdout_build(processed, tmp_path, held)
    r = run_holdout(_graph(tmp_path), held, grades)
    assert r["outcomes"]["silent"] == 0 and r["ddinter_leaks"] == 0
    assert r["outcomes"]["recovered"] == len(held)          # every sample DDInter pair also has TWOSIDES rows
    assert set(r["recovered_by_source"]) == {"TWOSIDES"}


def test_ddinter_only_build_declares_every_held_out_pair(processed, tmp_path):
    """Like the public build (DDInter only): a held-out pair has nowhere to recover from."""
    src = tmp_path / "src" / "processed"
    write_holdout_build(processed, tmp_path / "src", [])
    inter = read_table(src / "interactions.parquet")
    write_table(inter[inter.source == "DDInter"].reset_index(drop=True), src / "interactions.parquet")
    grades = ddinter_pairs(inter)
    held = select_holdout(grades, 0.2, seed=1)
    write_holdout_build(src, tmp_path / "held", held)
    r = run_holdout(_graph(tmp_path / "held"), held, grades)
    assert r["outcomes"]["declared_no_data"] == len(held) and r["outcomes"]["silent"] == 0


def _state(report, no_data=(), interactions=(), passed=True, resolved=("a", "b")):
    return {"resolved": [{"generic_name": g, "resolved": True} for g in resolved],
            "retrieval": {"interactions": list(interactions), "no_data_pairs": [list(p) for p in no_data]},
            "report": report, "final_validation": {"passed": passed}}


def test_classify_needs_the_declaration_in_the_report_text():
    declared = "## Coverage Notes\n### No Curated Interaction Data\nNo record.\n- a + b\n"
    assert classify(_state(declared, no_data=[("a", "b")]), ("a", "b"))[0] == "declared_no_data"
    # In the state's no-data list but missing from the text: silent.
    assert classify(_state("## Coverage Notes\n", no_data=[("a", "b")]), ("a", "b"))[0] == "silent"
    # Named, but outside the no-data section: silent.
    assert classify(_state("## Summary\n- a + b\n", no_data=[("a", "b")]), ("a", "b"))[0] == "silent"
    assert classify(_state(declared, no_data=[("a", "b")], passed=False), ("a", "b"))[0] == "silent"
    assert classify(_state(""), ("a", "b"))[0] == "silent"


def test_classify_recovered_and_unresolved():
    rec = [{"pair": ["a", "b"], "records": [{"source": "TWOSIDES"}]}]
    assert classify(_state("", interactions=rec), ("a", "b")) == ("recovered", ["TWOSIDES"])
    assert classify(_state("", resolved=("a",)), ("a", "b"))[0] == "unresolved"
