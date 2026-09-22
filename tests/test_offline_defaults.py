"""Tests must run offline and without API keys unless explicitly marked live."""
from __future__ import annotations

import urllib.request

import pytest

from src.config import Config


def test_default_test_config_disables_live_fallbacks():
    cfg = Config()
    assert cfg.retrieval.rxnorm_api_enabled is False
    assert cfg.retrieval.faers_enabled is False


def test_network_is_blocked_in_unmarked_tests():
    with pytest.raises(Exception, match="network access is disabled"):
        urllib.request.urlopen("https://rxnav.nlm.nih.gov/REST/version.json", timeout=3)


def test_llm_path_without_key_falls_back_to_template(sample_pipeline):
    result = sample_pipeline.run(["aspirin", "warfarin"], use_llm=True)
    assert result.trace["report_source"] == "deterministic_fallback"
    assert result.trace["fallback_reason"] == "llm_error: LLMError"
