"""Score the pharmacist review; writes results/pharmacist_review.{json,md}.

    python scripts/score_pharmacist_review.py                  # data/validation/pharmacist/rubric.csv
    python scripts/score_pharmacist_review.py --ab             # + rubric_ab.csv, unblinded with data/cache/pharmacist_ab_key.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.pharmacist import ACCURACY, score_ab, score_rubric  # noqa: E402

DIR = ROOT / "data" / "validation" / "pharmacist"


def to_markdown(r: dict) -> str:
    f = lambda v: "—" if v is None else f"{v:.0%}"
    s = r["rubric"]
    L = ["# Pharmacist review", "", "Regenerate with `python scripts/score_pharmacist_review.py`. Cases and protocol: "
         "data/validation/pharmacist/cases.md, docs/PHARMACIST_REVIEW_PROTOCOL.md.", "",
         f"Reviewers: {s['reviewers']}. Case reviews scored: {s['rows_scored']} (blank {s['rows_blank']}, "
         f"invalid {len(s['rows_invalid'])}).", "",
         "| | Count |", "|---|---:|"]
    L += [f"| {k} | {s['accuracy'][k]} |" for k in ACCURACY]
    L += ["", f"Accurate: {f(s['accurate_rate'])}. Useful: {f(s['useful_rate'])}. "
              f"Would recommend: {f(s['would_recommend_rate'])}.", ""]
    ab = r.get("ab")
    if ab:
        L += ["## Blinded A/B: template vs LLM", "", f"Cases scored: {ab['cases_scored']}.", "",
              "| Report | Accurate | Partly | Inaccurate | Accurate rate | Useful rate |", "|---|---:|---:|---:|---:|---:|"]
        for arm, d in ab["arms"].items():
            a = d["accuracy"]
            L.append(f"| {arm} | {a['accurate']} | {a['partly accurate']} | {a['inaccurate']} | "
                     f"{f(d['accurate_rate'])} | {f(d['useful_rate'])} |")
        L += ["", f"Preferred: {ab['preferred'] or '—'}.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rubric", default=str(DIR / "rubric.csv"))
    ap.add_argument("--ab", action="store_true")
    ap.add_argument("--output-dir", default=str(ROOT / "results"))
    args = ap.parse_args()
    r = {"rubric": score_rubric(Path(args.rubric))}
    if args.ab:
        key = json.loads((ROOT / "data" / "cache" / "pharmacist_ab_key.json").read_text())["key"]
        r["ab"] = score_ab(DIR / "rubric_ab.csv", key)
    if r["rubric"]["rows_scored"] == 0 and not r.get("ab"):
        print("No filled rubric rows yet: nothing written.")
        return 1
    out = Path(args.output_dir)
    (out / "pharmacist_review.json").write_text(json.dumps(r, indent=2) + "\n")
    (out / "pharmacist_review.md").write_text(to_markdown(r))
    print(to_markdown(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
