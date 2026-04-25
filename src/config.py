"""Central configuration for PharmGuard AI.

Loads from environment variables with sensible defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env_path(key: str, default: str) -> Path:
    return Path(os.getenv(key, default)).expanduser().resolve()


def _detect_provider() -> str:
    """Auto-detect which LLM provider to use based on which key is set."""
    explicit = os.getenv("PHARMGUARD_LLM_PROVIDER")
    if explicit:
        return explicit.lower()
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    return "anthropic"  # default; will error at call time if no key


DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
}


@dataclass
class PathConfig:
    data_dir: Path = field(default_factory=lambda: _env_path("PHARMGUARD_DATA_DIR", str(PROJECT_ROOT / "data")))

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def sample_dir(self) -> Path:
        return self.data_dir / "sample"

    @property
    def vector_db_path(self) -> Path:
        override = os.getenv("PHARMGUARD_VECTOR_DB_PATH")
        if override:
            return Path(override).expanduser().resolve()
        return self.processed_dir / "chroma"


@dataclass
class LLMConfig:
    provider: str = field(default_factory=_detect_provider)
    model: Optional[str] = field(default_factory=lambda: os.getenv("PHARMGUARD_LLM_MODEL"))
    temperature: float = field(
        default_factory=lambda: float(os.getenv("PHARMGUARD_LLM_TEMPERATURE", "0.1"))
    )
    max_tokens: int = 2048

    def resolved_model(self) -> str:
        return self.model or DEFAULT_MODELS.get(self.provider, DEFAULT_MODELS["anthropic"])


@dataclass
class RetrievalConfig:
    top_k: int = field(default_factory=lambda: int(os.getenv("PHARMGUARD_TOP_K", "5")))
    min_confidence: float = field(
        default_factory=lambda: float(os.getenv("PHARMGUARD_MIN_CONFIDENCE", "0.0"))
    )
    # TWOSIDES uses PRR / mean-reporting-frequency as significance signals
    twosides_min_prr: float = 2.0
    # Fuzzy match threshold for drug name normalization (0-100)
    name_match_threshold: int = 85
    # FAERS live-query fallback (opt-in; requires network access)
    faers_enabled: bool = field(
        default_factory=lambda: os.getenv("PHARMGUARD_FAERS_ENABLED", "false").lower() == "true"
    )
    # RxNorm REST API fallback for name normalization (ON by default)
    # When enabled, drug names not in the local vocabulary are resolved via
    # https://rxnav.nlm.nih.gov — handles virtually any FDA-approved drug.
    rxnorm_api_enabled: bool = field(
        default_factory=lambda: os.getenv("PHARMGUARD_RXNORM_API_ENABLED", "true").lower() == "true"
    )


@dataclass
class Config:
    paths: PathConfig = field(default_factory=PathConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)

    # Disclaimer text appended to every generated report
    disclaimer: str = (
        "PharmGuard is a decision-support tool grounded in public pharmaceutical "
        "databases. It is not a substitute for professional medical judgment. "
        "Always consult a licensed clinician or pharmacist before making changes to "
        "a medication regimen."
    )


# Module-level singleton for convenience
config = Config()
