"""Export the 10 pharmacist-review cases with PharmGuard's report for each, plus the blank rubric.

Public build, deterministic reports (what https://pharmguard.web.app shows). Writes
data/validation/pharmacist/: cases.md (one report per case) and rubric.csv (one row per
case to fill in). See docs/PHARMACIST_REVIEW_PROTOCOL.md.

    python scripts/export_pharmacist_cases.py
    python scripts/export_pharmacist_cases.py --ab --provider gemini   # + blinded LLM vs template (needs a key)
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.graph import PharmGuardGraph, Settings  # noqa: E402

OUT = ROOT / "data" / "validation" / "pharmacist"
# (id, what it exercises, input exactly as typed)
CASES = [
    ("PR-01", "several Major findings", ["warfarin", "amiodarone", "simvastatin", "clarithromycin"]),
    ("PR-02", "Major findings, hyperkalemia risk", ["lisinopril", "spironolactone", "potassium chloride"]),
    ("PR-03", "serotonergic combination", ["sertraline", "tramadol", "linezolid"]),
    ("PR-04", "7-drug geriatric list: mixed grades and ungraded listings",
     ["lisinopril", "spironolactone", "metformin", "atorvastatin", "aspirin", "omeprazole", "sertraline"]),
    ("PR-05", "mostly ungraded DDInter listings", ["acetaminophen", "levothyroxine", "atorvastatin", "aspirin"]),
    ("PR-06", "discontinued brand, a brand, and the same drug twice", ["Coumadin", "Diflucan", "warfarin"]),
    ("PR-07", "misspelling between two look-alike brands", ["Celebyx", "warfarin", "aspirin"]),
    ("PR-08", "ambiguous name and a combination product", ["insulin", "metoprolol", "Percocet"]),
    ("PR-09", "pairs with no curated data", ["escitalopram", "amoxicillin", "melatonin"]),
    ("PR-10", "misspellings and a brand name", ["metfromin", "lisonopril", "ibuprofen", "Lasix"]),
]
RUBRIC = ["case_id", "report", "reviewer", "accuracy", "useful", "would_recommend", "missed_or_wrong", "comments"]
AB_RUBRIC = ["case_id", "reviewer", "accuracy_A", "accuracy_B", "useful_A", "useful_B", "preferred", "comments"]


def body(report: str) -> str:
    return report.replace("\n# ", "\n#### ").replace("\n## ", "\n### ").lstrip("# ").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--ab", action="store_true", help="also export a blinded LLM-vs-template comparison")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--seed", type=int, default=20260929)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data_dir = ROOT / "data" / "profiles" / "public"
    graph = PharmGuardGraph(Settings(data_dir=data_dir, mode="deterministic", rxnorm_enabled=False, faers_enabled=False))
    states = {cid: graph.run(drugs) for cid, _, drugs in CASES}
    L = ["# PharmGuard pharmacist review: cases", "",
         "Read docs/PHARMACIST_REVIEW_PROTOCOL.md first. Each report below is exactly what PharmGuard returns "
         "for the input shown (public build, deterministic mode). Score each one in rubric.csv.", ""]
    for cid, what, drugs in CASES:
        L += [f"## {cid}", "", f"Input, as typed: `{', '.join(drugs)}`", "", body(states[cid]["report"]), "", "---", ""]
    (out / "cases.md").write_text("\n".join(L))
    with (out / "rubric.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RUBRIC)
        w.writeheader()
        for cid, _, _ in CASES:
            w.writerow({"case_id": cid, "report": "template"} | {k: "" for k in RUBRIC[2:]})
    print(f"Wrote {out / 'cases.md'} and {out / 'rubric.csv'} ({len(CASES)} cases).")
    if args.ab:
        return export_ab(graph, states, out, args)
    return 0


def export_ab(graph, states, out: Path, args) -> int:
    """Blinded A/B: per case, the template and an LLM report in random order; the key goes to data/cache/."""
    import os
    from src.graph.settings import KEY_VARS
    from src.agents.generator import Generator
    from src.config import DEFAULT_MODELS
    provider = args.provider
    if not provider or not os.getenv(KEY_VARS.get(provider, "-")):
        sys.exit("--ab needs --provider with an API key in the environment")
    s = replace(graph.settings, mode="llm", llm_provider=provider, llm_configured=True)
    llm_graph = PharmGuardGraph(s, replace(graph.components, generator=Generator(
        s.to_config(), provenance=graph.components.generator.provenance), llm_available=True,
        llm_label=f"{provider}:{DEFAULT_MODELS[provider]}"))
    rng = random.Random(args.seed)
    key, L = {}, ["# PharmGuard pharmacist review: blinded A/B", "",
                  "Two reports per case, A and B, in random order. Score both in rubric_ab.csv.", ""]
    for cid, _, drugs in CASES:
        llm = llm_graph.run(drugs)
        pair = [("template", states[cid]["report"]), (f"llm ({llm['report_source']})", llm["report"])]
        rng.shuffle(pair)
        key[cid] = {"A": pair[0][0], "B": pair[1][0]}
        L += [f"## {cid}", "", f"Input, as typed: `{', '.join(drugs)}`", "", "### Report A", "", body(pair[0][1]),
              "", "### Report B", "", body(pair[1][1]), "", "---", ""]
    (out / "cases_ab.md").write_text("\n".join(L))
    with (out / "rubric_ab.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=AB_RUBRIC)
        w.writeheader()
        for cid, _, _ in CASES:
            w.writerow({"case_id": cid} | {k: "" for k in AB_RUBRIC[1:]})
    kp = ROOT / "data" / "cache" / "pharmacist_ab_key.json"
    kp.parent.mkdir(parents=True, exist_ok=True)
    kp.write_text(json.dumps({"seed": args.seed, "provider": provider, "key": key}, indent=2) + "\n")
    print(f"Wrote {out / 'cases_ab.md'} and {out / 'rubric_ab.csv'}; key in {kp} (not committed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
