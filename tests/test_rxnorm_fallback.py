"""RxNorm live fallback: only accept confident matches that map back to local data.

All HTTP is stubbed. Payload shapes mirror real approximateTerm responses
captured on 2026-09-22 (e.g. the nonsense query returned only NDDF/MMSL/MTHSPL
candidates with no RxNorm name, at score ~10.5).
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.config import Config
from src.data.normalizer import DrugNormalizer
from src.data.rxnorm_api import RxNormApiResolver


def _cand(rxcui, score, name=None, source="RXNORM"):
    c = {"rxcui": rxcui, "score": str(score), "rank": "1", "source": source}
    if name:
        c["name"] = name
    return c


PAYLOADS = {
    "definitely_not_a_drug_xyz": [
        _cand("835748", 10.496, source="NDDF"),
        _cand("2593843", 9.337, source="MMSL"),
        _cand("1595027", 8.350, "TULATHROMYCIN A 485 g in 500 g NOT APPLICABLE POWDER [X]", "MTHSPL"),
    ],
    "jantoven": [_cand("352318", 12.4, source="MMSL"), _cand("352318", 12.4, "Jantoven")],
    "weakbrand": [_cand("99999", 6.0, "Weakbrand")],
    "ziagen": [_cand("284393", 12.9, "Ziagen")],
}
INGREDIENTS = {"352318": "warfarin", "99999": "warfarin", "284393": "abacavir"}


@pytest.fixture
def stub_fetch(monkeypatch):
    calls = []

    def fake_fetch(self, url):
        calls.append(url)
        if "approximateTerm" in url:
            term = url.split("term=")[1].split("&")[0]
            return {"approximateGroup": {"candidate": PAYLOADS.get(term, [])}}
        if "/related.json" in url:
            rxcui = url.split("/rxcui/")[1].split("/")[0]
            name = INGREDIENTS.get(rxcui)
            groups = [{"tty": "IN", "conceptProperties": [{"name": name}]}] if name else []
            return {"relatedGroup": {"conceptGroup": groups}}
        return {}

    monkeypatch.setattr(RxNormApiResolver, "_fetch", fake_fetch)
    return calls


@pytest.fixture
def normalizer(sample_pipeline):
    cfg = Config()
    cfg.retrieval.rxnorm_api_enabled = True
    cfg.retrieval.min_confidence = 10.0
    vocab = pd.read_parquet(sample_pipeline.cfg.paths.processed_dir / "drug_vocabulary.parquet")
    return DrugNormalizer(cfg).load_from_dataframe(vocab)


def test_nonsense_input_stays_unresolved(normalizer, stub_fetch):
    r = normalizer.resolve("definitely_not_a_drug_xyz")
    assert stub_fetch, "the API fallback should have been consulted"
    assert not r.resolved
    assert r.generic_name is None


def test_confident_brand_maps_back_to_local_generic(normalizer, stub_fetch):
    r = normalizer.resolve("Jantoven")
    assert (r.resolved, r.generic_name, r.method) == (True, "warfarin", "rxnorm_api")
    assert r.confidence == pytest.approx(12.4)


def test_match_below_threshold_is_rejected(normalizer, stub_fetch):
    r = normalizer.resolve("weakbrand")
    assert not r.resolved and r.generic_name is None


def test_real_drug_without_local_data_is_unresolved_not_invented(normalizer, stub_fetch):
    # RxNorm knows abacavir, but nothing in the local tables does.
    r = normalizer.resolve("ziagen")
    assert not r.resolved
    assert r.generic_name is None
    assert r.method == "rxnorm_not_in_local_vocab"


def test_min_confidence_env_var_is_wired(monkeypatch):
    monkeypatch.setenv("PHARMGUARD_MIN_CONFIDENCE", "11.5")
    assert Config().retrieval.min_confidence == 11.5
