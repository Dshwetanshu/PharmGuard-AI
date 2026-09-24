"""API settings. Only ApiSettings.from_env() reads the environment.

Public defaults: deterministic mode, live RxNorm off, tracing off, FAERS only
when a request asks for it (capped), and the real public build required
(never a silent fall-back to the synthetic sample).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

from src.graph.settings import Settings


@dataclass(frozen=True)
class ApiSettings:
    data_dir: Path
    required_profile: str = "public"          # the build /v1/check will serve; anything else -> 503
    api_key: Optional[str] = None             # X-API-Key value that unlocks LLM mode
    rate_limit_requests: int = 20             # per client IP ...
    rate_limit_window_s: float = 60.0         # ... per window
    trusted_proxy_hops: int = 0               # 1 behind the Hugging Face Spaces proxy
    timeout_deterministic_s: float = 20.0
    timeout_llm_s: float = 90.0
    max_concurrency: int = 4
    allow_faers: bool = True                  # FAERS still runs only when a request asks for it
    faers_max_pairs: int = 5
    faers_budget_s: float = 10.0
    faers_timeout_s: float = 4.0              # per openFDA call
    # Optional start-up download of the build from a private Hugging Face dataset.
    hf_dataset: Optional[str] = None
    hf_revision: Optional[str] = None         # pinned commit sha
    hf_provenance_sha256: Optional[str] = None
    hf_token: Optional[str] = field(default=None, repr=False)
    graph: Optional[Settings] = None          # graph settings (LLM provider/model, key presence)

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None, **overrides) -> "ApiSettings":
        from dotenv import load_dotenv

        if env is None:
            load_dotenv()
            env = os.environ
        data_dir = Path(env.get("PHARMGUARD_DATA_DIR", "/data/public")).expanduser().resolve()
        # Live RxNorm off (the local RxNorm vocabulary covers normalization), tracing off,
        # FAERS off at the graph level (a separate FAERS-enabled graph serves requests that ask).
        graph = Settings.from_env(data_dir=data_dir, mode="deterministic", rxnorm_enabled=False,
                                  faers_enabled=False, tracing="none")
        rate = env.get("PHARMGUARD_RATE_LIMIT", "20/60").split("/")
        values = dict(
            data_dir=data_dir,
            required_profile=env.get("PHARMGUARD_REQUIRED_PROFILE", "public"),
            api_key=env.get("PHARMGUARD_API_KEY") or None,
            rate_limit_requests=int(rate[0]),
            rate_limit_window_s=float(rate[1]) if len(rate) > 1 else 60.0,
            trusted_proxy_hops=int(env.get("PHARMGUARD_TRUSTED_PROXY_HOPS", "0")),
            timeout_deterministic_s=float(env.get("PHARMGUARD_TIMEOUT_S", "20")),
            timeout_llm_s=float(env.get("PHARMGUARD_LLM_TIMEOUT_S", "90")),
            max_concurrency=int(env.get("PHARMGUARD_MAX_CONCURRENCY", "4")),
            allow_faers=env.get("PHARMGUARD_API_ALLOW_FAERS", "true").lower() == "true",
            faers_max_pairs=int(env.get("PHARMGUARD_FAERS_MAX_PAIRS", "5")),
            faers_budget_s=float(env.get("PHARMGUARD_FAERS_BUDGET_S", "10")),
            hf_dataset=env.get("PHARMGUARD_HF_DATASET") or None,
            hf_revision=env.get("PHARMGUARD_HF_REVISION") or None,
            hf_provenance_sha256=env.get("PHARMGUARD_HF_PROVENANCE_SHA256") or None,
            hf_token=env.get("HF_TOKEN") or None,
            graph=graph,
        )
        values.update(overrides)
        return cls(**values)

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"
