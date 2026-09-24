"""Checks on the real-data builds (opt-in: pytest --run-realdata).

Needs: python scripts/fetch_data.py --with-twosides
       python scripts/ingest_data.py --full --profile public
       python scripts/ingest_data.py --full --profile research
No network: sockets stay blocked; this reads data/profiles/<profile>/processed only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.evaluation.test_cases import TEST_CASES

pytestmark = pytest.mark.realdata
ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "data" / "profiles"

def _processed(profile):
    p = PROFILES / profile / "processed"
    if not (p / "provenance.json").exists():
        pytest.skip(f"no {profile} build at {p}")
    return p


@pytest.fixture(scope="module")
def public_graph():
    from src.graph import PharmGuardGraph, Settings
    return PharmGuardGraph(Settings(data_dir=_processed("public").parent, mode="deterministic"))


def test_public_provenance_names_sources_with_hashes():
    prov = json.loads((_processed("public") / "provenance.json").read_text())
    assert (prov["profile"], prov["synthetic"], prov["not_for_redistribution"]) == ("public", False, False)
    assert prov["source_order"] == ["rxnorm", "ddinter", "sider"] and prov["join_integrity_issues"] == 0
    for key in prov["source_order"]:
        files = prov["sources"][key]["files"]
        assert files and all(len(f["sha256"]) == 64 and f["url"].startswith("http") for f in files), key


def test_public_build_contains_no_twosides():
    inter = pd.read_parquet(_processed("public") / "interactions.parquet", columns=["source"])
    assert set(inter.source) == {"DDInter"}


def test_research_build_is_marked_not_for_redistribution():
    p = _processed("research")
    prov = json.loads((p / "provenance.json").read_text())
    assert prov["not_for_redistribution"] is True and "twosides" in prov["sources"]
    assert prov["sources"]["twosides"]["filters"]["min_prr"] == 2.0


def test_every_evaluation_input_resolves_in_the_real_vocabulary(public_graph):
    n = public_graph.components.normalizer
    wrong = []
    for case in TEST_CASES:
        resolved, unresolved = case.expectations("public")
        for q in case.input_drugs:
            r = n.resolve(q)
            if q in unresolved:
                ok = not r.resolved
            else:
                ok = r.resolved and r.generic_name == resolved.get(q, " ".join(q.split()).lower())
            if not ok:
                wrong.append((case.case_id, q, r.generic_name, r.method))
    assert wrong == []


def test_insulin_is_ambiguous_but_a_specific_insulin_resolves(public_graph):
    n = public_graph.components.normalizer
    generic = n.resolve("insulin")
    assert generic.method == "fuzzy_ambiguous" and "enter the specific drug" in generic.note
    for q, expected in [("insulin glargine", "insulin glargine"), ("Lantus", "insulin glargine"),
                        ("insulin lispro", "insulin lispro")]:
        r = n.resolve(q)
        assert (r.resolved, r.generic_name) == (True, expected), (q, r)
    s = public_graph.run(["insulin", "metoprolol"])
    assert "- insulin — ambiguous name; closest matches:" in s["report"]


def test_inn_names_from_ddinter_reach_the_report(public_graph):
    s = public_graph.run(["albuterol", "propranolol"])      # DDInter says "Salbutamol"
    assert "[DDInter:DDI-" in s["report"] and s["final_validation"]["passed"]
