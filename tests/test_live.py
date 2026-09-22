"""Opt-in live checks against free public APIs (no keys). Run: pytest --run-live -m live"""
from __future__ import annotations

import pytest

from src.config import Config
from src.data.normalizer import DrugNormalizer
from src.retrieval.faers_retriever import FaersRetriever

pytestmark = pytest.mark.live


@pytest.fixture
def live_normalizer(sample_pipeline):
    cfg = Config()
    cfg.paths.data_dir = sample_pipeline.cfg.paths.data_dir
    cfg.retrieval.rxnorm_api_enabled = True
    return DrugNormalizer(cfg).load()


def test_live_rxnorm_maps_brand_to_local_generic(live_normalizer):
    r = live_normalizer.resolve("jantoven")
    assert (r.resolved, r.generic_name, r.method) == (True, "warfarin", "rxnorm_api")


def test_live_rxnorm_rejects_nonsense(live_normalizer):
    assert not live_normalizer.resolve("definitely_not_a_drug_xyz").resolved


def test_live_faers_returns_signals_for_common_pair():
    signals = FaersRetriever(enabled=True).retrieve_pair("warfarin", "aspirin")
    assert signals and all(s.record_id.startswith("FAERS-") for s in signals)
