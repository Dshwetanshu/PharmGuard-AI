"""Agreement between PRR-derived tiers (TWOSIDES) and DDInter's curated grades.

Grades are ordinal: Minor < Moderate < Major. The pair-level PRR is the highest PRR
among the pair's kept TWOSIDES events; the tier comes from thresholds on it
(src/data/loaders.py::_prr_to_severity uses PRR >= 4 Moderate, >= 10 Major).
Only DDInter pairs with a grade are scored; "not graded" pairs are counted apart.
"""
from __future__ import annotations

import random
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

GRADES = ("Minor", "Moderate", "Major")
ORD = {g: i for i, g in enumerate(GRADES)}
CURRENT_THRESHOLDS = (4.0, 10.0)      # (Moderate from, Major from); the loader's values


def tier(prr: float, thresholds: Tuple[float, float]) -> str:
    moderate, major = thresholds
    return "Major" if prr >= major else "Moderate" if prr >= moderate else "Minor"


def confusion(truth: Sequence[str], pred: Sequence[str]) -> List[List[int]]:
    """Rows = truth (DDInter), columns = prediction (PRR tier), both in GRADES order."""
    m = [[0] * len(GRADES) for _ in GRADES]
    for t, p in zip(truth, pred):
        m[ORD[t]][ORD[p]] += 1
    return m


def accuracy(m: List[List[int]]) -> Optional[float]:
    n = sum(map(sum, m))
    return sum(m[i][i] for i in range(len(m))) / n if n else None


def macro_f1(m: List[List[int]]) -> Optional[float]:
    """Mean F1 over the classes that occur in the truth or the predictions."""
    k = len(m)
    scores = []
    for c in range(k):
        tp = m[c][c]
        pred_c = sum(m[r][c] for r in range(k))
        true_c = sum(m[c])
        if pred_c == 0 and true_c == 0:
            continue
        scores.append(2 * tp / (pred_c + true_c))
    return sum(scores) / len(scores) if scores else None


def linear_weighted_kappa(m: List[List[int]]) -> Optional[float]:
    k, n = len(m), sum(map(sum, m))
    if not n:
        return None
    rows = [sum(r) for r in m]
    cols = [sum(m[r][c] for r in range(k)) for c in range(k)]
    w = lambda i, j: 1 - abs(i - j) / (k - 1)
    po = sum(w(i, j) * m[i][j] for i in range(k) for j in range(k)) / n
    pe = sum(w(i, j) * rows[i] * cols[j] for i in range(k) for j in range(k)) / n / n
    return (po - pe) / (1 - pe) if pe != 1 else None


def spearman(x: Iterable[float], y: Iterable[float]) -> Optional[float]:
    """Spearman's rho with average ranks for ties (Pearson correlation of the ranks)."""
    rx, ry = pd.Series(list(x)).rank(), pd.Series(list(y)).rank()
    if len(rx) < 2 or rx.std() == 0 or ry.std() == 0:
        return None
    return float(rx.corr(ry))


def scores(truth: Sequence[str], pred: Sequence[str], prr: Sequence[float]) -> dict:
    m = confusion(truth, pred)
    r = lambda v: None if v is None else round(v, 4)
    return {"n": len(truth), "accuracy": r(accuracy(m)), "macro_f1": r(macro_f1(m)),
            "linear_weighted_kappa": r(linear_weighted_kappa(m)),
            "spearman_tier": r(spearman([ORD[p] for p in pred], [ORD[t] for t in truth])),
            "spearman_prr": r(spearman(prr, [ORD[t] for t in truth])),
            "confusion": {"rows_ddinter": list(GRADES), "cols_prr_tier": list(GRADES), "counts": m}}


def pair_table(interactions: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """One row per pair with both a DDInter record and a TWOSIDES signal: grade and max PRR."""
    df = interactions.assign(a=interactions[["drug_a_name", "drug_b_name"]].min(axis=1),
                             b=interactions[["drug_a_name", "drug_b_name"]].max(axis=1))
    tw = df[df.source == "TWOSIDES"].groupby(["a", "b"]).prr.max().rename("max_prr")
    dd = df[df.source == "DDInter"].copy()
    dd["rank"] = dd.severity.map(ORD).fillna(-1)
    dd = dd.sort_values("rank").groupby(["a", "b"]).tail(1).set_index(["a", "b"])[["severity"]]
    both = dd.join(tw, how="inner")
    graded = both[both.severity.isin(GRADES)].reset_index()
    counts = {"ddinter_pairs": len(dd), "twosides_pairs": len(tw), "overlap_pairs": len(both),
              "overlap_graded": len(graded), "overlap_not_graded": len(both) - len(graded)}
    return graded, counts


def split(pairs: pd.DataFrame, seed: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Seeded 50/50 split by pair (calibration, test)."""
    idx = list(range(len(pairs)))
    random.Random(seed).shuffle(idx)
    half = len(idx) // 2
    return pairs.iloc[sorted(idx[:half])], pairs.iloc[sorted(idx[half:])]


def tune(prr: Sequence[float], truth: Sequence[str], candidates: Sequence[float]) -> Tuple[Tuple[float, float], float]:
    """Thresholds (moderate < major) maximizing linear-weighted kappa on the given (calibration) data."""
    best, best_k = CURRENT_THRESHOLDS, float("-inf")
    cands = sorted(set(candidates))
    for i, lo in enumerate(cands):
        for hi in cands[i + 1:]:
            k = linear_weighted_kappa(confusion(truth, [tier(p, (lo, hi)) for p in prr]))
            if k is not None and k > best_k:
                best, best_k = (lo, hi), k
    return best, best_k


def evaluate(interactions: pd.DataFrame, seed: int, n_candidates: int = 60) -> Dict:
    pairs, counts = pair_table(interactions)
    cal, test = split(pairs, seed)
    qs = [i / n_candidates for i in range(1, n_candidates)]
    candidates = sorted(set(round(float(q), 2) for q in cal.max_prr.quantile(qs)))
    tuned, cal_kappa = tune(list(cal.max_prr), list(cal.severity), candidates)
    majority = cal.severity.value_counts().idxmax()

    def on(df, th):
        return scores(list(df.severity), [tier(p, th) for p in df.max_prr], list(df.max_prr))

    return {"counts": counts, "seed": seed, "split": {"calibration": len(cal), "test": len(test)},
            "pair_prr": "highest PRR among the pair's kept TWOSIDES events",
            "tuning": {"objective": "linear-weighted kappa on the calibration half",
                       "candidates": f"{len(candidates)} calibration-half PRR quantiles",
                       "tuned_thresholds": {"moderate_from": tuned[0], "major_from": tuned[1]},
                       "calibration_kappa": round(cal_kappa, 4)},
            "current_thresholds": {"moderate_from": CURRENT_THRESHOLDS[0], "major_from": CURRENT_THRESHOLDS[1]},
            "test": {"current": on(test, CURRENT_THRESHOLDS), "tuned": on(test, tuned),
                     "majority_class": {"class": majority,
                                        **scores(list(test.severity), [majority] * len(test), list(test.max_prr))}},
            "calibration": {"current": on(cal, CURRENT_THRESHOLDS), "tuned": on(cal, tuned)},
            "ddinter_grade_share_test": {g: int((test.severity == g).sum()) for g in GRADES}}
