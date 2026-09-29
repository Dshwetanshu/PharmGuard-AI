"""Scoring PharmGuard against an independent reference set (data/validation/reference_interactions.csv).

Only rows with verified_source and verified_on filled are scored; the rest are skipped
and counted. Each scored pair is run on its own (deterministic) and gets one outcome:

- DETECTED: a curated record with a severity grade (Major / Moderate / Minor);
- LISTED_UNGRADED: only records without a grade (a DDInter listing, or statistical signals);
- NO_DATA: declared under "No Curated Interaction Data";
- UNRESOLVED: a drug name didn't resolve (declared as unresolved);
- SILENT: none of the above. Must never happen.

Metrics: recall (DETECTED / expected interactions) and recall including ungraded
listings; under-triage (DETECTED with PharmGuard's grade below min_severity);
silent misses; how the negative controls come back; and DDInter vs Drugs.com agreement
on rows with drugscom_severity filled.
"""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

COLUMNS = ["drug_a", "drug_b", "expected", "min_severity", "source_hint", "verified_source", "verified_on",
           "drugscom_severity", "notes"]
OUTCOMES = ("DETECTED", "LISTED_UNGRADED", "NO_DATA", "UNRESOLVED", "SILENT")
LEVELS = ("none", "Minor", "Moderate", "Major")     # ordinal; "none" = no interaction listed
RANK = {v: i for i, v in enumerate(LEVELS)}


@dataclass
class Row:
    drug_a: str
    drug_b: str
    expected: str               # "interaction" | "none"
    min_severity: str
    verified: bool
    drugscom: Optional[str]


def _level(v: str) -> Optional[str]:
    v = (v or "").strip()
    if not v:
        return None
    for lv in LEVELS:
        if v.lower() == lv.lower():
            return lv
    if v.lower() in ("no interaction", "no interactions found", "not listed"):
        return "none"
    raise ValueError(f"unknown severity {v!r}; use one of {LEVELS}")


def load(path: Path) -> List[Row]:
    with Path(path).open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"columns must be {COLUMNS}, got {reader.fieldnames}")
        rows = []
        for r in reader:
            exp = r["expected"].strip().lower()
            if exp not in ("interaction", "none"):
                raise ValueError(f"expected must be 'interaction' or 'none': {r}")
            rows.append(Row(r["drug_a"].strip(), r["drug_b"].strip(), exp, r["min_severity"].strip(),
                            bool(r["verified_source"].strip() and r["verified_on"].strip()),
                            _level(r["drugscom_severity"])))
    return rows


def outcome(state: Dict[str, Any]) -> Dict[str, Any]:
    """Outcome of a two-drug run, and PharmGuard's most severe curated grade if any."""
    resolved = [r for r in state["resolved"] if r.get("resolved")]
    names = {r["generic_name"] for r in resolved}
    if len(names) < 2:
        return {"outcome": "UNRESOLVED", "grade": None}
    recs = [r for x in state["retrieval"]["interactions"] for r in x["records"]]
    graded = [r["severity"] for r in recs if r["source"] != "TWOSIDES" and r["severity"] in ("Major", "Moderate", "Minor")]
    if graded:
        return {"outcome": "DETECTED", "grade": max(graded, key=RANK.get)}
    if recs:
        return {"outcome": "LISTED_UNGRADED", "grade": None}
    a, b = sorted(names)
    if [a, b] in [sorted(p) for p in state["retrieval"]["no_data_pairs"]] and \
            "### No Curated Interaction Data" in state["report"] and f"- {a} + {b}" in state["report"]:
        return {"outcome": "NO_DATA", "grade": None}
    return {"outcome": "SILENT", "grade": None}


def _kappa_linear(a: Sequence[str], b: Sequence[str]) -> Optional[float]:
    k, n = len(LEVELS), len(a)
    if not n:
        return None
    m = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        m[RANK[x]][RANK[y]] += 1
    rows, cols = [sum(r) for r in m], [sum(m[i][j] for i in range(k)) for j in range(k)]
    w = lambda i, j: 1 - abs(i - j) / (k - 1)
    po = sum(w(i, j) * m[i][j] for i in range(k) for j in range(k)) / n
    pe = sum(w(i, j) * rows[i] * cols[j] for i in range(k) for j in range(k)) / n / n
    return None if pe == 1 else round((po - pe) / (1 - pe), 4)


def score(rows: Sequence[Row], run) -> Dict[str, Any]:
    """run(list_of_two_names) -> final graph state."""
    scored = [r for r in rows if r.verified]
    results = []
    for r in scored:
        o = outcome(run([r.drug_a, r.drug_b]))
        results.append({"pair": [r.drug_a, r.drug_b], "expected": r.expected, "min_severity": r.min_severity,
                        "drugscom": r.drugscom, **o})
    pos = [x for x in results if x["expected"] == "interaction"]
    neg = [x for x in results if x["expected"] == "none"]
    det = [x for x in pos if x["outcome"] == "DETECTED"]
    under = [x for x in det if x["min_severity"] in RANK and RANK[x["grade"]] < RANK[x["min_severity"]]]
    rate = lambda n, d: round(n / d, 4) if d else None
    both = [x for x in results if x["drugscom"] is not None]
    pg = [x["grade"] or "none" for x in both]
    dc = [x["drugscom"] for x in both]
    return {
        "rows": len(rows), "scored": len(scored), "skipped_unverified": len(rows) - len(scored),
        "positives": len(pos), "negative_controls": len(neg),
        "outcomes_positives": {o: sum(x["outcome"] == o for x in pos) for o in OUTCOMES},
        "outcomes_negative_controls": {o: sum(x["outcome"] == o for x in neg) for o in OUTCOMES},
        "recall_graded": rate(len(det), len(pos)),
        "recall_including_ungraded": rate(len(det) + sum(x["outcome"] == "LISTED_UNGRADED" for x in pos), len(pos)),
        "under_triage": {"count": len(under), "of_detected": len(det), "rate": rate(len(under), len(det)),
                         "pairs": [x["pair"] for x in under]},
        "silent": sum(x["outcome"] == "SILENT" for x in results),
        "drugscom_agreement": {"rows": len(both), "exact": rate(sum(a == b for a, b in zip(pg, dc)), len(both)),
                               "linear_weighted_kappa": _kappa_linear(pg, dc),
                               "confusion_pharmguard_by_drugscom": dict(Counter(f"{a} / {b}" for a, b in zip(pg, dc)))},
        "results": results,
    }
