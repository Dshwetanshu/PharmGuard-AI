"""Shared pytest fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

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


@pytest.fixture(scope="session")
def sample_ingest_report():
    """Ingest the sample data once per session and return the ingestion report."""
    cfg = Config()
    cfg.paths.data_dir = Path(__file__).resolve().parent.parent / "data"
    return Ingester(cfg).ingest_sample()


@pytest.fixture(scope="module")
def sample_pipeline(sample_ingest_report):
    """Build a pipeline over the ingested sample data."""
    cfg = Config()
    cfg.paths.data_dir = Path(__file__).resolve().parent.parent / "data"
    normalizer = DrugNormalizer(cfg).load()
    ir = InteractionRetriever(cfg).load()
    ser = SideEffectRetriever(cfg).load()
    retriever = Retriever(ir, ser)
    generator = Generator(cfg)
    return PharmGuardPipeline(normalizer, Planner(), retriever, generator, cfg=cfg)
