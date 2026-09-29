"""Scoring the pharmacist review (docs/PHARMACIST_REVIEW_PROTOCOL.md).

rubric.csv: one row per case and reviewer; accuracy is accurate / partly accurate /
inaccurate; useful and would_recommend are y / n. Blank rows are counted, not scored.
rubric_ab.csv + the key: the same per report A and B, unblinded with the key into
template vs LLM, plus which one the reviewer preferred.
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

ACCURACY = ("accurate", "partly accurate", "inaccurate")
YN = ("y", "n")


def _norm(v: Optional[str]) -> str:
    return " ".join((v or "").strip().lower().split())


def _yn(v: str) -> Optional[str]:
    v = _norm(v)
    return {"yes": "y", "no": "n"}.get(v, v) if v else None


def _rate(c: Counter, k: str) -> Optional[float]:
    n = sum(c.values())
    return round(c[k] / n, 4) if n else None


def score_rubric(path: Path) -> Dict[str, Any]:
    acc, useful, rec, reviewers, invalid, blank = Counter(), Counter(), Counter(), set(), [], 0
    with Path(path).open(newline="") as f:
        for row in csv.DictReader(f):
            a, u, r = _norm(row.get("accuracy")), _yn(row.get("useful")), _yn(row.get("would_recommend"))
            if not (a or u or r):
                blank += 1
                continue
            if (a and a not in ACCURACY) or (u and u not in YN) or (r and r not in YN):
                invalid.append(row.get("case_id"))
                continue
            reviewers.add(_norm(row.get("reviewer")) or "(unnamed)")
            if a:
                acc[a] += 1
            if u:
                useful[u] += 1
            if r:
                rec[r] += 1
    return {"reviewers": len(reviewers), "rows_scored": sum(acc.values()), "rows_blank": blank,
            "rows_invalid": invalid, "accuracy": {k: acc[k] for k in ACCURACY},
            "accurate_rate": _rate(acc, "accurate"), "useful_rate": _rate(useful, "y"),
            "would_recommend_rate": _rate(rec, "y")}


def score_ab(path: Path, key: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """Per arm (template / llm): accuracy and usefulness; preferences unblinded with the key."""
    arms: Dict[str, Dict[str, Counter]] = {}
    prefs, scored = Counter(), 0
    with Path(path).open(newline="") as f:
        for row in csv.DictReader(f):
            k = key.get(row["case_id"])
            if not k:
                continue
            filled = False
            for side in ("A", "B"):
                arm = "template" if k[side] == "template" else "llm"
                a, u = _norm(row.get(f"accuracy_{side}")), _yn(row.get(f"useful_{side}"))
                d = arms.setdefault(arm, {"accuracy": Counter(), "useful": Counter()})
                if a in ACCURACY:
                    d["accuracy"][a] += 1
                    filled = True
                if u in YN:
                    d["useful"][u] += 1
            p = _norm(row.get("preferred")).upper()
            if p in ("A", "B"):
                prefs["template" if k[p] == "template" else "llm"] += 1
            elif p in ("NONE", "NEITHER", "SAME"):
                prefs["no preference"] += 1
            scored += filled
    return {"cases_scored": scored,
            "arms": {arm: {"accuracy": {k: d["accuracy"][k] for k in ACCURACY},
                           "accurate_rate": _rate(d["accuracy"], "accurate"), "useful_rate": _rate(d["useful"], "y")}
                     for arm, d in sorted(arms.items())},
            "preferred": dict(prefs)}
