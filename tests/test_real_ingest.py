"""ingest_real on the real-format fixtures (offline): profiles, integrity reports, provenance."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from src.data.provenance import provenance_line
from src.data.real_ingest import ingest_real

FX = Path(__file__).resolve().parent / "fixtures" / "realformat"


@pytest.fixture(scope="module")
def raw(tmp_path_factory):
    raw = tmp_path_factory.mktemp("raw")
    for d in ("rxnorm", "ddinter", "sider", "twosides"):
        shutil.copytree(FX / d, raw / d)
    return raw


@pytest.fixture(scope="module")
def builds(raw, tmp_path_factory):
    out = {}
    for profile in ("public", "research"):
        d = tmp_path_factory.mktemp(profile)
        out[profile] = (ingest_real(raw, d, profile), d / "processed")
    return out


def test_public_build_has_no_twosides(builds):
    report, processed = builds["public"]
    inter = pd.read_parquet(processed / "interactions.parquet")
    assert set(inter.source) == {"DDInter"} and "twosides" not in report["sources"]
    prov = json.loads((processed / "provenance.json").read_text())
    assert (prov["profile"], prov["synthetic"], prov["not_for_redistribution"]) == ("public", False, False)
    line = provenance_line(processed)
    assert line.startswith("Data: public build from RxNorm Current Prescribable") and "TWOSIDES" not in line


def test_research_build_adds_twosides_and_says_so(builds):
    report, processed = builds["research"]
    inter = pd.read_parquet(processed / "interactions.parquet")
    assert set(inter.source) == {"DDInter", "TWOSIDES"}
    assert "TWOSIDES (research only; not for redistribution)" in provenance_line(processed)
    assert json.loads((processed / "provenance.json").read_text())["not_for_redistribution"] is True


def test_per_source_integrity_reports_unmatched(builds):
    report, processed = builds["research"]
    dd = report["sources"]["ddinter"]
    assert dd["unmatched_names"] == 1 and dd["top_unmatched"] == [["acyclovir (topical)", 1]]
    assert (processed / "unmatched_ddinter.csv").read_text().splitlines()[1] == "acyclovir (topical),1"
    assert report["sources"]["twosides"]["top_unmatched"] == [("zzzdrug", 1)]
    assert report["sources"]["sider"]["top_unmatched"] == [["simvastatin", 1]]
    assert report["join_integrity"]["issues"] == []


def test_real_names_map_onto_canonical_pairs(builds):
    _, processed = builds["public"]
    inter = pd.read_parquet(processed / "interactions.parquet")
    pairs = {(a, b, s) for a, b, s in zip(inter.drug_a_name, inter.drug_b_name, inter.severity)}
    assert ("aspirin", "warfarin", "Major") in pairs                  # "Acetylsalicylic acid" -> aspirin
    assert ("albuterol", "propranolol", "Moderate") in pairs          # "Salbutamol" -> albuterol
    lithium = inter[(inter.drug_a_name == "hydrochlorothiazide") & (inter.drug_b_name == "lithium")]
    assert sorted(lithium.severity) == ["Major", "Unknown"]           # carbonate and citrate records both kept
    assert inter.mechanism.isna().all()


def test_pipeline_runs_on_a_real_format_build(builds):
    from src.graph import PharmGuardGraph, Settings

    _, processed = builds["public"]
    g = PharmGuardGraph(Settings(data_dir=processed.parent, mode="deterministic"))
    s = g.run(["Lipitor", "Percocet", "salbutamol", "propranolol"])
    assert s["final_validation"]["passed"], s["final_validation"]["findings"]
    assert "combination product: acetaminophen + oxycodone" in s["report"]
    assert "[DDInter:DDI-" in s["report"] and "Data: public build from" in s["report"]


def test_real_build_states_no_mechanisms_and_checker_rejects_any(builds):
    """DDInter bulk files have no mechanism text: the prompt says so, and any mechanism fails."""
    from src.agents.generator import Generator
    from src.graph import PharmGuardGraph, Settings
    from src.verification import validate_report

    _, processed = builds["public"]
    g = PharmGuardGraph(Settings(data_dir=processed.parent, mode="deterministic"))
    s = g.run(["aspirin", "warfarin"])
    assert "mechanism" not in s["report"].lower().split("---")[0]      # the template states none

    class Capture:
        last_usage = None

        def complete(self, system, messages, **kw):
            self.user = messages[0]["content"]
            return "## Summary\nok"

    from src.graph.serde import plan_from_dict, result_from_dict
    llm = Capture()
    Generator(g.components.generator.cfg, llm=llm).generate(plan_from_dict(s["plan"]), result_from_dict(s["retrieval"]))
    assert "None of the records below has mechanism text" in llm.user

    body = s["report"].split("\n---\n")[0]
    line = next(ln for ln in body.splitlines() if "[DDInter:" in ln)
    for injected in (" via CYP2C9 inhibition", " through platelet inhibition", " by displacing it from protein binding"):
        bad = body.replace(line, line.replace(" [DDInter:", injected + " [DDInter:"))
        from src.verification import Evidence
        v = validate_report(g.components.generator.finalize(bad), Evidence.from_dict(s["evidence"]))
        assert "UNSUPPORTED_MECHANISM" in v.codes(), injected
