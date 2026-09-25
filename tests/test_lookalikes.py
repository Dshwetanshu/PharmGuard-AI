"""Dangerous near-misses (blind trial, step 8b): a real name resolves to itself; a misspelling
close to two real drugs comes back ambiguous, never silently resolved; fuzzy matching can't
land on a substance the loaded data has no records for (Coumadin -> coumarin).

The small vocabulary here mirrors the real one (brand aliases, look-alike pairs); the same
checks run against the public build in tests/test_realdata.py.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.config import Config
from src.data.normalizer import DrugNormalizer

ALIASES = [("warfarin", "warfarin"), ("coumadin", "warfarin"), ("coumarin", "coumarin"),
           ("fluconazole", "fluconazole"), ("diflucan", "fluconazole"),
           ("celecoxib", "celecoxib"), ("celebrex", "celecoxib"), ("fosphenytoin", "fosphenytoin"),
           ("cerebyx", "fosphenytoin"), ("hydroxyzine", "hydroxyzine"), ("hydralazine", "hydralazine"),
           ("tramadol", "tramadol"), ("trazodone", "trazodone"), ("clonidine", "clonidine"),
           ("clonazepam", "clonazepam"), ("klonopin", "clonazepam"), ("inulin", "inulin"),
           ("insulin glargine", "insulin glargine"), ("insulin lispro", "insulin lispro"),
           ("metformin", "metformin"), ("amoxicillin", "amoxicillin")]
VOCAB = pd.DataFrame([(n, g, None, None) for n, g in ALIASES],
                     columns=["name_lower", "generic_name", "rxcui", "drugbank_id"])
# Drugs with records in the loaded data: everything except coumarin and inulin.
IN_DATA = {g for _, g in ALIASES} - {"coumarin", "inulin"}


@pytest.fixture(scope="module")
def n():
    cfg = Config()
    cfg.retrieval.rxnorm_api_enabled = False
    return DrugNormalizer(cfg).load_from_dataframe(VOCAB).set_fuzzy_targets(IN_DATA)


@pytest.mark.parametrize("name,expected", [
    ("Coumadin", "warfarin"), ("Celebrex", "celecoxib"), ("Cerebyx", "fosphenytoin"),
    ("hydroxyzine", "hydroxyzine"), ("hydralazine", "hydralazine"), ("tramadol", "tramadol"),
    ("trazodone", "trazodone"), ("clonidine", "clonidine"), ("Klonopin", "clonazepam"),
    ("coumarin", "coumarin"),          # a real name still resolves to itself by exact match
])
def test_real_names_resolve_to_themselves(n, name, expected):
    r = n.resolve(name)
    assert (r.resolved, r.generic_name, r.method) == (True, expected, "exact")


@pytest.mark.parametrize("misspelling,pair", [
    ("Celebyx", {"celecoxib", "fosphenytoin"}), ("Cerebrex", {"celecoxib", "fosphenytoin"}),
    ("hydroxalazine", {"hydralazine", "hydroxyzine"}), ("tramadone", {"tramadol", "trazodone"}),
    ("Klonidin", {"clonidine", "clonazepam"}),
])
def test_misspelling_between_two_real_drugs_is_ambiguous(n, misspelling, pair):
    r = n.resolve(misspelling)
    assert (r.resolved, r.generic_name, r.method) == (False, None, "fuzzy_ambiguous"), r
    assert all(p in r.note for p in pair), r.note


def test_fuzzy_matching_never_lands_on_a_drug_without_records(n):
    for q in ("Coumadine", "coumadn", "coumarn"):
        assert n.resolve(q).generic_name != "coumarin", q
    assert n.resolve("Coumadine").generic_name == "warfarin"
    r = n.resolve("insulin")
    assert r.method == "fuzzy_ambiguous" and "inulin" not in r.note
    assert r.note.startswith("ambiguous name; matching drugs: insulin lispro / insulin glargine")


def test_clear_misspellings_still_resolve_and_say_so(n):
    for q, g in (("warfrin", "warfarin"), ("flucanazole", "fluconazole"), ("metfromin", "metformin")):
        r = n.resolve(q)
        assert (r.generic_name, r.method) == (g, "fuzzy"), q


def test_every_unresolved_input_has_a_reason(n):
    r = n.resolve("xyz123")
    assert not r.resolved and r.note.startswith("not found: check the spelling or enter the generic name")
