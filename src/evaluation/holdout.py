"""Holdout as a graceful-degradation test (not a retrieval-quality test).

A seeded fraction of the DDInter pairs is removed from a copy of a build. Each
removed pair is then run through the graph on its own, and the outcome is:

- ``declared_no_data``: the report lists the pair under "No Curated Interaction
  Data" (the right behaviour when a source has a gap);
- ``recovered``: another loaded source still has records for the pair (on the
  research build, TWOSIDES statistical signals; these are not curated severity);
- ``unresolved``: a drug of the pair no longer resolves to itself, and the report
  lists it as unresolved;
- ``rejected_input``: the input validator refuses a canonical name;
- ``silent``: none of the above. This must never happen.

Removing rows from the processed interaction table is the same as rebuilding
without them: DDInter rows are ingested independently of each other, and the
vocabulary and side-effect tables don't depend on them.
"""
from __future__ import annotations

import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import pandas as pd

from src.data.storage import read_table, write_table

Pair = Tuple[str, str]
OUTCOMES = ("declared_no_data", "recovered", "unresolved", "rejected_input", "silent")
NO_DATA_HEADING = "### No Curated Interaction Data"


def ddinter_pairs(interactions: pd.DataFrame) -> Dict[Pair, str]:
    """Canonical DDInter pair -> its most severe DDInter grade."""
    dd = interactions[interactions.source == "DDInter"]
    rank = {"Major": 0, "Moderate": 1, "Minor": 2}
    out: Dict[Pair, str] = {}
    for a, b, sev in zip(dd.drug_a_name, dd.drug_b_name, dd.severity):
        pair = tuple(sorted((a, b)))
        if pair not in out or rank.get(sev, 3) < rank.get(out[pair], 3):
            out[pair] = sev
    return out


def select_holdout(pairs: Iterable[Pair], fraction: float, seed: int) -> List[Pair]:
    """A seeded sample of pairs; the same inputs always give the same sample."""
    if not 0 < fraction < 1:
        raise ValueError("fraction must be between 0 and 1")
    pool = sorted(set(pairs))
    return sorted(random.Random(seed).sample(pool, round(fraction * len(pool))))


def write_holdout_build(src_processed: Path, dst_data_dir: Path, held: Sequence[Pair]) -> Path:
    """Copy a build into dst_data_dir/processed without the DDInter rows of the held pairs."""
    dst = Path(dst_data_dir) / "processed"
    dst.mkdir(parents=True, exist_ok=True)
    for f in Path(src_processed).iterdir():
        if f.is_file() and f.name != "interactions.parquet":
            shutil.copy2(f, dst / f.name)
    inter = read_table(Path(src_processed) / "interactions.parquet")
    held_keys = {f"{a}||{b}" for a, b in held}
    lo = inter[["drug_a_name", "drug_b_name"]].min(axis=1)
    hi = inter[["drug_a_name", "drug_b_name"]].max(axis=1)
    drop = (inter.source == "DDInter") & (lo + "||" + hi).isin(held_keys)
    write_table(inter[~drop].reset_index(drop=True), dst / "interactions.parquet")
    return dst


def _no_data_lines(report: str) -> set:
    lines, inside = set(), False
    for line in report.splitlines():
        if line.startswith("#"):
            inside = line.strip() == NO_DATA_HEADING
        elif inside and line.startswith("- "):
            lines.add(line[2:].strip())
    return lines


def classify(state: dict, pair: Pair) -> Tuple[str, List[str]]:
    """Outcome for one held-out pair, from the graph's final state; also the sources that still had records."""
    a, b = pair
    resolved = {r["generic_name"] for r in state["resolved"] if r.get("resolved")}
    if not {a, b} <= resolved:
        return "unresolved", []
    for x in state["retrieval"]["interactions"]:
        if tuple(sorted(x["pair"])) == pair and x["records"]:
            return "recovered", sorted({r["source"] for r in x["records"]})
    declared = any(tuple(sorted(p)) == pair for p in state["retrieval"]["no_data_pairs"])
    if declared and f"{a} + {b}" in _no_data_lines(state["report"]) and state["final_validation"]["passed"]:
        return "declared_no_data", []
    return "silent", []


def run_holdout(graph, held: Sequence[Pair], grades: Dict[Pair, str]) -> dict:
    """Run every held-out pair through the graph; counts overall and by the pair's DDInter grade."""
    from src.input_validation import InvalidDrugNameError

    counts: Counter = Counter()
    by_grade: Dict[str, Counter] = defaultdict(Counter)
    recovered_by: Counter = Counter()
    leaked = 0
    for pair in held:
        try:
            outcome, sources = classify(graph.run(list(pair)), pair)
        except InvalidDrugNameError:
            outcome, sources = "rejected_input", []
        if "DDInter" in sources:
            leaked += 1          # a held-out DDInter record reached the report: the holdout build is wrong
        counts[outcome] += 1
        by_grade[grades.get(pair, "not graded")][outcome] += 1
        for s in sources:
            recovered_by[s] += 1
    n = len(held)
    return {"held_out_pairs": n,
            "outcomes": {o: counts[o] for o in OUTCOMES},
            "rates": {o: round(counts[o] / n, 4) if n else None for o in OUTCOMES},
            "by_ddinter_grade": {g: {o: c[o] for o in OUTCOMES} for g, c in sorted(by_grade.items())},
            "recovered_by_source": dict(recovered_by),
            "ddinter_leaks": leaked}
