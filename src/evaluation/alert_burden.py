"""Alert-fatigue view: what a reader is shown per report, from the structured report's summary.

Per report, every checked pair falls into one of: a graded interaction (DDInter
Major/Moderate/Minor), a listing without a severity grade, a pair with only
statistical signals (research build), or a declared no-data pair. Counts are
per record where a pair has several records, as the report shows them.
"""
from __future__ import annotations

from statistics import median
from typing import Dict, List

KEYS = ("pairs", "major", "moderate", "minor", "graded", "ungraded", "signals", "hidden_signals",
        "no_data_pairs", "unresolved")


def counts(structure: dict) -> Dict[str, int]:
    s = structure["summary"]
    g = s["graded"]
    return {"pairs": s["pairs"], "major": g["Major"], "moderate": g["Moderate"], "minor": g["Minor"],
            "graded": g["Major"] + g["Moderate"] + g["Minor"], "ungraded": s["ungraded"], "signals": s["signals"],
            "hidden_signals": s["hidden_signals"], "no_data_pairs": s["no_data_pairs"], "unresolved": s["unresolved"]}


def summarize(rows: List[Dict[str, int]]) -> dict:
    n = len(rows)
    tot = {k: sum(r[k] for r in rows) for k in KEYS}
    shown = tot["graded"] + tot["ungraded"] + tot["signals"]
    share = lambda k: round(tot[k] / shown, 4) if shown else None
    return {"reports": n, "totals": tot,
            "items_shown": shown,
            "share_of_items": {k: share(k) for k in ("graded", "ungraded", "signals")},
            "major_share_of_items": share("major"),
            "median_per_report": {k: median(r[k] for r in rows) if rows else None
                                  for k in ("graded", "major", "ungraded", "signals", "no_data_pairs")},
            "max_per_report": {k: max((r[k] for r in rows), default=None) for k in ("graded", "ungraded", "signals")},
            "reports_with_a_major": sum(r["major"] > 0 for r in rows),
            "reports_with_nothing_graded": sum(r["graded"] == 0 for r in rows)}
