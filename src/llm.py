"""Unified LLM client.

Wraps Anthropic, OpenAI, and Gemini under a single .complete(system, messages) API
so the rest of the codebase is provider-agnostic.
"""
from __future__ import annotations

import os
from typing import List, Dict, Optional

from src.config import Config, config as default_config


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or default_config
        self.provider = self.cfg.llm.provider
        self.model = self.cfg.llm.resolved_model()
        self._client = self._build_client()

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
            resp = self._client.messages.create(
                model=self.model,
                system=system,
                messages=messages,
                temperature=t,
                max_tokens=mt,
            )
            return "".join(block.text for block in resp.content if block.type == "text")

        if self.provider == "openai":
            full = [{"role": "system", "content": system}] + messages
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=full,
                temperature=t,
                max_tokens=mt,
            )
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
