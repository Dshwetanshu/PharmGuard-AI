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
    assert prov["source_order"] == ["rxnorm", "drugsatfda", "ddinter", "sider"] and prov["join_integrity_issues"] == 0
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
    assert "- insulin — ambiguous name; matching drugs: insulin" in s["report"]
    assert "inulin" not in s["report"]


def test_inn_names_from_ddinter_reach_the_report(public_graph):
    s = public_graph.run(["albuterol", "propranolol"])      # DDInter says "Salbutamol"
    assert "[DDInter:DDI-" in s["report"] and s["final_validation"]["passed"]


def test_public_build_has_all_14_ddinter_atc_files():
    prov = json.loads((_processed("public") / "provenance.json").read_text())
    names = sorted(f["name"] for f in prov["sources"]["ddinter"]["files"])
    assert names == [f"ddinter_downloads_code_{c}.csv" for c in "ABCDGHJLMNPRSV"]


@pytest.mark.parametrize("pair", [("lisinopril", "spironolactone"), ("aspirin", "warfarin"),
                                  ("hydrochlorothiazide", "lithium")])
def test_well_known_curated_pairs_are_present(public_graph, pair):
    s = public_graph.run(list(pair))
    assert s["retrieval"]["interactions"], pair
    assert "curated severity:" in s["report"] and s["final_validation"]["passed"]


def test_research_report_separates_signals_and_counts_hidden_ones():
    from src.graph import PharmGuardGraph, Settings
    g = PharmGuardGraph(Settings(data_dir=_processed("research").parent, mode="deterministic"))
    s = g.run(["warfarin", "aspirin", "simvastatin", "clarithromycin"])
    report = s["report"]
    assert "## Statistical reporting signals (not graded for clinical severity)" in report
    assert s["final_validation"]["passed"], s["final_validation"]["findings"]
    for x in s["retrieval"]["interactions"]:
        signals = [r for r in x["records"] if r["source"] == "TWOSIDES"]
        assert len(signals) <= 3
    hidden = s["retrieval"]["hidden_signals"]
    for h in hidden:
        assert f"+{h['count']} more not shown" in report


def test_attribution_notices_follow_the_build():
    from src.data.attribution import notices_for_dir
    pub = [n.key for n in notices_for_dir(_processed("public"))]
    res = [n.key for n in notices_for_dir(_processed("research"))]
    assert "twosides" not in pub and "twosides" in res
    assert {"ddinter", "sider", "rxnorm", "openfda", "noncommercial"} <= set(pub)


@pytest.mark.parametrize("name,expected", [
    ("Coumadin", "warfarin"), ("Biaxin", "clarithromycin"), ("Lanoxin", "digoxin"), ("Celebrex", "celecoxib"),
    ("Cerebyx", "fosphenytoin"), ("Klonopin", "clonazepam"), ("hydroxyzine", "hydroxyzine"),
    ("hydralazine", "hydralazine"), ("tramadol", "tramadol"), ("trazodone", "trazodone"), ("clonidine", "clonidine"),
])
def test_real_build_brands_and_lookalikes_resolve_to_themselves(public_graph, name, expected):
    r = public_graph.components.normalizer.resolve(name)
    assert (r.resolved, r.generic_name, r.method) == (True, expected, "exact")


@pytest.mark.parametrize("misspelling", ["Celebyx", "Cerebrex", "hydroxalazine", "tramadone", "trazadol",
                                         "klonidine", "Klonidin"])
def test_real_build_lookalike_misspellings_are_ambiguous(public_graph, misspelling):
    r = public_graph.components.normalizer.resolve(misspelling)
    assert (r.resolved, r.method) == (False, "fuzzy_ambiguous"), r


def test_real_build_coumadin_report_finds_warfarin_and_flags_the_duplicate(public_graph):
    s = public_graph.run(["Coumadin", "Diflucan", "warfarin"])
    report = s["report"]
    assert "- Coumadin → warfarin (brand name, Drugs@FDA)" in report
    assert "> **Same drug entered more than once:** Coumadin and warfarin both mean warfarin" in report
    assert "fluconazole + warfarin** — curated severity: Major" in report and "coumarin" not in report
    assert s["final_validation"]["passed"]


def test_real_build_source_names_use_drugsatfda_aliases_only_when_reviewed():
    from src.data.rxnorm import REVIEWED_SOURCE_BRAND_ALIASES, source_aliases
    p = _processed("public")
    vocab = pd.read_parquet(p / "drug_vocabulary.parquet")
    table, missing = source_aliases(vocab)
    assert missing == []
    fda = set(vocab[vocab.kind == "DRUGSATFDA:BRAND"].name_lower)
    assert set(table.name_lower) & fda == set(REVIEWED_SOURCE_BRAND_ALIASES) & fda
    prov = json.loads((p / "provenance.json").read_text())
    assert prov["vocabulary"]["reviewed_source_brand_aliases"] == REVIEWED_SOURCE_BRAND_ALIASES
    se = pd.read_parquet(p / "side_effects.parquet", columns=["drug_name"])
    assert (se.drug_name == "perflutren").any() and not (se.drug_name == "albumin human, usp").any()
    assert "penicillin" in set(pd.read_csv(p / "unmatched_sider.csv").name)


def test_real_build_optison_input_reads_as_perflutren(public_graph):
    r = public_graph.components.normalizer.resolve("Optison")
    assert (r.generic_name, r.alias_kind) == ("perflutren", "REVIEWED_BRAND_OVERRIDE")


def test_real_build_structured_report_matches_markdown(public_graph):
    from tests.test_report_structure import _check
    for case in TEST_CASES:
        s = public_graph.run(case.input_drugs)
        if s["report_source"].startswith("deterministic"):
            _check(s, public_graph.components.generator)
