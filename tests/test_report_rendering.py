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
    p = _pipeline(sample_pipeline, faers=StubFaers())
    result = p.run(["metformin", "levothyroxine"], use_llm=False)
    assert result.retrieval.no_data_pairs == [("levothyroxine", "metformin")]
    assert result.retrieval.total_faers_signals == 1
    if use_llm:  # the LLM path itself (the pipeline guardrail is tested separately)
        report = Generator(sample_pipeline.cfg, llm=StubLLM()).generate(result.plan, result.retrieval)
    else:
        report = result.report
    assert "all pairs had coverage" not in report.lower()
    assert "FAERS Spontaneous Reports (unvalidated)" in report
    assert "[FAERS:FAERS-abc123]" in report
    assert "600" in report


# ---------- ungraded severity ----------

def _ungraded_case(sample_pipeline):
    from src.agents.retriever import RetrievalResult
    from src.retrieval.interaction_retriever import InteractionRecord

    plan = Planner().plan(sample_pipeline.normalizer.resolve_many(["warfarin", "digoxin"]))
    rec = InteractionRecord("DDI-00009999", "digoxin", "warfarin", None, None,
                            "interaction", "Unknown", None, None, "DDInter")
    return plan, RetrievalResult(interactions={("digoxin", "warfarin"): [rec]})


def test_unknown_severity_is_shown_as_not_graded(sample_pipeline):
    plan, result = _ungraded_case(sample_pipeline)
    report = Generator(sample_pipeline.cfg).generate_deterministic(plan, result)
    assert "## Severity Not Graded" in report
    assert "[DDInter:DDI-00009999]" in report


def test_llm_is_told_about_ungraded_records(sample_pipeline):
    plan, result = _ungraded_case(sample_pipeline)
    llm = StubLLM()
    Generator(sample_pipeline.cfg, llm=llm).generate(plan, result)
    system, messages = llm.calls[0]
    assert "Severity Not Graded" in system
    assert "severity=not graded" in messages[0]["content"]


# ---------- disclaimer ----------

@pytest.mark.parametrize("llm_text", [
    "## Summary\nThe word disclaimer appears here, but no actual disclaimer.",
    "## Summary\nok\n\n---\n**Disclaimer.** {disclaimer}",   # model echoes the canonical text
    "## Summary\nok\n\n{disclaimer}\n\n{disclaimer}",       # ...even twice
])
def test_llm_report_has_canonical_disclaimer_exactly_once(sample_pipeline, llm_text):
    disclaimer = sample_pipeline.cfg.disclaimer
    r = sample_pipeline.run(["aspirin", "warfarin"], use_llm=False)
    llm = StubLLM(llm_text.format(disclaimer=disclaimer))
    report = Generator(sample_pipeline.cfg, llm=llm).generate(r.plan, r.retrieval)
    assert report.count(disclaimer) == 1
    assert report.rstrip().endswith(disclaimer)


def test_template_report_has_canonical_disclaimer_exactly_once(sample_pipeline):
    report = sample_pipeline.run(["aspirin", "warfarin"], use_llm=False).report
    assert report.count(sample_pipeline.cfg.disclaimer) == 1


# ---------- coverage notes ----------

def test_template_lists_every_no_data_pair_and_unresolved_input(sample_pipeline):
    drugs = ["lisinopril", "spironolactone", "metformin", "atorvastatin",
             "aspirin", "omeprazole", "sertraline", "fictional_drug_xyz"]
    result = sample_pipeline.run(drugs, use_llm=False)
    report = result.report
    assert len(result.retrieval.no_data_pairs) == 16
    assert "### No Curated Interaction Data" in report
    for a, b in result.retrieval.no_data_pairs:
        assert f"\n- {a} + {b}\n" in report
    assert "### Unresolved Inputs" in report and "\n- fictional_drug_xyz\n" in report
    assert "..." not in report


def test_source_mechanism_is_quoted_verbatim_in_both_paths(sample_pipeline):
    mech = "ACE inhibition + K-sparing diuretic → hyperkalemia risk"
    report = sample_pipeline.run(["lisinopril", "spironolactone"], use_llm=False).report
    assert f'source mechanism: "{mech}" [DDInter:DDI-00000003]' in report

    llm = StubLLM()
    r = sample_pipeline.run(["lisinopril", "spironolactone"], use_llm=False)
    Generator(sample_pipeline.cfg, llm=llm).generate(r.plan, r.retrieval)
    assert f'mechanism="{mech}"' in llm.calls[0][1][0]["content"]
