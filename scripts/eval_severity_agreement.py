"""Severity agreement: PRR-derived TWOSIDES tiers vs DDInter grades (research build).

Writes results/severity_agreement_research.{json,md}: aggregate numbers only (no pairs,
no events), because TWOSIDES content stays local. Offline, no API key.

    python scripts/eval_severity_agreement.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.provenance import data_stamp  # noqa: E402
from src.data.storage import read_table  # noqa: E402
from src.evaluation.severity_agreement import GRADES, evaluate  # noqa: E402

COMMAND = "python scripts/eval_severity_agreement.py"


def _row(name, s):
    f = lambda v: "—" if v is None else f"{v:.3f}"
    return (f"| {name} | {s['n']:,} | {f(s['accuracy'])} | {f(s['macro_f1'])} | {f(s['linear_weighted_kappa'])} | "
            f"{f(s['spearman_tier'])} | {f(s['spearman_prr'])} |")


def _confusion(title, s):
    L = [f"{title} (rows: DDInter grade; columns: PRR tier)", "", "| DDInter \\ PRR tier | " + " | ".join(GRADES) + " |",
         "|---|" + "---:|" * len(GRADES)]
    for g, row in zip(GRADES, s["confusion"]["counts"]):
        L.append(f"| {g} | " + " | ".join(f"{v:,}" for v in row) + " |")
    return L + [""]


def to_markdown(r: dict) -> str:
    d, c, t, tu = r["data"], r["counts"], r["test"], r["tuning"]
    th = tu["tuned_thresholds"]
    L = ["# Severity agreement: TWOSIDES PRR tiers vs DDInter grades (research build)", "",
         f"Regenerate with `{COMMAND}`. Offline, no API key. Aggregate numbers only.",
         f"{d['data']} provenance sha256 `{d['provenance_sha256']}`.", "",
         "**What is compared.** For each pair that has both a DDInter record and a TWOSIDES signal, the DDInter grade "
         "(Minor < Moderate < Major) against a tier from the pair's PRR, the highest PRR among its kept TWOSIDES events "
         "(TWOSIDES filters: PRR ≥ 2, ≥ 5 co-reports, top 5 events per pair). Pairs DDInter lists without a grade are "
         "left out. PharmGuard never shows these tiers: reports give TWOSIDES signals without severity words. This "
         "asks whether a PRR could stand in for a curated grade.", "",
         f"Pairs: DDInter {c['ddinter_pairs']:,}; TWOSIDES {c['twosides_pairs']:,}; in both {c['overlap_pairs']:,} "
         f"({c['overlap_graded']:,} graded by DDInter, {c['overlap_not_graded']:,} not graded).",
         f"Split: seeded 50/50 by pair (seed {r['seed']}): calibration {r['split']['calibration']:,}, "
         f"test {r['split']['test']:,}. Tuned thresholds were chosen on the calibration half only "
         f"({tu['objective']}, over {tu['candidates']}).", "",
         "## Test half", "",
         "| Thresholds | Pairs | Accuracy | Macro-F1 | Linear-weighted κ | Spearman (tier) | Spearman (PRR) |",
         "|---|---:|---:|---:|---:|---:|---:|",
         _row("current: Moderate ≥ 4, Major ≥ 10", t["current"]),
         _row(f"tuned on calibration: Moderate ≥ {th['moderate_from']:g}, Major ≥ {th['major_from']:g}", t["tuned"]),
         _row(f"baseline: always {t['majority_class']['class']} (calibration majority)", t["majority_class"]),
         "", "DDInter grades in the test half: " + ", ".join(f"{g} {n:,}" for g, n in r["ddinter_grade_share_test"].items())
         + ".", ""]
    L += _confusion("Current thresholds, test half", t["current"])
    L += _confusion("Tuned thresholds, test half", t["tuned"])
    L += ["Spearman (tier) correlates the tier with the DDInter grade; Spearman (PRR) uses the raw PRR, so it doesn't "
          "depend on any threshold. Both use average ranks for ties.", "",
          "## Calibration half (for reference; the tuned row is fitted here)", "",
          "| Thresholds | Pairs | Accuracy | Macro-F1 | Linear-weighted κ | Spearman (tier) | Spearman (PRR) |",
          "|---|---:|---:|---:|---:|---:|---:|",
          _row("current", r["calibration"]["current"]), _row("tuned", r["calibration"]["tuned"]), ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260928)
    ap.add_argument("--output-dir", default=str(ROOT / "results"))
    args = ap.parse_args()
    processed = ROOT / "data" / "profiles" / "research" / "processed"
    if not (processed / "provenance.json").exists():
        sys.exit("needs the research build: python scripts/ingest_data.py --full --profile research")
    inter = read_table(processed / "interactions.parquet")
    r = {"command": COMMAND, "data": {**data_stamp(processed), "data_dir": "data/profiles/research"},
         "aggregate_only": True, **evaluate(inter, args.seed)}
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "severity_agreement_research.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    (out / "severity_agreement_research.md").write_text(to_markdown(r))
    print(to_markdown(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
