"""LLMClient request shape for the Anthropic provider (fake SDK client, no network)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.config import Config
from src.llm import LLMClient, LLMError


class FakeMessages:
    def __init__(self, stop_reason="end_turn", text="## Summary\nok"):
        self.kwargs = None
        self.stop_reason, self.text = stop_reason, text

    def create(self, **kwargs):
        self.kwargs = kwargs
        content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.text)]
        return SimpleNamespace(content=content, stop_reason=self.stop_reason)


def _client(monkeypatch, **fake):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.delenv("PHARMGUARD_LLM_MODEL", raising=False)
    cfg = Config()
    cfg.llm.provider = "anthropic"
    client = LLMClient(cfg)
    client._client = SimpleNamespace(messages=FakeMessages(**fake))
    return client


def test_default_anthropic_model_is_current(monkeypatch):
    assert _client(monkeypatch).model == "claude-sonnet-5"


def test_anthropic_request_omits_sampling_params(monkeypatch):
    # Sonnet 5 rejects temperature/top_p/top_k with a 400.
    client = _client(monkeypatch)
    assert client.complete("sys", [{"role": "user", "content": "hi"}]) == "## Summary\nok"
    kwargs = client._client.messages.kwargs
    assert "temperature" not in kwargs and "top_p" not in kwargs
    assert kwargs["max_tokens"] >= 16000


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_incomplete_responses_raise(monkeypatch, stop_reason):
    client = _client(monkeypatch, stop_reason=stop_reason)
    with pytest.raises(LLMError, match=stop_reason):
        client.complete("sys", [{"role": "user", "content": "hi"}])
