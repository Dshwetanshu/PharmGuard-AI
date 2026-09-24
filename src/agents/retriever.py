"""Retriever agent.

Executes a RetrievalPlan against the configured knowledge sources:
  - Interactions (structured lookup over TWOSIDES + DDInter)
  - Side effects (structured lookup over SIDER)
  - Optional: FAERS live-query fallback for pairs with no local data

Returns a RetrievalResult bundle that the Generator consumes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.agents.planner import RetrievalPlan
from src.retrieval.interaction_retriever import InteractionRetriever, InteractionRecord
from src.retrieval.side_effect_retriever import SideEffectRetriever, SideEffectRecord
from src.retrieval.faers_retriever import FaersRetriever, FaersRecord


@dataclass
class RetrievalResult:
    # pair_key (sorted tuple of drug names) -> list of interaction records
    interactions: Dict[tuple, List[InteractionRecord]] = field(default_factory=dict)
    side_effects: Dict[str, List[SideEffectRecord]] = field(default_factory=dict)
    faers_signals: Dict[tuple, List[FaersRecord]] = field(default_factory=dict)
    # Pairs that returned zero interaction records — surfaced, not silenced
    no_data_pairs: List[tuple] = field(default_factory=list)
    # pair -> statistical signals retrieved but not selected (the report states "+N more not shown")
    hidden_signals: Dict[tuple, int] = field(default_factory=dict)

    @property
    def total_interactions(self) -> int:
        return sum(len(v) for v in self.interactions.values())

    @property
    def total_faers_signals(self) -> int:
        return sum(len(v) for v in self.faers_signals.values())

    @property
    def curated_records(self) -> List[InteractionRecord]:
        return [r for recs in self.interactions.values() for r in recs if not r.is_statistical]

    @property
    def statistical_signals(self) -> List[InteractionRecord]:
        return [r for recs in self.interactions.values() for r in recs if r.is_statistical]

    @property
    def total_hidden_signals(self) -> int:
        return sum(self.hidden_signals.values())


# At most this many statistical signals per pair are shown; curated records are never hidden.
MAX_SIGNALS_PER_PAIR = 3


def select_pair_records(records: List[InteractionRecord],
                        max_signals: int = MAX_SIGNALS_PER_PAIR) -> Tuple[List[InteractionRecord], int]:
    """(selected, hidden count): every curated record (in retrieval order), then the
    top `max_signals` statistical signals by PRR. The hidden count is stated in the report."""
    curated = [r for r in records if not r.is_statistical]
    signals = sorted((r for r in records if r.is_statistical),
                     key=lambda r: -(r.prr if r.prr is not None else float("-inf")))
    return curated + signals[:max_signals], max(0, len(signals) - max_signals)


class Retriever:
    def __init__(
        self,
        interaction_retriever: InteractionRetriever,
        side_effect_retriever: Optional[SideEffectRetriever] = None,
        faers_retriever: Optional[FaersRetriever] = None,
    ):
        self.interactions = interaction_retriever
        self.side_effects = side_effect_retriever
        self.faers = faers_retriever

    def execute(self, plan: RetrievalPlan) -> RetrievalResult:
        result = RetrievalResult()

        # 1. Pairwise interactions from local index (TWOSIDES + DDInter)
        for pair in plan.pairs:
            a, b = pair
            records, hidden = select_pair_records(self.interactions.retrieve_all(a, b))
            if records:
                result.interactions[pair] = records
                if hidden:
                    result.hidden_signals[pair] = hidden
            else:
                result.no_data_pairs.append(pair)

        # 2. Per-drug side effects (SIDER)
        if self.side_effects is not None:
            for name in plan.side_effect_lookups:
                ses = self.side_effects.retrieve_for_drug(name, top_k=8)
                if ses:
                    result.side_effects[name] = ses

        # 3. FAERS fallback — only for pairs with no local data, only if enabled.
        # FAERS hits are unvalidated spontaneous reports, not curated interaction
        # data, so the pair stays in no_data_pairs; the signals are reported
        # separately.
        if self.faers is not None and self.faers.enabled and result.no_data_pairs:
            for pair in result.no_data_pairs:
                a, b = pair
                signals = self.faers.retrieve_pair(a, b)
                if signals:
                    result.faers_signals[pair] = signals

        return result
