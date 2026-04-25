"""Retriever agent.

Executes a RetrievalPlan against the configured knowledge sources:
  - Interactions (structured lookup over TWOSIDES + DDInter)
  - Side effects (structured lookup over SIDER + ADE-Corpus-V2)
  - Optional: FAERS live-query fallback for pairs with no local data
  - Optional: patient-review context (vector search over WebMD + UCI)

Returns a RetrievalResult bundle that the Generator consumes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.agents.planner import RetrievalPlan
from src.retrieval.interaction_retriever import InteractionRetriever, InteractionRecord
from src.retrieval.side_effect_retriever import SideEffectRetriever, SideEffectRecord
from src.retrieval.vector_store import VectorStore
from src.retrieval.faers_retriever import FaersRetriever, FaersRecord


@dataclass
class RetrievalResult:
    # pair_key (sorted tuple of drug names) -> list of interaction records
    interactions: Dict[tuple, List[InteractionRecord]] = field(default_factory=dict)
    side_effects: Dict[str, List[SideEffectRecord]] = field(default_factory=dict)
    review_context: Dict[str, List[dict]] = field(default_factory=dict)
    faers_signals: Dict[tuple, List[FaersRecord]] = field(default_factory=dict)
    # Pairs that returned zero interaction records — surfaced, not silenced
    no_data_pairs: List[tuple] = field(default_factory=list)

    @property
    def total_interactions(self) -> int:
        return sum(len(v) for v in self.interactions.values())

    @property
    def total_faers_signals(self) -> int:
        return sum(len(v) for v in self.faers_signals.values())


class Retriever:
    def __init__(
        self,
        interaction_retriever: InteractionRetriever,
        side_effect_retriever: Optional[SideEffectRetriever] = None,
        vector_store: Optional[VectorStore] = None,
        faers_retriever: Optional[FaersRetriever] = None,
    ):
        self.interactions = interaction_retriever
        self.side_effects = side_effect_retriever
        self.vector_store = vector_store
        self.faers = faers_retriever

    def execute(self, plan: RetrievalPlan, with_reviews: bool = False) -> RetrievalResult:
        result = RetrievalResult()

        # 1. Pairwise interactions from local index (TWOSIDES + DDInter)
        for pair in plan.pairs:
            a, b = pair
            records = self.interactions.retrieve_pair(a, b)
            if records:
                result.interactions[pair] = records
            else:
                result.no_data_pairs.append(pair)

        # 2. Per-drug side effects (SIDER + ADE if loaded)
        if self.side_effects is not None:
            for name in plan.side_effect_lookups:
                ses = self.side_effects.retrieve_for_drug(name, top_k=8)
                if ses:
                    result.side_effects[name] = ses

        # 3. FAERS fallback — only for pairs with no local data, only if enabled
        if self.faers is not None and self.faers.enabled and result.no_data_pairs:
            still_no_data = []
            for pair in result.no_data_pairs:
                a, b = pair
                signals = self.faers.retrieve_pair(a, b)
                if signals:
                    result.faers_signals[pair] = signals
                else:
                    still_no_data.append(pair)
            result.no_data_pairs = still_no_data

        # 4. Optional review context (WebMD + UCI in the vector store)
        if with_reviews and self.vector_store is not None:
            for name in plan.side_effect_lookups:
                try:
                    hits = self.vector_store.search(
                        query=f"patient experience with {name}",
                        top_k=3,
                        where={"drug_name": name},
                    )
                    if hits:
                        result.review_context[name] = hits
                except Exception:
                    # Vector store is a nice-to-have — don't crash the pipeline
                    pass

        return result
