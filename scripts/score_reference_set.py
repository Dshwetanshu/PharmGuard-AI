"""Score PharmGuard against data/validation/reference_interactions.csv (public build, deterministic).

Only rows with verified_source and verified_on filled are scored; unverified rows are skipped
and counted. Writes results/reference_set_<profile>.{json,md}.

    python scripts/score_reference_set.py --check-names     # names resolve? no outcomes shown, nothing written
    python scripts/score_reference_set.py                   # score the verified rows
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.provenance import data_stamp  # noqa: E402
from src.evaluation.reference_set import OUTCOMES, load, score  # noqa: E402
from src.graph import PharmGuardGraph, Settings  # noqa: E402

CSV = ROOT / "data" / "validation" / "reference_interactions.csv"


def to_markdown(r: dict) -> str:
    f = lambda v: "—" if v is None else f"{v:.3f}"
    d = r["data"]
    L = [f"# Reference set ({d['profile']} build)", "",
         f"Regenerate with `python scripts/score_reference_set.py --profile {d['profile']}`. {d['data']} "
         f"provenance sha256 `{d['provenance_sha256']}`.", "",
         f"Rows: {r['rows']}; scored {r['scored']}; **skipped {r['skipped_unverified']} unverified** "
         "(no verified_source / verified_on).", "",
         "| Outcome | Expected interaction | Negative control |", "|---|---:|---:|"]
    for o in OUTCOMES:
        L.append(f"| {o} | {r['outcomes_positives'][o]} | {r['outcomes_negative_controls'][o]} |")
    u, a = r["under_triage"], r["drugscom_agreement"]
    L += ["", f"- Recall (graded): {f(r['recall_graded'])}; including ungraded listings: {f(r['recall_including_ungraded'])}.",
          f"- Under-triage (PharmGuard's DDInter grade below the reference's minimum): {u['count']} of {u['of_detected']} "
          f"detected ({f(u['rate'])}).",
          f"- Silent misses: {r['silent']} (must be 0).",
          f"- DDInter vs Drugs.com, {a['rows']} rows with a Drugs.com grade: exact agreement {f(a['exact'])}, "
          f"linear-weighted κ {f(a['linear_weighted_kappa'])} (levels none < Minor < Moderate < Major).", "",
          "| Pair | Expected | Min severity | Outcome | PharmGuard grade | Drugs.com |", "|---|---|---|---|---|---|"]
    for x in r["results"]:
        L.append(f"| {x['pair'][0]} + {x['pair'][1]} | {x['expected']} | {x['min_severity'] or '—'} | {x['outcome']} | "
                 f"{x['grade'] or '—'} | {x['drugscom'] or '—'} |")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["public"], default="public")
    ap.add_argument("--csv", default=str(CSV))
    ap.add_argument("--check-names", action="store_true")
    ap.add_argument("--output-dir", default=str(ROOT / "results"))
    args = ap.parse_args()
    data_dir = ROOT / "data" / "profiles" / args.profile
    graph = PharmGuardGraph(Settings(data_dir=data_dir, mode="deterministic", rxnorm_enabled=False, faers_enabled=False))
    rows = load(Path(args.csv))
    if args.check_names:
        n = graph.components.normalizer
        bad = sorted({(q, r.method) for row in rows for q in (row.drug_a, row.drug_b)
                      for r in [n.resolve(q)] if not (r.resolved and r.generic_name == q.lower())})
        print(f"{len(rows)} rows; names that don't resolve to themselves: {bad or 'none'}")
        return 1 if bad else 0
    r = {"data": {**data_stamp(data_dir / "processed"), "data_dir": f"data/profiles/{args.profile}"},
         **score(rows, graph.run)}
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"reference_set_{args.profile}.json").write_text(json.dumps(r, indent=2) + "\n")
    (out / f"reference_set_{args.profile}.md").write_text(to_markdown(r))
    print(to_markdown(r))
    return 1 if r["silent"] else 0


if __name__ == "__main__":
    sys.exit(main())
