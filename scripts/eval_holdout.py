"""Holdout graceful-degradation test; writes results/holdout_<profile>.{json,md}.

Holds out a seeded fraction of DDInter pairs (by pair), writes a copy of the build
without them to a temp folder, runs each held-out pair through the graph
(deterministic, offline) and counts how the report degrades: declared as no data,
recovered from another source (research build: TWOSIDES signals), unresolved, or
silent (must be 0). This is a graceful-degradation test, not a retrieval-quality
test: it checks that a source gap is reported, not that the gap is filled.

Usage:
    python scripts/eval_holdout.py --profile public
    python scripts/eval_holdout.py --profile research     # aggregate numbers only
    python scripts/eval_holdout.py --profile sample       # synthetic sample (what the tests use)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import Config  # noqa: E402
from src.data.ingestion import Ingester  # noqa: E402
from src.data.provenance import data_stamp  # noqa: E402
from src.data.storage import read_table  # noqa: E402
from src.evaluation.holdout import OUTCOMES, ddinter_pairs, run_holdout, select_holdout, write_holdout_build  # noqa: E402
from src.graph import PharmGuardGraph, Settings  # noqa: E402

LABELS = {"declared_no_data": "declared as no data", "recovered": "recovered from another source",
          "unresolved": "a drug unresolved (declared)", "rejected_input": "input rejected by the validator",
          "silent": "**silent (must be 0)**"}


def source_processed(profile: str, tmp: Path) -> Path:
    if profile == "sample":
        cfg = Config()
        cfg.paths.data_dir = tmp / "sample_build"
        shutil.copytree(ROOT / "data" / "sample", cfg.paths.data_dir / "sample")
        Ingester(cfg).ingest_sample()
        return cfg.paths.processed_dir
    p = ROOT / "data" / "profiles" / profile / "processed"
    if not (p / "provenance.json").exists():
        sys.exit(f"no {profile} build at {p}; see docs/DATASETS.md")
    return p


def evaluate(profile: str, fraction: float, seed: int, tmp: Path) -> dict:
    src = source_processed(profile, tmp)
    grades = ddinter_pairs(read_table(src / "interactions.parquet"))
    held = select_holdout(grades, fraction, seed)
    dst = tmp / "holdout"
    write_holdout_build(src, dst, held)
    graph = PharmGuardGraph(Settings(data_dir=dst, mode="deterministic", rxnorm_enabled=False, faers_enabled=False))
    t = time.perf_counter()
    res = run_holdout(graph, held, grades)
    stamp = data_stamp(src)
    if profile != "sample":
        stamp["data_dir"] = f"data/profiles/{profile}"
    return {"command": f"python scripts/eval_holdout.py --profile {profile} --fraction {fraction} --seed {seed}",
            "kind": "graceful-degradation test (not a retrieval-quality test)",
            "data": stamp, "fraction": fraction, "seed": seed, "ddinter_pairs": len(grades),
            "mode": "deterministic; RxNorm API and FAERS off", **res,
            "seconds": round(time.perf_counter() - t, 1)}


def to_markdown(r: dict) -> str:
    d = r["data"]
    n = r["held_out_pairs"]
    L = [f"# Holdout: graceful degradation ({d['profile']} build)", "",
         f"Regenerate with `{r['command']}`. Offline, no API key, {r['mode']}.",
         f"{d['data']} provenance sha256 `{d['provenance_sha256']}`.", "",
         "**This is a graceful-degradation test, not a retrieval-quality test.** "
         f"{r['fraction']:.0%} of the build's {r['ddinter_pairs']:,} DDInter pairs (seed {r['seed']}, sampled by pair) "
         "were removed from a copy of the build, and each removed pair was then checked on its own. It shows what a "
         "user sees when the curated source has a gap; it says nothing about how many real interactions DDInter lacks.",
         "", "| Outcome | Pairs | Share |", "|---|---:|---:|"]
    for o in OUTCOMES:
        L.append(f"| {LABELS[o]} | {r['outcomes'][o]:,} | {r['rates'][o]:.1%} |")
    L += [f"| total held out | {n:,} | |", "", "By the held-out pair's DDInter grade:", "",
          "| DDInter grade | " + " | ".join(LABELS[o].replace("**", "") for o in OUTCOMES) + " |",
          "|---|" + "---:|" * len(OUTCOMES)]
    order = {"Major": 0, "Moderate": 1, "Minor": 2}
    for g, c in sorted(r["by_ddinter_grade"].items(), key=lambda x: order.get(x[0], 3)):
        name = g if g in order else "not graded"
        L.append(f"| {name} | " + " | ".join(f"{c[o]:,}" for o in OUTCOMES) + " |")
    L.append("")
    if r["recovered_by_source"]:
        L.append("Recovered pairs by source: " + ", ".join(f"{k} {v:,}" for k, v in r["recovered_by_source"].items())
                 + ". A recovered TWOSIDES pair shows statistical reporting signals, not a curated severity, so a "
                 "held-out Major pair recovered this way is no longer reported as Major.")
        L.append("")
    L.append(f"Held-out DDInter records that still reached a report (must be 0): {r['ddinter_leaks']}.")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["sample", "public", "research"], default="public")
    ap.add_argument("--fraction", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=20260928)
    ap.add_argument("--output-dir", default=str(ROOT / "results"))
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="pharmguard-holdout-") as tmp:
        r = evaluate(args.profile, args.fraction, args.seed, Path(tmp))
    suffix = "" if args.profile == "sample" else f"_{args.profile}"
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"holdout{suffix}.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    (out / f"holdout{suffix}.md").write_text(to_markdown(r))
    print(to_markdown(r))
    return 1 if r["outcomes"]["silent"] or r["ddinter_leaks"] else 0


if __name__ == "__main__":
    sys.exit(main())
