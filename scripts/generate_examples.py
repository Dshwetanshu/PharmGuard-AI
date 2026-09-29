"""Regenerate examples/*.md: PharmGuard's deterministic report for 9 scenarios on the public build.

    python scripts/generate_examples.py            # needs data/profiles/public (docs/DATASETS.md)

The output is what https://pharmguard.web.app returns for the same input (deterministic mode), plus the
graph's path. A realdata test (pytest --run-realdata) fails if the files are stale.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.attribution import notices_for_dir  # noqa: E402
from src.graph import PharmGuardGraph, Settings  # noqa: E402

OUT = ROOT / "examples"
EXAMPLES = [
    ("01_geriatric_polypharmacy", "7-drug geriatric list",
     ["lisinopril", "spironolactone", "metformin", "atorvastatin", "aspirin", "omeprazole", "sertraline"],
     "21 pairs checked; curated grades, ungraded DDInter listings."),
    ("02_warfarin_nsaid", "Warfarin + ibuprofen", ["warfarin", "ibuprofen"], "A textbook Major interaction."),
    ("03_post_mi_regimen", "Post-MI regimen",
     ["aspirin", "clopidogrel", "atorvastatin", "metoprolol", "lisinopril", "omeprazole"],
     "Includes clopidogrel + omeprazole."),
    ("04_afib_regimen", "AFib regimen", ["warfarin", "digoxin", "amiodarone", "atorvastatin", "lisinopril"],
     "Several Major findings involving amiodarone."),
    ("05_brand_names_misspellings", "Brand names, a misspelling, mixed case", ["Lipitor", "metfromin", "XANAX", "Prilosec"],
     "How each entry was read: brands, a spelling match flagged for checking."),
    ("06_ungraded_listing", "A pair DDInter lists without a grade", ["acetaminophen", "levothyroxine"],
     "Listed, but not graded: the report says so rather than calling it safe or dangerous."),
    ("07_single_drug", "Single drug", ["warfarin"], "Fewer than 2 drugs: no pairs to check."),
    ("08_unresolved_and_ambiguous", "An unknown name, an ambiguous name and a combination product",
     ["lisinopril", "warfarin", "fictional_drug_xyz", "insulin", "Percocet"], "Nothing is silently dropped or guessed."),
    ("09_no_curated_data", "Pairs with no curated record", ["escitalopram", "amoxicillin", "melatonin"],
     "Declared as no data, which is not evidence of safety."),
]


def render(graph, title: str, drugs, note: str) -> str:
    s = graph.run(drugs)
    path = " → ".join(t["node"] for t in s["trajectory"])
    v = s["final_validation"]
    return "\n".join([
        f"# {title}", "", note, "", "## Input", "", "```", *drugs, "```", "",
        "## Output (deterministic report, public build)", "", s["report"], "",
        "## How it was produced", "",
        f"- Graph path: {path}", f"- report_source: `{s['report_source']}`",
        f"- Final checker: {'passed' if v['passed'] else 'FAILED'}, {v['stats']['clinical_claims']} clinical claims, "
        f"{v['stats']['citations']} citations", ""])


def index(graph) -> str:
    L = ["# Example outputs", "",
         "PharmGuard's deterministic reports for 9 scenarios on the **public build** (the data the live app uses: "
         "https://pharmguard.web.app). Regenerate with `python scripts/generate_examples.py`; a realdata test checks "
         "they are current.", "", "| File | Scenario |", "|---|---|"]
    L += [f"| [{f}.md]({f}.md) | {t}: {n} |" for f, t, _, n in EXAMPLES]
    L += ["", "## Data sources and attribution", ""]
    L += [f"- **{n.title}.** {n.text}" for n in notices_for_dir(graph.settings.to_config().paths.processed_dir)]
    return "\n".join(L) + "\n"


def build(graph):
    files = {f"{f}.md": render(graph, t, d, n) for f, t, d, n in EXAMPLES}
    files["README.md"] = index(graph)
    return files


def main() -> int:
    data_dir = ROOT / "data" / "profiles" / "public"
    if not (data_dir / "processed" / "provenance.json").exists():
        sys.exit("needs the public build (docs/DATASETS.md)")
    graph = PharmGuardGraph(Settings(data_dir=data_dir, mode="deterministic", rxnorm_enabled=False, faers_enabled=False))
    for old in OUT.glob("*.md"):
        old.unlink()
    for name, text in build(graph).items():
        (OUT / name).write_text(text)
    print(f"Wrote {len(EXAMPLES)} examples and README.md to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
