"""Runtime guardrail: an LLM report reaches the user only if it passes validation."""
from __future__ import annotations

import json

from src.agents.generator import SYSTEM_PROMPT, Generator
from src.agents.planner import Planner
from src.pipeline import PharmGuardPipeline

DRUGS = ["lisinopril", "spironolactone", "aspirin"]


class StubLLM:
    def __init__(self, text):
        self.text = text

    def complete(self, system, messages, **kw):
        return self.text


def _pipeline(sample_pipeline, text):
    cfg = sample_pipeline.cfg
    return PharmGuardPipeline(sample_pipeline.normalizer, Planner(), sample_pipeline.retriever,
                              Generator(cfg, llm=StubLLM(text)), cfg=cfg)


def _faithful_llm_text(sample_pipeline):
    # A report that obeys every rule: reuse the template's content, as prose-free
    # bullets, so the stub stands in for a well-behaved model.
    return sample_pipeline.run(DRUGS, use_llm=False).report.split("\n---\n")[0]


def test_valid_llm_report_is_returned(sample_pipeline):
    text = _faithful_llm_text(sample_pipeline) + "\n\nThe pairing warrants potassium monitoring [DDInter:DDI-00000003]."
    result = _pipeline(sample_pipeline, text).run(DRUGS, use_llm=True)
    assert result.trace["report_source"] == "llm"
    assert result.trace["llm_validation"]["passed"] is True
    assert "potassium monitoring" in result.report


def test_fabricated_mechanism_falls_back_to_template(sample_pipeline):
    text = _faithful_llm_text(sample_pipeline).replace(
        "hyperkalemia (PRR=14.20)", "hyperkalemia via CYP3A4 inhibition (PRR=14.20)")
    result = _pipeline(sample_pipeline, text).run(DRUGS, use_llm=True)
    assert result.trace["report_source"] == "deterministic_fallback"
    assert result.trace["fallback_reason"] == "validation_failed"
    codes = [f["code"] for f in result.trace["llm_validation"]["findings"]]
    assert codes == ["UNSUPPORTED_MECHANISM"]
    assert "CYP3A4" not in result.report
    assert result.report == sample_pipeline.run(DRUGS, use_llm=False).report


def test_deterministic_path_and_trace_is_json(sample_pipeline):
    result = sample_pipeline.run(DRUGS, use_llm=False)
    assert result.trace["report_source"] == "deterministic"
    json.dumps(result.trace)


def test_system_prompt_states_the_checked_rules():
    for phrase in ("[SOURCE:RECORD_ID]", "### No Curated Interaction Data", "### Unresolved Inputs",
                   "Severity Not Graded", "PRR", "P-glycoprotein", "elderly", "not evidence of safety",
                   "discarded"):
        assert phrase in SYSTEM_PROMPT, phrase
