"""Score the human audit of the LLM judge: percent agreement and Cohen's kappa.

After a person fills in human_verdict (supported / unsupported / contradicted) in
results/judge_audit_<profile>.csv without looking at the judge's verdicts:

    python scripts/score_judge_audit.py --profile public

Writes results/judge_audit_score_<profile>.{json,md}. The key (the judge's verdicts)
is read from data/cache/judge_audit_key_<profile>.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.judge import VERDICTS, score_audit  # noqa: E402


def to_markdown(s: dict, profile: str) -> str:
    f = lambda v: "—" if v is None else f"{v:.3f}"
    L = [f"# Human audit of the LLM judge ({profile} build)", "",
         f"Regenerate with `python scripts/score_judge_audit.py --profile {profile}`.", "",
         f"Rows scored: {s['rows_scored']} (blank: {s['rows_blank']}; invalid: {len(s['rows_invalid'])}).",
         f"Percent agreement: {f(s['percent_agreement'])}. Cohen's κ: {f(s['cohen_kappa'])}.", "",
         "| human \\ judge | " + " | ".join(VERDICTS) + " |", "|---|" + "---:|" * len(VERDICTS)]
    for h in VERDICTS:
        L.append(f"| {h} | " + " | ".join(str(s["confusion_human_by_judge"][h][j]) for j in VERDICTS) + " |")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["sample", "public"], default="public")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--key", default=None)
    ap.add_argument("--output-dir", default=str(ROOT / "results"))
    args = ap.parse_args()
    csv_path = Path(args.csv or ROOT / "results" / f"judge_audit_{args.profile}.csv")
    key_path = Path(args.key or ROOT / "data" / "cache" / f"judge_audit_key_{args.profile}.json")
    if not csv_path.exists() or not key_path.exists():
        sys.exit(f"needs {csv_path} and {key_path}: run scripts/run_llm_eval.py first")
    s = score_audit(csv_path, key_path)
    out = Path(args.output_dir)
    (out / f"judge_audit_score_{args.profile}.json").write_text(json.dumps(s, indent=2) + "\n")
    (out / f"judge_audit_score_{args.profile}.md").write_text(to_markdown(s, args.profile))
    print(to_markdown(s, args.profile))
    return 0


if __name__ == "__main__":
    sys.exit(main())
