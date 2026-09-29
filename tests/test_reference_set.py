"""Reference-set scorer (src/evaluation/reference_set.py) on the synthetic sample."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.data.storage import read_table
from src.evaluation import reference_set as R
from src.graph import PharmGuardGraph, Settings

REPO_CSV = Path(__file__).resolve().parent.parent / "data" / "validation" / "reference_interactions.csv"


def _write(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=R.COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: "" for c in R.COLUMNS} | r)
    return path


def _v(a, b, expected="interaction", min_severity="", drugscom="", verified=True):
    return {"drug_a": a, "drug_b": b, "expected": expected, "min_severity": min_severity,
            "verified_source": "label" if verified else "", "verified_on": "2026-10-01" if verified else "",
            "drugscom_severity": drugscom}


@pytest.fixture(scope="module")
def graph(test_data_dir, sample_ingest_report):
    return PharmGuardGraph(Settings(data_dir=test_data_dir, mode="deterministic"))


@pytest.fixture(scope="module")
def signal_only_pair(test_data_dir, sample_ingest_report):
    df = read_table(test_data_dir / "processed" / "interactions.parquet")
    key = lambda d: {tuple(sorted(p)) for p in zip(d.drug_a_name, d.drug_b_name)}
    return sorted(key(df[df.source == "TWOSIDES"]) - key(df[df.source == "DDInter"]))[0]


def test_repo_reference_set_loads_and_is_all_unverified():
    rows = R.load(REPO_CSV)
    assert len([r for r in rows if r.expected == "interaction"]) >= 30
    assert len([r for r in rows if r.expected == "none"]) >= 10
    assert not any(r.verified or r.drugscom for r in rows)          # nothing verified yet: nothing scored
    assert R.score(rows, run=lambda d: pytest.fail("ran an unverified row"))["skipped_unverified"] == len(rows)


def test_outcomes_metrics_and_skips(graph, signal_only_pair, tmp_path):
    rows = R.load(_write(tmp_path / "ref.csv", [
        _v("lisinopril", "spironolactone", min_severity="Major", drugscom="Major"),       # DETECTED, Major
        _v("aspirin", "omeprazole", min_severity="Major", drugscom="Moderate"),           # DETECTED Moderate: under-triage
        _v(*signal_only_pair),                                                            # LISTED_UNGRADED
        _v("metformin", "levothyroxine", drugscom="none"),                                # NO_DATA
        _v("fictional_drug_xyz", "warfarin"),                                             # UNRESOLVED
        _v("warfarin", "aspirin", expected="none", drugscom="Major"),                     # negative control, DETECTED
        _v("warfarin", "aspirin", verified=False),                                        # skipped
    ]))
    r = R.score(rows, graph.run)
    assert (r["rows"], r["scored"], r["skipped_unverified"]) == (7, 6, 1)
    assert r["outcomes_positives"] == {"DETECTED": 2, "LISTED_UNGRADED": 1, "NO_DATA": 1, "UNRESOLVED": 1, "SILENT": 0}
    assert r["outcomes_negative_controls"]["DETECTED"] == 1
    assert (r["recall_graded"], r["recall_including_ungraded"]) == (0.4, 0.6)
    assert r["under_triage"] == {"count": 1, "of_detected": 2, "rate": 0.5, "pairs": [["aspirin", "omeprazole"]]}
    assert r["silent"] == 0
    # PharmGuard vs Drugs.com: Major/Major, Moderate/Moderate, none/none, Major/Major -> all agree
    a = r["drugscom_agreement"]
    assert (a["rows"], a["exact"], a["linear_weighted_kappa"]) == (4, 1.0, 1.0)


def test_silent_is_detected_from_the_state():
    state = {"resolved": [{"generic_name": "a", "resolved": True}, {"generic_name": "b", "resolved": True}],
             "retrieval": {"interactions": [], "no_data_pairs": [["a", "b"]]}, "report": "## Summary\n"}
    assert R.outcome(state)["outcome"] == "SILENT"


def test_linear_kappa_by_hand():
    # levels none<Minor<Moderate<Major; weights 1, 2/3, 1/3, 0
    # pairs: (Major,Major) (Moderate,Major) (none,none) (Minor,Moderate)
    # po = (1 + 2/3 + 1 + 2/3) / 4 = 0.8333; rows: none1 Minor1 Mod1 Maj1; cols: none1 Mod1 Maj2
    a, b = ["Major", "Moderate", "none", "Minor"], ["Major", "Major", "none", "Moderate"]
    w = lambda i, j: 1 - abs(i - j) / 3
    rows, cols = [1, 1, 1, 1], [1, 0, 1, 2]
    pe = sum(w(i, j) * rows[i] * cols[j] for i in range(4) for j in range(4)) / 16
    assert R._kappa_linear(a, b) == round((10 / 12 - pe) / (1 - pe), 4)


def test_bad_rows_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="expected"):
        R.load(_write(tmp_path / "a.csv", [_v("a", "b", expected="maybe")]))
    with pytest.raises(ValueError, match="unknown severity"):
        R.load(_write(tmp_path / "b.csv", [_v("a", "b", drugscom="severe")]))
    (tmp_path / "c.csv").write_text("drug_a,drug_b\nx,y\n")
    with pytest.raises(ValueError, match="columns"):
        R.load(tmp_path / "c.csv")
