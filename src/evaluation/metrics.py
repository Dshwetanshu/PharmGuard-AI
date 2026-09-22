"""Retrieval metrics (internal consistency).

Report-level metrics (semantic hallucination rate, uncited-claim rate, citation
validity, omission rates, completeness) live in src/verification/checker.py.
An LLM-judge faithfulness score is not implemented.

Recall and precision here are an INTERNAL CONSISTENCY check: ground
truth = every input pair present in the loaded interactions table, derived with
the same normalizer and table the retriever uses. Recall and precision are
therefore 1.0 by construction and cannot detect normalization errors (e.g. the
lithium / lithium carbonate key mismatch scored 1.0). For an independent check
see src/evaluation/hand_labels.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from src.agents.planner import Planner
from src.agents.retriever import Retriever, RetrievalResult
from src.data.normalizer import DrugNormalizer
from src.evaluation.test_cases import TestCase


@dataclass
class CaseMetrics:
    case_id: str
    num_drugs: int
    num_pairs: int
    ground_truth_pairs: int
    retrieved_pairs: int
    true_positives: int
    false_positives: int
    false_negatives: int
    recall: float
    precision: float
    no_data_pairs_flagged: int
    unresolved_inputs: int
    hallucination_count: Optional[int] = None
    severity_correct: Optional[int] = None
    severity_total: Optional[int] = None


@dataclass
class AggregateMetrics:
    cases: List[CaseMetrics] = field(default_factory=list)

    @property
    def mean_recall(self) -> float:
        vals = [c.recall for c in self.cases if c.ground_truth_pairs > 0]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def mean_precision(self) -> float:
        vals = [c.precision for c in self.cases if c.retrieved_pairs > 0]
        return sum(vals) / len(vals) if vals else 0.0

    def as_dict(self) -> dict:
        return {
            "note": "internal consistency: ground truth uses the same normalizer and "
                    "table as retrieval, so recall/precision are 1.0 by construction",
            "num_cases": len(self.cases),
            "mean_recall": round(self.mean_recall, 3),
            "mean_precision": round(self.mean_precision, 3),
            "cases": [c.__dict__ for c in self.cases],
        }


class Evaluator:
    def __init__(
        self,
        normalizer: DrugNormalizer,
        retriever: Retriever,
        interactions_df: pd.DataFrame,
    ):
        self.normalizer = normalizer
        self.retriever = retriever
        self.planner = Planner()
        self.interactions_df = interactions_df
        self._pair_index = self._build_pair_index(interactions_df)

    @staticmethod
    def _build_pair_index(df: pd.DataFrame) -> Set[Tuple[str, str]]:
        pairs = set()
        for _, r in df.iterrows():
            a = str(r.get("drug_a_name") or "").lower().strip()
            b = str(r.get("drug_b_name") or "").lower().strip()
            if a and b:
                pairs.add(tuple(sorted([a, b])))
        return pairs

    # ---------- ground truth derivation ----------

    def ground_truth_for_case(self, case: TestCase) -> Set[Tuple[str, str]]:
        """All pairs from the input list that exist in the loaded interaction data."""
        resolved = self.normalizer.resolve_many(case.input_drugs)
        names = [d.generic_name.lower() for d in resolved if d.resolved and d.generic_name]
        names = sorted(set(names))
        return {tuple(sorted(p)) for p in combinations(names, 2) if tuple(sorted(p)) in self._pair_index}

    # ---------- per-case metrics ----------

    def evaluate_case(self, case: TestCase) -> CaseMetrics:
        resolved = self.normalizer.resolve_many(case.input_drugs)
        plan = self.planner.plan(resolved)
        retrieval = self.retriever.execute(plan)

        ground_truth = self.ground_truth_for_case(case)
        retrieved = set(retrieval.interactions.keys())

        tp = len(ground_truth & retrieved)
        fp = len(retrieved - ground_truth)
        fn = len(ground_truth - retrieved)

        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0

        return CaseMetrics(
            case_id=case.case_id,
            num_drugs=plan.num_drugs,
            num_pairs=plan.num_pairs,
            ground_truth_pairs=len(ground_truth),
            retrieved_pairs=len(retrieved),
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            recall=recall,
            precision=precision,
            no_data_pairs_flagged=len(retrieval.no_data_pairs),
            unresolved_inputs=len(plan.unresolved),
        )

    def evaluate_all(self, cases: List[TestCase]) -> AggregateMetrics:
        agg = AggregateMetrics()
        for case in cases:
            agg.cases.append(self.evaluate_case(case))
        return agg
