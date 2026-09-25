"""Validate the report checker (src/verification) and write results/checker_validation.{json,md}.

Usage:
    python scripts/validate_checker.py                      # sample + fixtures -> results/checker_validation.*
    python scripts/validate_checker.py --profile public     # real build -> results/checker_validation_public.*

1. False positives: the deterministic template report for every evaluation
   cases (synthetic sample data), plus clean fixture reports in two styles
   (template bullets and LLM-style prose), must produce zero findings.
2. Sensitivity: known faults are injected into clean fixture reports
   (synthetic FX- records); detection = the expected finding code is raised.
3. Blind spots: fabrications worded outside the lexicons, expected to be
   missed. They document that the lexicon checks are a lower bound.

With --profile public|research, only false positives are measured, on the
template reports of a real build (data/profiles/<profile>): the evaluation
cases plus a seeded stress set of random 4-drug lists drawn from drugs with
interaction records (real names: commas, parentheses, long RxNorm names). For
the research build only counts are written (finding messages quote TWOSIDES
record text, which stays local).

Offline, no API key, deterministic output.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["PHARMGUARD_RXNORM_API_ENABLED"] = "false"
os.environ["PHARMGUARD_FAERS_ENABLED"] = "false"

from src.config import Config  # noqa: E402
from src.data.ingestion import Ingester  # noqa: E402
from src.evaluation.checker_fixtures import (  # noqa: E402
    BLIND_SPOTS, FAULTS, SCENARIOS, STYLES, evidence_for, render,
)
from src.data.provenance import data_stamp  # noqa: E402
from src.evaluation.test_cases import TEST_CASES  # noqa: E402
from src.pipeline import PharmGuardPipeline  # noqa: E402
from src.verification import validate_report  # noqa: E402

COMMAND = "python scripts/validate_checker.py"


def false_positives_on_sample() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config()
        cfg.paths.data_dir = Path(tmp) / "data"
        shutil.copytree(ROOT / "data" / "sample", cfg.paths.data_dir / "sample")
        Ingester(cfg).ingest_sample()
        pipeline = PharmGuardPipeline.from_config(cfg)
        by_code: Counter = Counter()
        failing = {}
        clinical = 0
        for case in TEST_CASES:
            r = pipeline.run(case.input_drugs, use_llm=False)
            v = validate_report(r.report, pipeline.evidence(r.plan, r.retrieval))
            clinical += v.stats["clinical_claims"]
            if v.findings:
                failing[case.case_id] = [f.__dict__ for f in v.findings]
                by_code.update(f.code for f in v.findings)
    return {"reports": len(TEST_CASES), "clinical_claims_checked": clinical,
            "reports_with_findings": len(failing), "findings": sum(by_code.values()),
            "by_code": dict(by_code), "failing_cases": failing}


def _fp_run(pipeline, drug_lists, names) -> dict:
    by_code: Counter = Counter()
    failing = {}
    clinical = 0
    for name, drugs in zip(names, drug_lists):
        r = pipeline.run(drugs, use_llm=False)
        v = validate_report(r.report, pipeline.evidence(r.plan, r.retrieval))
        clinical += v.stats["clinical_claims"]
        if v.findings:
            failing[name] = {"drugs": drugs, "findings": [f.__dict__ for f in v.findings]}
            by_code.update(f.code for f in v.findings)
    return {"reports": len(drug_lists), "clinical_claims_checked": clinical,
            "reports_with_findings": len(failing), "findings": sum(by_code.values()),
            "by_code": dict(by_code), "failing_cases": failing}


def false_positives_on_profile(profile: str, stress: int, seed: int = 7) -> dict:
    cfg = Config()
    cfg.paths.data_dir = ROOT / "data" / "profiles" / profile
    pipeline = PharmGuardPipeline.from_config(cfg)
    cases = _fp_run(pipeline, [c.input_drugs for c in TEST_CASES], [c.case_id for c in TEST_CASES])
    table = pipeline.retriever.interactions.table
    drugs = sorted(set(table.drug_a_name) | set(table.drug_b_name))
    rng = random.Random(seed)
    lists = [rng.sample(drugs, 4) for _ in range(stress)]
    stressed = _fp_run(pipeline, lists, [f"stress-{i:03d}" for i in range(stress)])
    stressed.update(seed=seed, drugs_per_list=4, drawn_from=f"{len(drugs):,} drugs with interaction records")
    # Every name with a comma, a parenthesis or more than 30 characters, with its most-connected partners.
    hard = [d for d in drugs if "," in d or "(" in d or len(d) > 30]
    degree = Counter(table.drug_a_name) + Counter(table.drug_b_name)
    partners = {d: set(table.drug_b_name[table.drug_a_name == d]) | set(table.drug_a_name[table.drug_b_name == d])
                for d in hard}
    hard_lists = [[d] + sorted(partners[d], key=lambda x: (-degree[x], x))[:3] for d in hard]
    hard_run = _fp_run(pipeline, hard_lists, [f"hard-{i:03d}" for i in range(len(hard_lists))])
    hard_run.update(names=len(hard), rule="name has a comma, a parenthesis or > 30 characters; "
                                          "listed with its 3 most-connected interaction partners")
    return {"data": {**data_stamp(cfg.paths.processed_dir), "data_dir": f"data/profiles/{profile}"},
            "evaluation_cases": cases, "stress": stressed, "hard_names": hard_run}


def profile_markdown(profile: str, res: dict) -> str:
    st = res["data"]
    lines = [f"# Report checker false positives: {profile} build", "",
             f"Regenerate with `python scripts/validate_checker.py --profile {profile}`. Offline, no API key.",
             f"{st['data'].rstrip('.')}; provenance.json sha256 `{st['provenance_sha256']}`.", "",
             "Template reports on real data; every finding on a clean template report is a false positive "
             "(target 0). Sensitivity is measured on the FX- fixtures (results/checker_validation.md).", "",
             "| Report set | Reports | Clinical claims checked | Reports with findings | Findings |",
             "|---|---:|---:|---:|---:|"]
    for label, key in ((f"{len(TEST_CASES)} evaluation cases", "evaluation_cases"),
                       (f"stress: random 4-drug lists (seed {res['stress']['seed']})", "stress"),
                       ("hard names (comma, parenthesis or > 30 chars) + 3 partners each", "hard_names")):
        r = res[key]
        lines.append(f"| {label} | {r['reports']} | {r['clinical_claims_checked']} | {r['reports_with_findings']} "
                     f"| {r['findings']} |")
    codes = sum((Counter(res[k]["by_code"]) for k in ("evaluation_cases", "stress", "hard_names")), Counter())
    lines += ["", "Findings by code: " + (", ".join(f"`{k}` {v}" for k, v in sorted(codes.items())) or "none"), ""]
    return "\n".join(lines)


def false_positives_on_fixtures() -> dict:
    out = {}
    for style in STYLES:
        for s in SCENARIOS:
            v = validate_report(render(s, style=style), evidence_for(s))
            out[f"{style}/{s.name}"] = {"clinical_claims": v.stats["clinical_claims"],
                                        "findings": [f.__dict__ for f in v.findings]}
    return out


def sensitivity() -> dict:
    out = {}
    for style in STYLES:
        rows = {}
        for name, (inject, expected) in FAULTS.items():
            n = hit = hit_any = 0
            missed = []
            for s in SCENARIOS:
                ev = evidence_for(s)
                for site, report in inject(s, style):
                    n += 1
                    codes = validate_report(report, ev).codes()
                    hit += expected in codes
                    hit_any += bool(codes)
                    if expected not in codes:
                        missed.append({"scenario": s.name, "site": site, "codes": sorted(codes)})
            rows[name] = {"expected_code": expected, "injected": n, "detected": hit,
                          "detection_rate": round(hit / n, 4) if n else None,
                          "any_finding_rate": round(hit_any / n, 4) if n else None, "missed": missed}
        out[style] = rows
    return out


def blind_spots() -> dict:
    ev = evidence_for(SCENARIOS[0])
    out = {}
    for style in STYLES:
        out[style] = {}
        for name, (make, expected) in BLIND_SPOTS.items():
            codes = sorted(validate_report(make(style), ev).codes())
            out[style][name] = {"expected_code_if_caught": expected, "detected": expected in codes, "codes": codes}
    return out


def to_markdown(res: dict) -> str:
    fp, fx = res["false_positives"]["sample_template_reports"], res["false_positives"]["fixture_clean_reports"]
    lines = [
        "# Report checker validation",
        "",
        f"Regenerate with `{COMMAND}`. Offline, no API key; all data is synthetic "
        f"(sample CSVs for the {len(TEST_CASES)} cases, `FX-` fixture records for fault injection).",
        "",
        "The mechanism, event and population checks use hand-written lexicons, so detection "
        "is a **lower bound**: the blind-spot probes below are fabrications the checker is known "
        "to miss. An LLM judge is planned as a later layer.",
        "",
        "## False positives (clean reports; target 0)",
        "",
        "| Report set | Reports | Clinical claims checked | Reports with findings | Findings |",
        "|---|---:|---:|---:|---:|",
        f"| Template, {len(TEST_CASES)} evaluation cases (sample data) | {fp['reports']} | {fp['clinical_claims_checked']} "
        f"| {fp['reports_with_findings']} | {fp['findings']} |",
    ]
    for style in STYLES:
        rows = {k: v for k, v in fx.items() if k.startswith(style + "/")}
        lines.append(f"| Fixtures, {style} style | {len(rows)} | {sum(v['clinical_claims'] for v in rows.values())} "
                     f"| {sum(bool(v['findings']) for v in rows.values())} "
                     f"| {sum(len(v['findings']) for v in rows.values())} |")
    lines += ["", "## Sensitivity (injected faults on FX- fixtures)", "",
              "Detection = the expected finding code is raised. These rates show each check works on "
              "the fault it targets. They are **not** an estimate of how many real LLM errors are caught: "
              "the injected faults use terms from the checker's own lexicons by construction, and the "
              f"fixtures are small ({len(SCENARIOS)} scenarios, {sum(len(s.records) for s in SCENARIOS)} records).", "",
              "| Fault | Expected code | " + " | ".join(f"{s}: detected / injected" for s in STYLES) + " |",
              "|---|---|" + "---:|" * len(STYLES)]
    for name, (_, code) in FAULTS.items():
        cells = []
        for style in STYLES:
            r = res["sensitivity"][style][name]
            cells.append(f"{r['detected']}/{r['injected']} ({r['detection_rate']:.0%})")
        lines.append(f"| {name} | `{code}` | " + " | ".join(cells) + " |")
    lines += ["", "## Blind-spot probes (expected to be missed)", "",
              "| Probe | " + " | ".join(f"{s}: caught?" for s in STYLES) + " |", "|---|" + "---|" * len(STYLES)]
    for name in BLIND_SPOTS:
        lines.append(f"| {name} | " + " | ".join(
            "yes" if res["blind_spots"][s][name]["detected"] else "no" for s in STYLES) + " |")
    lines += ["", "The canonical case (`canonical_pgp_to_cyp3a4`): fixture record `FX-0001` says "
              "\"Verapamil inhibits P-glycoprotein, raising digoxin levels\"; the mutated report claims "
              "CYP3A4 with the same, real citation.", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile", choices=["sample", "public", "research"], default="sample")
    ap.add_argument("--stress", type=int, default=200, help="Random drug lists for a real profile.")
    args = ap.parse_args()
    if args.profile != "sample":
        res = false_positives_on_profile(args.profile, args.stress)
        if args.profile == "research":   # counts only: finding messages quote TWOSIDES record text
            for key in ("evaluation_cases", "stress", "hard_names"):
                res[key]["failing_cases"] = sorted(res[key]["failing_cases"])
            res["aggregate_only"] = True
        out = ROOT / "results"
        (out / f"checker_validation_{args.profile}.json").write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
        (out / f"checker_validation_{args.profile}.md").write_text(profile_markdown(args.profile, res))
        for key in ("evaluation_cases", "stress", "hard_names"):
            r = res[key]
            print(f"{args.profile} {key}: {r['reports']} reports, {r['clinical_claims_checked']} claims, "
                  f"{r['findings']} finding(s) {r['by_code']}")
        return
    res = {
        "command": COMMAND,
        "false_positives": {"sample_template_reports": false_positives_on_sample(),
                            "fixture_clean_reports": false_positives_on_fixtures()},
        "sensitivity": sensitivity(),
        "blind_spots": blind_spots(),
    }
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "checker_validation.json").write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    (out / "checker_validation.md").write_text(to_markdown(res))
    fp = res["false_positives"]["sample_template_reports"]
    print(f"False positives on {len(TEST_CASES)} template reports: {fp['findings']} finding(s)")
    for style in STYLES:
        rates = {k: v["detection_rate"] for k, v in res["sensitivity"][style].items()}
        print(f"Sensitivity ({style}): {rates}")
    print(f"Wrote {out / 'checker_validation.json'} and {out / 'checker_validation.md'}")


if __name__ == "__main__":
    main()
