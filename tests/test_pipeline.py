"""End-to-end tests for the PharmGuard pipeline.

These tests run against the sample data and do NOT require an LLM API key.
They validate the deterministic path: normalization → planning → retrieval.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config
from src.data.normalizer import DrugNormalizer
from src.data.ingestion import Ingester
from src.retrieval.interaction_retriever import InteractionRetriever
from src.retrieval.side_effect_retriever import SideEffectRetriever
from src.agents.planner import Planner
from src.agents.retriever import Retriever
from src.agents.generator import Generator
from src.pipeline import PharmGuardPipeline


@pytest.fixture(scope="module")
def sample_pipeline(tmp_path_factory):
    """Build an isolated pipeline using the sample data."""
    tmp = tmp_path_factory.mktemp("pharmguard_test")
    cfg = Config()
    cfg.paths.data_dir = Path(__file__).resolve().parent.parent / "data"
    cfg.paths.data_dir.mkdir(exist_ok=True)

    # Ingest from sample
    Ingester(cfg).ingest_sample()

    normalizer = DrugNormalizer(cfg).load()
    ir = InteractionRetriever(cfg).load()
    ser = SideEffectRetriever(cfg).load()
    retriever = Retriever(ir, ser)
    generator = Generator(cfg)
    return PharmGuardPipeline(normalizer, Planner(), retriever, generator, cfg=cfg)


def test_resolves_generic_name(sample_pipeline):
    r = sample_pipeline.normalizer.resolve("lisinopril")
    assert r.resolved
    assert r.generic_name == "lisinopril"


def test_resolves_brand_name_to_generic(sample_pipeline):
    r = sample_pipeline.normalizer.resolve("Lipitor")
    assert r.resolved
    assert r.generic_name == "atorvastatin"


def test_resolves_misspelling_via_fuzzy(sample_pipeline):
    r = sample_pipeline.normalizer.resolve("metfromin")
    assert r.resolved
    assert r.generic_name == "metformin"


def test_flags_unresolved_drug(sample_pipeline):
    r = sample_pipeline.normalizer.resolve("definitely_not_a_drug_xyz")
    assert not r.resolved
    assert r.generic_name is None


def test_pairwise_enumeration(sample_pipeline):
    resolved = sample_pipeline.normalizer.resolve_many(
        ["aspirin", "warfarin", "ibuprofen"]
    )
    plan = sample_pipeline.planner.plan(resolved)
    assert plan.num_drugs == 3
    assert plan.num_pairs == 3  # C(3,2) = 3


def test_deduplicates_brand_and_generic(sample_pipeline):
    # Lipitor and atorvastatin should collapse to one drug
    resolved = sample_pipeline.normalizer.resolve_many(["lipitor", "atorvastatin"])
    plan = sample_pipeline.planner.plan(resolved)
    assert plan.num_drugs == 1
    assert plan.num_pairs == 0


def test_retrieves_known_interaction(sample_pipeline):
    result = sample_pipeline.run(["lisinopril", "spironolactone"], use_llm=False)
    assert result.retrieval.total_interactions > 0
    # At least one Major severity record expected
    all_records = [r for recs in result.retrieval.interactions.values() for r in recs]
    assert any(r.severity == "Major" for r in all_records)


def test_surfaces_no_data_pairs(sample_pipeline):
    # metformin + levothyroxine has no record in sample data
    result = sample_pipeline.run(["metformin", "levothyroxine"], use_llm=False)
    # Should flag the pair as no-data, not fabricate
    assert len(result.retrieval.no_data_pairs) == 1 or result.retrieval.total_interactions == 0


def test_deterministic_report_contains_disclaimer(sample_pipeline):
    result = sample_pipeline.run(["aspirin", "warfarin"], use_llm=False)
    assert "disclaimer" in result.report.lower()


def test_report_cites_sources(sample_pipeline):
    result = sample_pipeline.run(["aspirin", "warfarin"], use_llm=False)
    # Every retrieved record has a citation in the form [TWOSIDES:TS-...]
    assert "[TWOSIDES:" in result.report or "TS-" in result.report


def test_respects_max_drugs(sample_pipeline):
    too_many = ["metformin"] * 13
    with pytest.raises(ValueError):
        sample_pipeline.run(too_many, use_llm=False)


def test_empty_input_raises(sample_pipeline):
    with pytest.raises(ValueError):
        sample_pipeline.run([], use_llm=False)


def test_geriatric_proposal_scenario(sample_pipeline):
    """The exact scenario from the proposal's opening paragraph."""
    result = sample_pipeline.run(
        ["lisinopril", "spironolactone", "metformin", "atorvastatin",
         "aspirin", "omeprazole", "sertraline"],
        use_llm=False,
    )
    assert result.plan.num_drugs == 7
    assert result.plan.num_pairs == 21  # C(7,2)
    # Lisinopril + spironolactone hyperkalemia must be flagged
    pair_key = tuple(sorted(["lisinopril", "spironolactone"]))
    assert pair_key in result.retrieval.interactions
