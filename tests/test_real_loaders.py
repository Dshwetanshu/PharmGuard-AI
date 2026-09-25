"""Real-data loaders against tiny fixture files in each source's real format (offline).

Fixtures: tests/fixtures/realformat/ (hand-written, real RxCUIs/UNIIs, made-up counts).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.data.loaders import load_ddinter, load_drugbank_vocabulary, load_sider, load_twosides_filtered
from src.data.rxnorm import build_rxnorm_vocabulary, merge_drugbank_synonyms

FX = Path(__file__).resolve().parent / "fixtures" / "realformat"


@pytest.fixture(scope="module")
def vocab():
    return build_rxnorm_vocabulary(FX / "rxnorm")


@pytest.fixture(scope="module")
def alias(vocab):
    return dict(zip(vocab.aliases.name_lower, vocab.aliases.generic_name))


# ------------------------------------------------------------------ RxNorm

@pytest.mark.parametrize("name,expected", [
    ("aspirin", "aspirin"),
    ("acetylsalicylic acid", "aspirin"),         # FDA substance name (MTHSPL SU) on the IN's RxCUI
    ("warfarin sodium", "warfarin"),             # PIN has_form IN
    ("atorvastatin calcium", "atorvastatin"),
    ("lipitor", "atorvastatin"),                 # BN has_tradename IN
    ("valproic acid", "valproate"),              # RxNorm's ingredient is valproate
    ("lithium carbonate", "lithium"),            # reviewed SALT_GROUPS entry
    ("lithium citrate", "lithium"),
    ("lithobid", "lithium"),                     # brand of lithium carbonate
    ("potassium chloride", "potassium chloride"),  # no blind salt stripping
    ("albuterol", "albuterol"),
    ("salbutamol", "albuterol"),                 # reviewed INN alias
])
def test_rxnorm_aliases(alias, name, expected):
    assert alias[name] == expected


def test_rxnorm_excludes_suppressed_names_and_clinical_drug_strings(alias):
    assert "obsolete aspirin name" not in alias
    assert "lisinopril 10 mg oral tablet" not in alias


def test_combination_products_name_their_ingredients(vocab, alias):
    combos = dict(zip(vocab.combinations.name_lower, vocab.combinations.ingredients))
    assert combos["percocet"] == "acetaminophen + oxycodone" and "percocet" not in alias


def test_unii_links_substances_to_canonical_names(vocab):
    assert vocab.unii["R16CO5Y76E"] == "aspirin" and vocab.unii["QF8SVZ843E"] == "albuterol"


def test_drugbank_synonyms_join_by_unii(vocab):
    db = load_drugbank_vocabulary(FX / "drugbank" / "drugbank_vocabulary.csv")
    assert "unii" in db.columns
    merged, stats = merge_drugbank_synonyms(vocab, db)
    a = dict(zip(merged.name_lower, merged.generic_name))
    assert a["asa"] == "aspirin" and a["salbutamolum"] == "albuterol" and a["acetylsalicylate"] == "aspirin"
    assert stats["drugbank_rows_without_unii_link"] == 1


# ------------------------------------------------------------------ DDInter

def test_ddinter_real_columns_dedupe_and_no_mechanism():
    df = load_ddinter(sorted((FX / "ddinter").glob("*.csv")))
    assert len(df) == 5     # 7 rows, reversed + exact duplicates across the two files removed
    assert df["mechanism"].isna().all()
    assert set(df["severity"]) == {"Major", "Moderate", "Minor", "Unknown"}
    aspirin = df[df.ddinter_id_a.eq("DDInter1") | df.ddinter_id_b.eq("DDInter1")]
    assert len(aspirin) == 1 and aspirin.iloc[0].severity == "Major"
    assert df.record_id.is_unique and df.record_id.str.startswith("DDI-").all()


def test_ddinter_ids_do_not_depend_on_file_order():
    files = sorted((FX / "ddinter").glob("*.csv"))
    a, b = load_ddinter(files), load_ddinter(list(reversed(files)))
    assert set(a.record_id) == set(b.record_id)


# ----------------------------------------------------------------- TWOSIDES

@pytest.mark.parametrize("chunksize", [1, 2, 1000])
def test_twosides_filters_top_events_and_header_typo(vocab, alias, chunksize):
    df, stats = load_twosides_filtered(FX / "twosides" / "TWOSIDES.csv", alias, vocab.rxcui_to_generic,
                                       chunksize=chunksize)
    aw = df[(df.drug_a_name == "aspirin") & (df.drug_b_name == "warfarin")]
    # 6 valid events (PRR>=2, A>=5, not administrative) + 1 from the reversed row -> top 5 by PRR
    assert list(aw.condition_name) == ["haematoma", "haemorrhage", "gastrointestinal haemorrhage", "anaemia", "melaena"]
    assert aw.drug_a_rxcui.notna().all()                   # typo'd drug_1_rxnorn_id column is read
    assert set(df.drug_a_name) | set(df.drug_b_name) <= {"aspirin", "warfarin", "lisinopril"}
    lw = df[(df.drug_a_name == "lisinopril") & (df.drug_b_name == "warfarin")]
    assert len(lw) == 1                                     # PIN rxcui 114194 mapped to warfarin
    assert stats["rows_read"] == 11 and stats["dropped_prr"] == 1 and stats["dropped_min_reports"] == 1
    assert stats["dropped_administrative"] == 1 and stats["dropped_top_k"] == 1
    assert stats["unmatched_names"] == {"zzzdrug": 1}


def test_twosides_ids_stable_across_chunk_sizes(vocab, alias):
    a, _ = load_twosides_filtered(FX / "twosides" / "TWOSIDES.csv", alias, vocab.rxcui_to_generic, chunksize=3)
    b, _ = load_twosides_filtered(FX / "twosides" / "TWOSIDES.csv", alias, vocab.rxcui_to_generic, chunksize=50)
    assert list(a.record_id) == list(b.record_id)


# -------------------------------------------------------------------- SIDER

def test_sider_joins_drug_names_keeps_pt_and_dedupes():
    df = load_sider(FX / "sider" / "meddra_all_se.tsv.gz", FX / "sider" / "drug_names.tsv")
    aspirin = df[df.drug_name == "aspirin"]
    assert sorted(aspirin.side_effect_name) == ["headache", "nausea"]    # LLT dropped, stereo duplicate merged
    assert set(df.drug_name) == {"aspirin", "simvastatin"}
    assert df.record_id.is_unique


# ------------------------------------------------------- combination products

def test_combination_product_stays_unresolved_and_names_ingredients(vocab, sample_pipeline):
    from src.agents.generator import Generator
    from src.agents.planner import Planner
    from src.agents.retriever import RetrievalResult
    from src.config import Config
    from src.data.normalizer import DrugNormalizer

    cfg = Config()
    cfg.retrieval.rxnorm_api_enabled = False
    n = DrugNormalizer(cfg).load_from_dataframe(vocab.aliases, combinations=vocab.combinations)
    r = n.resolve("Percocet")
    assert (r.resolved, r.generic_name, r.method) == (False, None, "combination_product")
    assert r.note == "combination product: acetaminophen + oxycodone; enter them separately"
    assert n.resolve("lipitor").generic_name == "atorvastatin"
    plan = Planner().plan(n.resolve_many(["Percocet", "warfarin"]))
    report = Generator(sample_pipeline.cfg).generate_deterministic(plan, RetrievalResult())
    assert "- Percocet — combination product: acetaminophen + oxycodone; enter them separately" in report


# ------------------------------------------------- Drugs@FDA aliases vs source tables

def test_source_tables_map_through_drugsatfda_aliases_only_when_reviewed():
    from src.data.rxnorm import REVIEWED_SOURCE_BRAND_ALIASES, source_aliases
    aliases = pd.DataFrame([
        ("warfarin", "warfarin", "11289", None, "RXNORM:IN"),
        ("coumadin", "warfarin", "11289", None, "DRUGSATFDA:BRAND"),        # user input only
        ("newbrand", "warfarin", "11289", None, "DRUGSATFDA:BRAND"),        # a future release
        ("methoxsalen", "methoxsalen", "6854", None, "RXNORM:IN"),
        ("8-mop", "methoxsalen", "6854", None, "DRUGSATFDA:BRAND"),         # reviewed
        ("perflutren", "perflutren", "283753", None, "RXNORM:IN"),
        ("optison", "albumin human, usp", "828529", None, "DRUGSATFDA:BRAND"),  # reviewed -> perflutren
        ("penicillin", "penicillin g", "7980", None, "DRUGSATFDA:BRAND"),   # not reviewed
    ], columns=["name_lower", "generic_name", "rxcui", "drugbank_id", "kind"])
    table, missing = source_aliases(aliases)
    m = dict(zip(table.name_lower, table.generic_name))
    assert "coumadin" not in m and "newbrand" not in m and "penicillin" not in m
    assert m["8-mop"] == "methoxsalen" and m["optison"] == "perflutren"
    assert set(missing) == set(REVIEWED_SOURCE_BRAND_ALIASES) - {"8-mop", "optison"}   # targets absent here
    assert set(table.kind) <= {"RXNORM:IN", "REVIEWED_SOURCE_ALIAS"}


def test_reviewed_brand_override_points_optison_at_perflutren():
    from src.data.rxnorm import apply_brand_overrides
    aliases = pd.DataFrame([
        ("perflutren", "perflutren", "283753", None, "RXNORM:IN"),
        ("albumin human, usp", "albumin human, usp", "828529", None, "RXNORM:IN"),
        ("optison", "albumin human, usp", "828529", None, "DRUGSATFDA:BRAND"),
    ], columns=["name_lower", "generic_name", "rxcui", "drugbank_id", "kind"])
    out, missing = apply_brand_overrides(aliases)
    row = out[out.name_lower == "optison"]
    assert missing == [] and len(row) == 1
    assert (row.iloc[0].generic_name, row.iloc[0].kind, row.iloc[0].rxcui) == ("perflutren", "REVIEWED_BRAND_OVERRIDE", "283753")
    _, missing = apply_brand_overrides(aliases[aliases.name_lower != "perflutren"])
    assert missing == ["optison"]
