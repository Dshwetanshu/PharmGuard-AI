"""Severity agreement metrics, checked against values computed by hand."""
from __future__ import annotations

import pandas as pd
import pytest

from src.evaluation import severity_agreement as S

TRUTH = ["Minor", "Moderate", "Major", "Major"]
PRED = ["Minor", "Major", "Major", "Moderate"]


def test_confusion_and_accuracy():
    m = S.confusion(TRUTH, PRED)
    assert m == [[1, 0, 0], [0, 0, 1], [0, 1, 1]]
    assert S.accuracy(m) == 0.5


def test_macro_f1():
    # F1: Minor 1.0, Moderate 0.0, Major 2*1/(2+2) = 0.5
    assert S.macro_f1(S.confusion(TRUTH, PRED)) == pytest.approx(0.5)


def test_linear_weighted_kappa():
    # po = (2 + 0.5*2) / 4 = 0.75; pe = 9/16; kappa = 0.1875 / 0.4375
    assert S.linear_weighted_kappa(S.confusion(TRUTH, PRED)) == pytest.approx(0.1875 / 0.4375)
    assert S.linear_weighted_kappa(S.confusion(TRUTH, TRUTH)) == pytest.approx(1.0)


def test_spearman_with_ties():
    # ranks [1, 3.5, 3.5, 2] vs [1, 2, 3.5, 3.5] -> 2.25 / 4.5
    pred = [S.ORD[p] for p in PRED]
    truth = [S.ORD[t] for t in TRUTH]
    assert S.spearman(pred, truth) == pytest.approx(0.5)
    assert S.spearman([1, 1, 1], [1, 2, 3]) is None


def test_tier_boundaries_match_the_loader():
    from src.data.loaders import _prr_to_severity
    for prr in (2.0, 3.99, 4.0, 9.99, 10.0, 55.0):
        assert S.tier(prr, S.CURRENT_THRESHOLDS) == _prr_to_severity(prr)


def test_tune_finds_a_separating_pair_and_keeps_the_first_best():
    th, k = S.tune([1, 5, 20], ["Minor", "Moderate", "Major"], [20, 1, 5, 3, 12])
    assert (th, k) == ((3, 12), pytest.approx(1.0))


def test_pair_table_uses_max_prr_and_the_most_severe_grade():
    df = pd.DataFrame([
        ("b", "a", "Moderate", None, "DDInter"), ("a", "b", "Major", None, "DDInter"),
        ("a", "b", "Major", 12.0, "TWOSIDES"), ("b", "a", "Moderate", 30.0, "TWOSIDES"),
        ("c", "d", "Unknown", None, "DDInter"), ("c", "d", "Minor", 3.0, "TWOSIDES"),
        ("e", "f", "Minor", None, "DDInter"),
    ], columns=["drug_a_name", "drug_b_name", "severity", "prr", "source"])
    pairs, counts = S.pair_table(df)
    assert pairs[["a", "b", "severity", "max_prr"]].values.tolist() == [["a", "b", "Major", 30.0]]
    assert counts == {"ddinter_pairs": 3, "twosides_pairs": 2, "overlap_pairs": 2,
                      "overlap_graded": 1, "overlap_not_graded": 1}


def test_split_is_seeded_and_disjoint():
    pairs = pd.DataFrame({"a": [str(i) for i in range(11)]})
    cal, test = S.split(pairs, seed=5)
    assert len(cal) == 5 and len(test) == 6 and not set(cal.a) & set(test.a)
    assert S.split(pairs, seed=5)[0].a.tolist() == cal.a.tolist()
