"""PharmGuard end-to-end pipeline.

Usage:
    pipeline = PharmGuardPipeline.from_config()
    result = pipeline.run(["lisinopril", "spironolactone", "ibuprofen"])
    print(result.report)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from src.config import Config, config as default_config
from src.data.normalizer import DrugNormalizer, ResolvedDrug
from src.agents.planner import Planner, RetrievalPlan
from src.agents.retriever import Retriever, RetrievalResult
from src.agents.generator import Generator
from src.retrieval.interaction_retriever import InteractionRetriever
from src.retrieval.side_effect_retriever import SideEffectRetriever
from src.retrieval.vector_store import VectorStore


@dataclass
class PipelineResult:
    input_drugs: List[str]
    resolved: List[ResolvedDrug]
    plan: RetrievalPlan
    retrieval: RetrievalResult
    report: str
    latency_seconds: float
    trace: dict = field(default_factory=dict)


class PharmGuardPipeline:
    def __init__(
        self,
        normalizer: DrugNormalizer,
        planner: Planner,
        retriever: Retriever,
        generator: Generator,
        cfg: Optional[Config] = None,
    ):
        self.cfg = cfg or default_config
        self.normalizer = normalizer
        self.planner = planner
        self.retriever = retriever
        self.generator = generator

    # ---------- factory ----------

    @classmethod
    def from_config(cls, cfg: Optional[Config] = None, load_vectors: bool = False) -> "PharmGuardPipeline":
        cfg = cfg or default_config
        normalizer = DrugNormalizer(cfg).load()
        interaction_retriever = InteractionRetriever(cfg).load()
        side_effect_retriever = SideEffectRetriever(cfg).load()
        vs = VectorStore(cfg=cfg) if load_vectors else None
        from src.retrieval.faers_retriever import FaersRetriever
        faers = FaersRetriever(enabled=cfg.retrieval.faers_enabled)
        retriever = Retriever(interaction_retriever, side_effect_retriever, vs, faers_retriever=faers)
        return cls(
            normalizer=normalizer,
            planner=Planner(),
            retriever=retriever,
            generator=Generator(cfg),
            cfg=cfg,
        )

    # ---------- main entry point ----------

    def run(
        self,
        drug_names: List[str],
        use_llm: bool = True,
        with_reviews: bool = False,
    ) -> PipelineResult:
        if not drug_names:
            raise ValueError("At least one drug must be provided.")
        if len(drug_names) > 12:
            raise ValueError("MVP supports up to 12 drugs. Got %d." % len(drug_names))

        start = time.perf_counter()
        trace = {}

        # 1. Normalize
        t0 = time.perf_counter()
        resolved = self.normalizer.resolve_many(drug_names)
        trace["normalize_ms"] = int((time.perf_counter() - t0) * 1000)

        # 2. Plan
        t0 = time.perf_counter()
        plan = self.planner.plan(resolved)
        trace["plan_ms"] = int((time.perf_counter() - t0) * 1000)
        trace["num_pairs"] = plan.num_pairs

        # 3. Retrieve
        t0 = time.perf_counter()
        retrieval_result = self.retriever.execute(plan, with_reviews=with_reviews)
        trace["retrieve_ms"] = int((time.perf_counter() - t0) * 1000)
        trace["total_interactions"] = retrieval_result.total_interactions
        trace["no_data_pairs"] = len(retrieval_result.no_data_pairs)

        # 4. Generate
        t0 = time.perf_counter()
        if use_llm:
            try:
                report = self.generator.generate(plan, retrieval_result)
                trace["generator"] = "llm"
            except Exception as exc:
                # Hard fallback: deterministic report if LLM fails
                report = self.generator.generate_deterministic(plan, retrieval_result)
                trace["generator"] = f"deterministic (llm_error: {type(exc).__name__})"
        else:
            report = self.generator.generate_deterministic(plan, retrieval_result)
            trace["generator"] = "deterministic"
        trace["generate_ms"] = int((time.perf_counter() - t0) * 1000)

        return PipelineResult(
            input_drugs=drug_names,
            resolved=resolved,
            plan=plan,
            retrieval=retrieval_result,
            report=report,
            latency_seconds=time.perf_counter() - start,
            trace=trace,
        )
