"""What the user sees: FAERS signals, ungraded severities, disclaimer.

Both report paths are covered: the deterministic template and the LLM path
(with a stub LLM, so no API key or network is needed).
"""
from __future__ import annotations

import pytest

from src.agents.generator import Generator
from src.agents.planner import Planner
from src.agents.retriever import Retriever
from src.pipeline import PharmGuardPipeline
from src.retrieval.faers_retriever import FaersRecord


class StubFaers:
    enabled = True

    def retrieve_pair(self, a, b):
        return [FaersRecord("FAERS-abc123", a, b, "nausea", 600, "Major")]


class StubLLM:
    def __init__(self, text="## Summary\nStub report."):
        self.text = text
        self.calls = []

    def complete(self, system, messages, **kwargs):
        self.calls.append((system, messages))
        return self.text


def _pipeline(sample_pipeline, faers=None, llm=None):
    base = sample_pipeline.retriever
    retriever = Retriever(base.interactions, base.side_effects, faers_retriever=faers)
    cfg = sample_pipeline.cfg
    return PharmGuardPipeline(sample_pipeline.normalizer, Planner(), retriever, Generator(cfg, llm=llm), cfg=cfg)


# ---------- FAERS ----------

@pytest.mark.parametrize("use_llm", [False, True])
def test_faers_pairs_stay_no_data_and_are_shown_as_unvalidated(sample_pipeline, use_llm):
    # metformin + levothyroxine has no curated record in the sample data.
    p = _pipeline(sample_pipeline, faers=StubFaers(), llm=StubLLM())
    result = p.run(["metformin", "levothyroxine"], use_llm=use_llm)
    assert result.trace["generator"] == ("llm" if use_llm else "deterministic")

    assert result.retrieval.no_data_pairs == [("levothyroxine", "metformin")]
    assert result.retrieval.total_faers_signals == 1
    report = result.report
    assert "all pairs had coverage" not in report.lower()
    assert "FAERS Spontaneous Reports (unvalidated)" in report
    assert "[FAERS:FAERS-abc123]" in report
    assert "600" in report
