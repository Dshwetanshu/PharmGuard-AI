"""Pharmacist review scoring (src/evaluation/pharmacist.py) and the exported rubric's shape."""
from __future__ import annotations

import csv
from pathlib import Path

from src.evaluation.pharmacist import score_ab, score_rubric

ROOT = Path(__file__).resolve().parent.parent
RUBRIC = ROOT / "data" / "validation" / "pharmacist" / "rubric.csv"


def _csv(path, fields, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return path


def test_exported_rubric_is_blank_with_ten_cases():
    rows = list(csv.DictReader(RUBRIC.open()))
    assert [r["case_id"] for r in rows] == [f"PR-{i:02d}" for i in range(1, 11)]
    assert list(rows[0]) == ["case_id", "report", "reviewer", "accuracy", "useful", "would_recommend",
                             "missed_or_wrong", "comments"]
    assert all(not r["accuracy"] and not r["useful"] for r in rows)
    assert score_rubric(RUBRIC)["rows_scored"] == 0


def test_rubric_scoring(tmp_path):
    f = ["case_id", "reviewer", "accuracy", "useful", "would_recommend", "comments"]
    p = _csv(tmp_path / "r.csv", f, [
        {"case_id": "PR-01", "reviewer": "RPh1", "accuracy": "Accurate", "useful": "yes", "would_recommend": "y"},
        {"case_id": "PR-02", "reviewer": "RPh1", "accuracy": "partly  accurate", "useful": "y", "would_recommend": "n"},
        {"case_id": "PR-03", "reviewer": "RPh1", "accuracy": "inaccurate", "useful": "n", "would_recommend": "n"},
        {"case_id": "PR-04", "reviewer": "RPh1", "accuracy": "accurate", "useful": "y", "would_recommend": "y"},
        {"case_id": "PR-05", "reviewer": "", "accuracy": "", "useful": "", "would_recommend": ""},
        {"case_id": "PR-06", "reviewer": "RPh1", "accuracy": "great", "useful": "y", "would_recommend": "y"},
    ])
    s = score_rubric(p)
    assert (s["reviewers"], s["rows_scored"], s["rows_blank"], s["rows_invalid"]) == (1, 4, 1, ["PR-06"])
    assert s["accuracy"] == {"accurate": 2, "partly accurate": 1, "inaccurate": 1}
    assert (s["accurate_rate"], s["useful_rate"], s["would_recommend_rate"]) == (0.5, 0.75, 0.5)


def test_ab_is_unblinded_with_the_key(tmp_path):
    f = ["case_id", "reviewer", "accuracy_A", "accuracy_B", "useful_A", "useful_B", "preferred", "comments"]
    p = _csv(tmp_path / "ab.csv", f, [
        {"case_id": "PR-01", "accuracy_A": "accurate", "accuracy_B": "inaccurate", "useful_A": "y", "useful_B": "n",
         "preferred": "A"},
        {"case_id": "PR-02", "accuracy_A": "partly accurate", "accuracy_B": "accurate", "useful_A": "y",
         "useful_B": "y", "preferred": "b"},
        {"case_id": "PR-03", "preferred": "none"},
    ])
    key = {"PR-01": {"A": "template", "B": "llm (llm)"}, "PR-02": {"A": "llm (llm_retry)", "B": "template"},
           "PR-03": {"A": "template", "B": "llm (llm)"}}
    s = score_ab(p, key)
    assert s["cases_scored"] == 2
    assert s["arms"]["template"]["accuracy"] == {"accurate": 2, "partly accurate": 0, "inaccurate": 0}
    assert s["arms"]["llm"]["accuracy"] == {"accurate": 0, "partly accurate": 1, "inaccurate": 1}
    assert s["preferred"] == {"template": 2, "no preference": 1}
