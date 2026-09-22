"""Shared pytest fixtures and the offline test harness.

Every test runs offline and without LLM keys unless it is marked
``@pytest.mark.live`` and pytest is run with ``--run-live``.
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

# Must run before anything imports src.*: src.config reads the environment
# (and .env via load_dotenv) at import time. Keys are set to "" rather than
# deleted so load_dotenv(), which never overrides existing variables, cannot
# fill them in from a developer's .env.
os.environ["PHARMGUARD_RXNORM_API_ENABLED"] = "false"
os.environ["PHARMGUARD_FAERS_ENABLED"] = "false"
for _key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
    os.environ[_key] = ""

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


def pytest_addoption(parser):
    parser.addoption("--run-live", action="store_true", default=False,
                     help="run tests marked 'live' (real network calls to free public APIs)")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: makes real network calls; skipped unless --run-live")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skip = pytest.mark.skip(reason="live test; run with --run-live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _block_network(request, monkeypatch):
    """Fail fast on any outbound TCP connection from an unmarked test."""
    if "live" in request.keywords:
        return
    real_connect = socket.socket.connect

    def guarded_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError(f"network access is disabled in tests (tried {address!r}); "
                               "stub the call or mark the test @pytest.mark.live")
        return real_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


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
