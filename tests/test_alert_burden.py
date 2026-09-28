"""Alert-burden summary (src/evaluation/alert_burden.py)."""
from __future__ import annotations

from src.evaluation.alert_burden import counts, summarize
from src.graph import PharmGuardGraph, Settings


def _s(major=0, moderate=0, minor=0, ungraded=0, signals=0, hidden=0, no_data=0, unresolved=0, pairs=1):
    return {"summary": {"pairs": pairs, "graded": {"Major": major, "Moderate": moderate, "Minor": minor},
                        "ungraded": ungraded, "signals": signals, "hidden_signals": hidden,
                        "no_data_pairs": no_data, "unresolved": unresolved}}


def test_summary_totals_shares_and_medians():
    rows = [counts(_s(major=2, ungraded=2, pairs=3)), counts(_s(minor=1, signals=3, hidden=4, pairs=3)),
            counts(_s(no_data=1, unresolved=1))]
    s = summarize(rows)
    assert s["totals"]["graded"] == 3 and s["items_shown"] == 8
    assert s["share_of_items"] == {"graded": 0.375, "ungraded": 0.25, "signals": 0.375}
    assert s["major_share_of_items"] == 0.25
    assert s["median_per_report"]["graded"] == 1 and s["max_per_report"]["signals"] == 3
    assert (s["reports_with_a_major"], s["reports_with_nothing_graded"]) == (1, 1)


def test_empty_summary_has_no_shares():
    assert summarize([])["share_of_items"] == {"graded": None, "ungraded": None, "signals": None}


def test_counts_match_the_markdown_summary_line(test_data_dir, sample_ingest_report):
    g = PharmGuardGraph(Settings(data_dir=test_data_dir, mode="deterministic"))
    s = g.run(["lisinopril", "spironolactone", "aspirin", "fictional_drug_xyz"])
    c = counts(s["report_structure"])
    assert f"Found {c['graded']} graded interaction" in s["report"]
    assert c["unresolved"] == 1
