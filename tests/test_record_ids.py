"""Citation IDs must not depend on row order in the raw files."""
from __future__ import annotations

from collections import defaultdict

import pandas as pd
import pytest

from src.data import loaders

RAW = {
    "twosides": (loaders.load_twosides, "csv", pd.DataFrame({
        "drug_1_rxnorm_id": [1191, 29046, 11289, 11289, 1191],
        "drug_1_concept_name": ["Aspirin", "Lisinopril", "Warfarin", "Warfarin", "Aspirin"],
        "drug_2_rxnorm_id": [11289, 9997, 5640, 5640, 11289],
        "drug_2_concept_name": ["Warfarin", "Spironolactone", "Ibuprofen", "Ibuprofen", "Warfarin"],
        "condition_meddra_id": [10019016, 10020646, 10019016, 10019016, 10019016],
        "condition_concept_name": ["hemorrhage", "hyperkalemia", "hemorrhage", "hemorrhage", "hemorrhage"],
        "PRR": [18.7, 14.2, 15.6, 15.6, 3.0],          # rows 3 and 4 are exact duplicates
        "mean_reporting_frequency": [0.06, 0.05, 0.04, 0.04, 0.01],
    })),
    "ddinter": (loaders.load_ddinter, "csv", pd.DataFrame({
        "DDInterID_A": ["DDInter1", "DDInter2", "DDInter3"], "Drug_A": ["Warfarin", "Lisinopril", "Digoxin"],
        "DDInterID_B": ["DDInter9", "DDInter8", "DDInter7"], "Drug_B": ["Aspirin", "Spironolactone", "Amiodarone"],
        "Level": ["Major", "Major", "Unknown"], "Mechanism": ["bleeding", "hyperkalemia", None],
    })),
    "sider": (loaders.load_sider_side_effects, "tsv", pd.DataFrame([
        ["CID1", "CID1s", "C1", "PT", "C0017181", "Gastrointestinal hemorrhage"],
        ["CID2", "CID2s", "C2", "PT", "C0020461", "Hyperkalemia"],
        ["CID2", "CID2s", "C2", "LLT", "C0020461", "Hyperkalaemia"],
    ])),
    "ade": (loaders.load_ade_corpus, "csv", pd.DataFrame({
        "text": ["Atorvastatin caused rhabdomyolysis.", "Warfarin led to bleeding."],
        "drug": ["atorvastatin", "warfarin"], "effect": ["rhabdomyolysis", "bleeding"],
    })),
    "webmd": (loaders.load_webmd_reviews, "csv", pd.DataFrame({
        "Drug": ["lisinopril", "metformin"], "Condition": ["htn", "dm2"],
        "Reviews": ["Dry cough after a month.", "GI upset early on."], "Sides": ["cough", "nausea"],
        "Effectiveness": [4, 5], "Satisfaction": [3, 4],
    })),
    "uci": (loaders.load_uci_reviews, "csv", pd.DataFrame({
        "uniqueID": [1, 2], "drugName": ["metformin", "lisinopril"], "condition": ["dm2", "htn"],
        "review": ["Helped my sugars.", "Cough."], "rating": [8, 6],
    })),
}


def _load(tmp_path, name, df):
    loader, kind, _ = RAW[name]
    path = tmp_path / f"{name}.{kind}"
    if kind == "tsv":
        df.to_csv(path, sep="\t", header=False, index=False)
    else:
        df.to_csv(path, index=False)
    return loader(path)


def _ids_by_content(df):
    out = defaultdict(list)
    content = [c for c in df.columns if c != "record_id"]
    for row in df.itertuples(index=False):
        d = row._asdict()
        out[tuple(str(d[c]) for c in content)].append(d["record_id"])
    return {k: sorted(v) for k, v in out.items()}


@pytest.mark.parametrize("name", sorted(RAW))
def test_shuffled_raw_input_produces_same_ids(tmp_path, name):
    raw = RAW[name][2]
    a = _load(tmp_path, name, raw)
    b = _load(tmp_path, name, raw.iloc[::-1])  # reversed: every row changes position
    assert a["record_id"].is_unique
    assert _ids_by_content(a) == _ids_by_content(b)


def test_twosides_ids_do_not_depend_on_prr_threshold(tmp_path):
    raw = RAW["twosides"][2]
    path = tmp_path / "twosides.csv"
    raw.to_csv(path, index=False)
    strict = loaders.load_twosides(path, min_prr=15.0)
    loose = loaders.load_twosides(path, min_prr=2.0)
    strict_ids, loose_ids = _ids_by_content(strict), _ids_by_content(loose)
    assert strict_ids and all(loose_ids[k] == v for k, v in strict_ids.items())


def test_sample_ids_are_unchanged(sample_pipeline):
    rec = sample_pipeline.retriever.interactions.retrieve_pair("lisinopril", "spironolactone")
    by_id = {r.record_id: r for r in rec}
    assert by_id["TS-00000006"].condition == "hyperkalemia"
    assert by_id["TS-00000006"].prr == pytest.approx(14.2)
