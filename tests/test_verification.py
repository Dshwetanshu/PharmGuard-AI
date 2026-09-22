"""Semantic report checker: evidence adapter, parser, claim and report checks."""
from __future__ import annotations

import json

import pytest

from src.evaluation.checker_fixtures import FAULTS, SCENARIOS, STYLES, evidence_for, render
from src.verification import Evidence, build_evidence, validate_report
from src.verification.lexicon import claimed_tiers, unsupported_mechanisms
from src.verification.parser import parse_report

CARDIAC, ANTICOAG, RENAL = SCENARIOS


# ---------- evidence adapter ----------

def test_evidence_is_json_serializable_and_round_trips():
    ev = evidence_for(CARDIAC)
    blob = json.dumps(ev.to_dict())           # no tuple keys, no dataclass objects
    back = Evidence.from_dict(json.loads(blob))
    assert back.to_dict() == ev.to_dict()
    assert {r.kind for r in ev.records.values()} == {"interaction", "faers"}
    assert ev.records["ddinter:FX-0001"].mechanism.startswith("Verapamil inhibits P-glycoprotein")


def test_citation_lookup_is_case_insensitive_on_source_only():
    ev = evidence_for(CARDIAC)
    assert ev.get("ddinter", "FX-0001") is ev.get("DDINTER", "FX-0001") is not None
    assert ev.get("DDInter", "fx-0001") is None


def test_sample_pipeline_evidence_includes_side_effects_and_aliases(sample_pipeline):
    r = sample_pipeline.run(["Prinivil", "spironolactone"], use_llm=False)
    names = [d.generic_name for d in r.plan.resolved]
    ev = build_evidence(r.plan, r.retrieval, sample_pipeline.normalizer.aliases_for(names))
    assert ev.aliases["prinivil"] == "lisinopril"
    assert any(rec.kind == "side_effect" for rec in ev.records.values())
    json.dumps(ev.to_dict())


# ---------- parser ----------

def test_parser_sections_citations_and_aliases():
    report = ("## Major Findings\n"
              "Calan (verapamil) raises digoxin levels. [DDInter:FX-0001; TWOSIDES:FX-0005]\n"
              "## Coverage Notes\n### No Curated Interaction Data\n- digoxin + metformin\n")
    units = parse_report(report, evidence_for(CARDIAC).aliases).units
    assert units[0].section == "major"
    assert [c.record_id for c in units[0].citations] == ["FX-0001", "FX-0005"]  # citation-only fragment merged
    assert units[0].drugs == ["verapamil", "digoxin"]
    assert units[1].section == "no_data"


# ---------- lexicon guards ----------

def test_isoform_aware_mechanism_matching():
    assert unsupported_mechanisms("via CYP3A4", "inhibits CYP3A") == []
    assert unsupported_mechanisms("via CYP3A", "inhibits CYP3A4") == []
    assert unsupported_mechanisms("via CYP2D6", "inhibits CYP3A4") == ["CYP2D6"]
    assert unsupported_mechanisms("via CYP3A4", "inhibits P-glycoprotein") == ["CYP3A4"]
    assert unsupported_mechanisms("P-gp efflux", "inhibits P-glycoprotein") == []


def test_event_word_minor_is_not_a_severity_tier():
    assert claimed_tiers("sertraline + warfarin: minor bleeding") == set()
    assert claimed_tiers("a moderate-severity signal") == {"Moderate"}
    assert claimed_tiers("Severity: Major") == {"Major"}


# ---------- claim checks on real template output ----------

@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_clean_fixture_reports_pass(scenario, style):
    v = validate_report(render(scenario, style=style), evidence_for(scenario))
    assert v.passed, v.findings


def test_canonical_pgp_report_claiming_cyp3a4_is_caught():
    report = render(CARDIAC).replace("inhibits P-glycoprotein", "inhibits CYP3A4")
    v = validate_report(report, evidence_for(CARDIAC))
    assert [f.code for f in v.findings] == ["UNSUPPORTED_MECHANISM"]
    assert "CYP3A4" in v.findings[0].message
    assert v.stats["semantic_hallucination_rate"] > 0


@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_each_fault_type_is_detected_on_first_site(fault):
    fn, code = FAULTS[fault]
    for s in SCENARIOS:
        sites = fn(s, "template")
        if sites:
            _, report = sites[0]
            assert code in validate_report(report, evidence_for(s)).codes()
            return
    pytest.fail(f"no injection site for {fault}")


def test_no_interaction_data_phrase_is_not_conflated_absence():
    base = render(ANTICOAG, style="prose")
    assert "No interaction data available in the queried sources for amiodarone + sertraline." in base
    assert validate_report(base, evidence_for(ANTICOAG)).passed


def test_report_level_omission_disclaimer_and_unresolved():
    ev = evidence_for(RENAL)
    report = render(RENAL)
    stripped = "\n".join(ln for ln in report.splitlines()
                         if "FX-0202" not in ln and "zzz_fx_unknown" not in ln)
    stripped = stripped.split("\n---\n")[0]
    codes = validate_report(stripped, ev).codes()
    assert {"OMITTED_INTERACTION", "MISSING_UNRESOLVED_DECLARATION", "MISSING_DISCLAIMER"} <= codes
    assert "MISSING_DISCLAIMER" not in validate_report(stripped, ev, final=False).codes()


def test_stats_on_clean_report():
    s = validate_report(render(CARDIAC), evidence_for(CARDIAC)).stats
    assert (s["semantic_hallucination_rate"], s["uncited_claim_rate"], s["citation_validity"]) == (0.0, 0.0, 1.0)
    assert (s["pair_omission_rate"], s["major_omission_rate"], s["completeness"]) == (0.0, 0.0, 1.0)


def test_all_48_template_reports_have_zero_findings(sample_pipeline):
    from src.evaluation.test_cases import TEST_CASES

    failures = {}
    for case in TEST_CASES:
        r = sample_pipeline.run(case.input_drugs, use_llm=False)
        v = validate_report(r.report, sample_pipeline.evidence(r.plan, r.retrieval))
        if not v.passed:
            failures[case.case_id] = [(f.code, f.message) for f in v.findings]
    assert failures == {}


def test_verification_package_uses_standard_library_only():
    import ast
    import sys
    from pathlib import Path

    pkg = Path(__file__).resolve().parent.parent / "src" / "verification"
    for path in pkg.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                top = name.split(".")[0]
                assert top in sys.stdlib_module_names or top in ("src", "__future__"), f"{path.name}: {name}"
