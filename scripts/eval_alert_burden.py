"""Alert-fatigue view over the evaluation cases; writes results/alert_burden[_<profile>].{json,md}.

Counts graded interactions, listings without a severity grade, statistical signals
and no-data pairs across every report for the evaluation cases (deterministic,
offline). Research build: aggregate numbers only.

    python scripts/eval_alert_burden.py --profile public
    python scripts/eval_alert_burden.py --profile research
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import Config  # noqa: E402
from src.data.ingestion import Ingester  # noqa: E402
from src.data.provenance import data_stamp  # noqa: E402
from src.evaluation.alert_burden import counts, summarize  # noqa: E402
from src.evaluation.test_cases import TEST_CASES  # noqa: E402
from src.graph import PharmGuardGraph, Settings  # noqa: E402


def run(data_dir: Path) -> list:
    graph = PharmGuardGraph(Settings(data_dir=data_dir, mode="deterministic", rxnorm_enabled=False,
                                     faers_enabled=False))
    rows = []
    for case in TEST_CASES:
        try:
            s = graph.run(case.input_drugs)
        except ValueError:          # EDG-01 is a single drug: rejected before any report
            continue
        rows.append({"case_id": case.case_id, **counts(s["report_structure"])})
    return rows


def to_markdown(r: dict) -> str:
    d, s = r["data"], r["summary"]
    t, sh, med, mx = s["totals"], s["share_of_items"], s["median_per_report"], s["max_per_report"]
    pct = lambda v: "—" if v is None else f"{v:.1%}"
    L = [f"# Alert burden over the evaluation cases ({d['profile']} build)", "",
         f"Regenerate with `{r['command']}`. Offline, no API key, deterministic reports.",
         f"{d['data']} provenance sha256 `{d['provenance_sha256']}`.", "",
         f"{s['reports']} reports ({r['skipped']} case(s) rejected before a report: fewer than 2 drugs). "
         f"{t['pairs']:,} pairs checked. An *item* is one line a reader sees under a finding heading.", "",
         "| What the reader sees | Total | Share of items | Median per report | Max per report |",
         "|---|---:|---:|---:|---:|",
         f"| graded interactions (DDInter) | {t['graded']:,} | {pct(sh['graded'])} | {med['graded']:g} | {mx['graded']} |",
         f"| of which Major | {t['major']:,} | {pct(s['major_share_of_items'])} | {med['major']:g} | |",
         f"| of which Moderate / Minor | {t['moderate']:,} / {t['minor']:,} | | | |",
         f"| listings without a severity grade | {t['ungraded']:,} | {pct(sh['ungraded'])} | {med['ungraded']:g} | "
         f"{mx['ungraded']} |",
         f"| statistical signals shown (TWOSIDES) | {t['signals']:,} | {pct(sh['signals'])} | {med['signals']:g} | "
         f"{mx['signals']} |",
         f"| statistical signals hidden (\"+N more not shown\") | {t['hidden_signals']:,} | | | |",
         f"| no-data pairs (declared) | {t['no_data_pairs']:,} | | {med['no_data_pairs']:g} | |",
         f"| unresolved inputs (declared) | {t['unresolved']:,} | | | |", "",
         f"Reports with at least one Major: {s['reports_with_a_major']} of {s['reports']}. "
         f"Reports with nothing graded: {s['reports_with_nothing_graded']}.", ""]
    if r.get("per_case"):
        L += ["## Per case", "", "| Case | Pairs | Major | Moderate | Minor | Ungraded | Signals | No data | Unresolved |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for c in r["per_case"]:
            L.append(f"| {c['case_id']} | {c['pairs']} | {c['major']} | {c['moderate']} | {c['minor']} | "
                     f"{c['ungraded']} | {c['signals']} | {c['no_data_pairs']} | {c['unresolved']} |")
        L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["sample", "public", "research"], default="public")
    ap.add_argument("--output-dir", default=str(ROOT / "results"))
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        if args.profile == "sample":
            cfg = Config()
            cfg.paths.data_dir = Path(tmp) / "data"
            shutil.copytree(ROOT / "data" / "sample", cfg.paths.data_dir / "sample")
            Ingester(cfg).ingest_sample()
            data_dir = cfg.paths.data_dir
        else:
            data_dir = ROOT / "data" / "profiles" / args.profile
            if not (data_dir / "processed" / "provenance.json").exists():
                sys.exit(f"no {args.profile} build at {data_dir}")
        rows = run(data_dir)
        stamp = data_stamp(data_dir / "processed")
    if args.profile != "sample":
        stamp["data_dir"] = f"data/profiles/{args.profile}"
    r = {"command": f"python scripts/eval_alert_burden.py --profile {args.profile}", "data": stamp,
         "skipped": len(TEST_CASES) - len(rows), "summary": summarize(rows)}
    if args.profile == "research":
        r["aggregate_only"] = True
    else:
        r["per_case"] = rows
    suffix = "" if args.profile == "sample" else f"_{args.profile}"
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"alert_burden{suffix}.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    (out / f"alert_burden{suffix}.md").write_text(to_markdown(r))
    print(to_markdown(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
