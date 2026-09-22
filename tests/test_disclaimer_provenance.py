"""Disclaimer wording and the data-provenance line appended to every report."""
from __future__ import annotations

import json

from src.agents.generator import Generator
from src.config import Config
from src.data.provenance import provenance_line

NEW_DISCLAIMER = (
    "PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. "
    "It reports only what its loaded data contains; absence of data is not evidence of safety."
)
SAMPLE_LINE = "Data: synthetic sample dataset (85 interaction records), not real clinical data."


class StubLLM:
    def complete(self, system, messages, **kw):
        return "## Summary\nok"


def test_disclaimer_no_longer_claims_public_databases():
    assert Config().disclaimer == NEW_DISCLAIMER


def test_sample_ingest_records_provenance(sample_pipeline, sample_ingest_report):
    processed = sample_pipeline.cfg.paths.processed_dir
    data = json.loads((processed / "provenance.json").read_text())
    assert (data["mode"], data["interaction_records"], data["synthetic"]) == ("sample", 85, True)
    assert provenance_line(processed) == SAMPLE_LINE


def test_missing_provenance_is_stated_not_guessed(tmp_path):
    assert provenance_line(tmp_path) == "Data: no ingestion record found; data provenance unknown."


def test_both_report_paths_end_with_disclaimer_then_provenance(sample_pipeline):
    r = sample_pipeline.run(["aspirin", "warfarin"], use_llm=False)
    llm_report = Generator(sample_pipeline.cfg, llm=StubLLM()).generate(r.plan, r.retrieval)
    for report in (r.report, llm_report):
        assert report.endswith(f"---\n**Disclaimer.** {NEW_DISCLAIMER}\n\n{SAMPLE_LINE}")
        assert report.count(NEW_DISCLAIMER) == 1 and report.count(SAMPLE_LINE) == 1


def test_finalize_is_idempotent(sample_pipeline):
    gen = sample_pipeline.generator
    report = sample_pipeline.run(["aspirin", "warfarin"], use_llm=False).report
    assert gen.finalize(report) == report
    assert gen.finalize(gen.finalize(report)) == report
