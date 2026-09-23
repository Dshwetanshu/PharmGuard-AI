"""Explicit settings for building a PharmGuard graph.

Tests and the upcoming API build graphs from a Settings value. Only
Settings.from_env() reads the environment (and .env); nothing is read at
import time.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from src.config import DEFAULT_MODELS, PROJECT_ROOT, Config

KEY_VARS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GOOGLE_API_KEY"}
MODES = ("llm", "deterministic")
TRACING_BACKENDS = ("none", "langsmith", "phoenix")
log = logging.getLogger("pharmguard.tracing")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    mode: str = "llm"                    # "llm" | "deterministic"
    max_llm_attempts: int = 2            # first draft + one retry with checker feedback
    llm_configured: bool = False         # an API key for llm_provider is available
    llm_provider: str = "anthropic"
    llm_model: Optional[str] = None      # None -> provider default (src/config.DEFAULT_MODELS)
    rxnorm_enabled: bool = False
    rxnorm_min_score: float = 10.0
    faers_enabled: bool = False
    top_k: int = 5
    # Tracing (docs/OBSERVABILITY.md). Credentials are only recorded as present/absent here;
    # the SDKs read the values themselves.
    tracing: str = "none"                # "none" | "langsmith" | "phoenix"
    trace_redact: bool = True            # hide inputs/outputs (medication lists are health data)
    trace_project: str = "pharmguard"
    langsmith_key_present: bool = False
    phoenix_endpoint: str = "http://localhost:6006"

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {self.mode!r}")
        if self.max_llm_attempts < 1:
            raise ValueError("max_llm_attempts must be >= 1")
        if self.tracing not in TRACING_BACKENDS:
            raise ValueError(f"tracing must be one of {TRACING_BACKENDS}, got {self.tracing!r}")

    @property
    def model_id(self) -> str:
        return self.llm_model or DEFAULT_MODELS.get(self.llm_provider, DEFAULT_MODELS["anthropic"])

    def with_mode(self, mode: str) -> "Settings":
        return replace(self, mode=mode)

    def to_config(self) -> Config:
        """A Config for the existing components, with every relevant field set
        from these settings (not from the environment)."""
        cfg = Config()
        cfg.paths.data_dir = Path(self.data_dir)
        cfg.llm.provider = self.llm_provider
        cfg.llm.model = self.llm_model
        cfg.retrieval.top_k = self.top_k
        cfg.retrieval.min_confidence = self.rxnorm_min_score
        cfg.retrieval.rxnorm_api_enabled = self.rxnorm_enabled
        cfg.retrieval.faers_enabled = self.faers_enabled
        return cfg

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        from dotenv import load_dotenv

        load_dotenv()
        env = os.environ
        provider = (env.get("PHARMGUARD_LLM_PROVIDER") or next(
            (p for p, k in KEY_VARS.items() if env.get(k)), "anthropic")).lower()
        values = dict(
            data_dir=Path(env.get("PHARMGUARD_DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser().resolve(),
            llm_provider=provider,
            llm_model=env.get("PHARMGUARD_LLM_MODEL") or None,
            llm_configured=bool(env.get(KEY_VARS.get(provider, ""))),
            rxnorm_enabled=env.get("PHARMGUARD_RXNORM_API_ENABLED", "true").lower() == "true",
            rxnorm_min_score=float(env.get("PHARMGUARD_MIN_CONFIDENCE", "10.0")),
            faers_enabled=env.get("PHARMGUARD_FAERS_ENABLED", "false").lower() == "true",
            top_k=int(env.get("PHARMGUARD_TOP_K", "5")),
            tracing=_tracing_backend(env.get("PHARMGUARD_TRACING", "none")),
            trace_redact=env.get("PHARMGUARD_TRACE_REDACT", "true").lower() != "false",
            trace_project=env.get("LANGSMITH_PROJECT" if env.get("PHARMGUARD_TRACING", "").lower() == "langsmith"
                                  else "PHOENIX_PROJECT_NAME") or "pharmguard",
            langsmith_key_present=bool(env.get("LANGSMITH_API_KEY")),
            phoenix_endpoint=env.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006"),
        )
        values.update(overrides)
        return cls(**values)


def _tracing_backend(value: str) -> str:
    v = (value or "none").strip().lower()
    if v not in TRACING_BACKENDS:
        log.warning("PHARMGUARD_TRACING=%r is not one of %s; running untraced.", value, TRACING_BACKENDS)
        return "none"
    return v
