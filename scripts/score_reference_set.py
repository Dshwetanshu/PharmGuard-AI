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
EVIDENCE = ROOT / "data" / "validation" / "label_evidence.json"
DRUGSCOM_PICKS = [("simvastatin", "clarithromycin"), ("warfarin", "amiodarone"), ("atorvastatin", "lisinopril")]


def to_markdown(r: dict) -> str:
    f = lambda v: "—" if v is None else f"{v:.3f}"
    d = r["data"]
    L = [f"# Reference set ({d['profile']} build)", "",
         f"Regenerate with `python scripts/score_reference_set.py --profile {d['profile']}`. {d['data']} "
         f"provenance sha256 `{d['provenance_sha256']}`.", "",
         f"Rows: {r['rows']}; scored {r['scored']}; **skipped {r['skipped_unverified']} unverified** "
         "(no verified_source / verified_on).", ""]
    lab = r.get("label_reference")
    if lab:
        L += ["**Reference: FDA labeling, checked automatically** (`python scripts/verify_reference_labels.py`, "
              f"openFDA drug labels fetched {lab['fetched_on']}). Each drug's label was searched for the other drug by "
              "generic, salt or brand name, and the wording around the match was classified by keyword rules "
              "(src/evaluation/label_evidence.py). **The classification is heuristic**, and its rules were refined by "
              "reading these same labels, so it is not independently validated. An expected interaction counts as "
              "verified only if a label gives guidance (contraindicated, avoid, or monitor/adjust); "
              f"{lab['unclear']} rows the labels don't settle are excluded and counted as skipped. A negative control "
              "counts as verified when neither label names the other drug, which is **only weak evidence** of no "
              "interaction.", "",
              "Label evidence for the verified rows: " + ", ".join(f"{k} {v}" for k, v in lab["classes"].items()) + ".", ""]
    L += [
         "| Outcome | Expected interaction | Negative control |", "|---|---:|---:|"]
    for o in OUTCOMES:
        L.append(f"| {o} | {r['outcomes_positives'][o]} | {r['outcomes_negative_controls'][o]} |")
    u, a = r["under_triage"], r["drugscom_agreement"]
    L += ["", f"- Recall (graded): {f(r['recall_graded'])}; including ungraded listings: {f(r['recall_including_ungraded'])}.",
          f"- Under-triage (PharmGuard's DDInter grade below the reference's minimum): {u['count']} of {u['of_detected']} "
          f"detected ({f(u['rate'])}).",
          f"- Silent misses: {r['silent']} (must be 0).",
          f"- DDInter vs Drugs.com, {a['rows']} rows with a Drugs.com grade: exact agreement {f(a['exact'])}, "
          f"linear-weighted κ {f(a['linear_weighted_kappa'])} (levels none < Minor < Moderate < Major). Pairs picked for "
          "a manual Drugs.com lookup: " + "; ".join(f"{x} + {y}" for x, y in DRUGSCOM_PICKS) + ".", ""]
    if lab:
        c = lab["vs_ddinter"]
        L += [f"- FDA label vs DDInter grade, {c['pairs']} verified interactions (label wording mapped "
              f"{c['mapping']}): same grade {f(c['mapped_agreement'])} of {c['mapped_pairs']}; DDInter lower than the "
              f"label: {c['ddinter_lower_than_label']}.", "",
              "| Label wording / DDInter grade | Pairs |", "|---|---:|"]
        L += [f"| {k} | {v} |" for k, v in c["grid_label_class_by_ddinter"].items()]
        L.append("")
    L += [
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
    if EVIDENCE.exists():
        from collections import Counter
        from src.evaluation.label_evidence import CLASS_TEXT, severity_comparison
        ev = json.loads(EVIDENCE.read_text())
        grade = {tuple(x["pair"]): x["grade"] for x in r["results"]}
        settled = [p for p in ev["pairs"] if p["reference"] == "interaction"]
        r["label_reference"] = {
            "fetched_on": ev["fetched_on"], "unclear": sum(p["reference"] == "unclear" for p in ev["pairs"]),
            "classes": dict(Counter(CLASS_TEXT[p["evidence"]["klass"]] for p in ev["pairs"] if p["reference"] != "unclear")),
            "vs_ddinter": severity_comparison([(p["evidence"]["klass"], grade.get((p["row"]["drug_a"], p["row"]["drug_b"])))
                                               for p in settled])}
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"reference_set_{args.profile}.json").write_text(json.dumps(r, indent=2) + "\n")
    (out / f"reference_set_{args.profile}.md").write_text(to_markdown(r))
    print(to_markdown(r))
    return 1 if r["silent"] else 0


if __name__ == "__main__":
    sys.exit(main())
