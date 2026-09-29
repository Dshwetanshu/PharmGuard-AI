"""LLMClient on the Gemini provider through google-genai (fake SDK client, no network)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.config import Config
from src.llm import LLMClient, LLMError, is_transient_llm_error


class FakeModels:
    def __init__(self, finish_reason="STOP", text="## Summary\nok", usage=True):
        self.kwargs = None
        self.finish_reason, self.text, self.usage = finish_reason, text, usage

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        usage = SimpleNamespace(prompt_token_count=120, candidates_token_count=30) if self.usage else None
        return SimpleNamespace(text=self.text, usage_metadata=usage,
                               candidates=[SimpleNamespace(finish_reason=self.finish_reason)])


def _client(monkeypatch, **fake):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")
    monkeypatch.delenv("PHARMGUARD_LLM_MODEL", raising=False)
    cfg = Config()
    cfg.llm.provider = "gemini"
    client = LLMClient(cfg)
    client._client = SimpleNamespace(models=FakeModels(**fake))
    return client


def test_uses_google_genai_not_the_retired_sdk(monkeypatch):
    from google import genai
    c = _client(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")
    assert isinstance(c._build_client(), genai.Client)
    assert c.model == "gemini-3.8-flash"


def test_request_shape_roles_system_and_usage(monkeypatch):
    c = _client(monkeypatch)
    msgs = [{"role": "user", "content": "evidence"}, {"role": "assistant", "content": "draft"},
            {"role": "user", "content": "fix it"}]
    assert c.complete("SYSTEM", msgs) == "## Summary\nok"
    kw = c._client.models.kwargs
    assert kw["model"] == "gemini-3.8-flash"
    assert [x["role"] for x in kw["contents"]] == ["user", "model", "user"]
    assert kw["contents"][1]["parts"] == [{"text": "draft"}]
    assert kw["config"]["system_instruction"] == "SYSTEM" and "SYSTEM" not in str(kw["contents"])
    assert c.last_usage == {"input_tokens": 120, "output_tokens": 30}


def test_finish_reason_enum_value_is_accepted(monkeypatch):
    from google.genai import types
    assert _client(monkeypatch, finish_reason=types.FinishReason.STOP).complete("s", [{"role": "user", "content": "x"}])


@pytest.mark.parametrize("reason", ["MAX_TOKENS", "SAFETY", "RECITATION"])
def test_truncated_or_blocked_responses_raise(monkeypatch, reason):
    with pytest.raises(LLMError, match=reason):
        _client(monkeypatch, finish_reason=reason).complete("s", [{"role": "user", "content": "x"}])


def test_genai_errors_are_classified_by_http_code():
    from google.genai import errors
    assert is_transient_llm_error(errors.ServerError(503, {"error": {"message": "overloaded"}}))
    assert is_transient_llm_error(errors.ClientError(429, {"error": {"message": "quota"}}))
    assert not is_transient_llm_error(errors.ClientError(400, {"error": {"message": "bad"}}))
    assert not is_transient_llm_error(errors.ClientError(403, {"error": {"message": "key"}}))
