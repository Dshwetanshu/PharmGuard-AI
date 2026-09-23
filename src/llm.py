"""Unified LLM client.

Wraps Anthropic, OpenAI, and Gemini under a single .complete(system, messages) API
so the rest of the codebase is provider-agnostic.
"""
from __future__ import annotations

import os
from typing import List, Dict, Optional

from src.config import Config, config as default_config


class LLMError(RuntimeError):
    """Configuration or response problems (missing key, refusal, truncation). Not transient."""


# Transient failures by SDK class name (Anthropic and OpenAI share these names),
# matched against the exception's MRO so SDK subclasses count too.
_TRANSIENT_CLASSES = {
    "APITimeoutError", "APIConnectionError", "RateLimitError", "InternalServerError",
    "OverloadedError", "ServiceUnavailableError", "TimeoutError", "ConnectionError",
}


def is_transient_llm_error(exc: BaseException) -> bool:
    """True for errors worth retrying: timeouts, connection errors, rate limits,
    overloaded / 5xx. Auth, invalid-request (4xx) and LLMError are not."""
    if isinstance(exc, LLMError):
        return False
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in (408, 409, 429) or status >= 500
    return any(cls.__name__ in _TRANSIENT_CLASSES for cls in type(exc).__mro__)


class LLMClient:
    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or default_config
        self.provider = self.cfg.llm.provider
        self.model = self.cfg.llm.resolved_model()
        self._client = self._build_client()
        self.last_usage: Optional[Dict[str, int]] = None  # token usage of the last call, if reported

    # ---------- provider dispatch ----------

    def _build_client(self):
        if self.provider == "anthropic":
            key = os.getenv("ANTHROPIC_API_KEY")
            if not key:
                raise LLMError("ANTHROPIC_API_KEY not set. See .env.example.")
            import anthropic
            return anthropic.Anthropic(api_key=key)

        if self.provider == "openai":
            key = os.getenv("OPENAI_API_KEY")
            if not key:
                raise LLMError("OPENAI_API_KEY not set.")
            import openai
            return openai.OpenAI(api_key=key)

        if self.provider == "gemini":
            key = os.getenv("GOOGLE_API_KEY")
            if not key:
                raise LLMError("GOOGLE_API_KEY not set.")
            import google.generativeai as genai
            genai.configure(api_key=key)
            return genai.GenerativeModel(self.model)

        raise LLMError(f"Unknown provider: {self.provider}")

    def wrap_sdk_client(self, wrapper) -> None:
        """Replace the SDK client with a wrapped one (tracing), e.g. langsmith.wrappers.wrap_anthropic."""
        self._client = wrapper(self._client)

    # ---------- public API ----------

    def complete(
        self,
        system: str,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Return a text completion given a system prompt and conversation history.

        messages: [{"role": "user"|"assistant", "content": "..."}]
        """
        t = self.cfg.llm.temperature if temperature is None else temperature
        mt = self.cfg.llm.max_tokens if max_tokens is None else max_tokens

        if self.provider == "anthropic":
            from src.observability import active
            # Child span when no SDK instrumentor covers the call (tracing off: no-op).
            with active().llm(self.provider, self.model, [{"role": "system", "content": system}, *messages]) as rec:
                # No temperature: Sonnet 5 rejects sampling parameters (400).
                resp = self._client.messages.create(
                    model=self.model,
                    system=system,
                    messages=messages,
                    max_tokens=mt,
                )
                usage = getattr(resp, "usage", None)
                self.last_usage = ({"input_tokens": int(usage.input_tokens),
                                    "output_tokens": int(usage.output_tokens)} if usage is not None else None)
                if resp.stop_reason in ("refusal", "max_tokens"):
                    # A refused or truncated report must not be shown; the pipeline
                    # falls back to the deterministic template.
                    raise LLMError(f"Anthropic response incomplete: stop_reason={resp.stop_reason}")
                text = "".join(block.text for block in resp.content if block.type == "text")
                rec(usage=self.last_usage, output=text)
                return text

        if self.provider == "openai":
            full = [{"role": "system", "content": system}] + messages
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=full,
                temperature=t,
                max_tokens=mt,
            )
            usage = getattr(resp, "usage", None)
            self.last_usage = ({"input_tokens": int(usage.prompt_tokens), "output_tokens": int(usage.completion_tokens)}
                               if usage is not None else None)
            return resp.choices[0].message.content or ""

        if self.provider == "gemini":
            # Gemini handles system prompt via prepending to first turn
            joined = system + "\n\n" + "\n".join(
                f"{m['role'].upper()}: {m['content']}" for m in messages
            )
            resp = self._client.generate_content(
                joined,
                generation_config={
                    "temperature": t,
                    "max_output_tokens": mt,
                },
            )
            return resp.text or ""

        raise LLMError(f"Unknown provider: {self.provider}")
