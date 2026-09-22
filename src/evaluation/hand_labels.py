"""Retrieval scored against the hand-labelled ``known_interaction_pairs``.

This is the independent check. The internal-consistency metrics in
``metrics.Evaluator`` derive ground truth from the same normalizer and table
the retriever uses, so they are 1.0 by construction. Here the ground truth is
what a person wrote down in ``test_cases.py``.

Caveats that belong next to any number this produces:
- Labels are partial. Many cases list only the headline interaction, and 14
  of 48 list none, so precision here is a lower bound: an "unlabelled
  retrieved" pair is not necessarily wrong.
- Labels are mapped to canonical keys through the local vocabulary (exact
  alias match only), e.g. "lithium" -> "lithium carbonate". A label name that
  isn't in the vocabulary is kept as-is and can never be hit.
- All current data is synthetic sample data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Mapping, Set, Tuple

Pair = Tuple[str, str]


def canonical_pair(a: str, b: str, alias_map: Mapping[str, str]) -> Pair:
    ca = alias_map.get(a.strip().lower(), a.strip().lower())
    cb = alias_map.get(b.strip().lower(), b.strip().lower())
    return tuple(sorted((ca, cb)))


@dataclass
class HandLabelCase:
    case_id: str
    labelled: List[Pair]
    retrieved: List[Pair]
    hits: List[Pair] = field(default_factory=list)
    missed: List[Pair] = field(default_factory=list)
    unlabelled_retrieved: List[Pair] = field(default_factory=list)


def score_hand_labels(
    cases: Iterable,
    retrieve_pairs: Callable[[List[str]], Set[Pair]],
    alias_map: Mapping[str, str],
) -> Dict:
    """Micro-averaged recall/precision of retrieved pairs vs. hand labels.

    ``retrieve_pairs(input_drugs)`` returns the set of canonical pairs for which
    the system retrieved at least one interaction record.
    """
    per_case: List[HandLabelCase] = []
    for case in cases:
        labelled = {canonical_pair(a, b, alias_map) for a, b in case.known_interaction_pairs}
        retrieved = set(retrieve_pairs(case.input_drugs))
        per_case.append(HandLabelCase(
            case_id=case.case_id,
            labelled=sorted(labelled),
            retrieved=sorted(retrieved),
            hits=sorted(labelled & retrieved),
            missed=sorted(labelled - retrieved),
            unlabelled_retrieved=sorted(retrieved - labelled),
        ))

    n_labelled = sum(len(c.labelled) for c in per_case)
    n_retrieved = sum(len(c.retrieved) for c in per_case)
    n_hits = sum(len(c.hits) for c in per_case)
    return {
        "num_cases": len(per_case),
        "labelled_pairs": n_labelled,
        "retrieved_pairs": n_retrieved,
        "hits": n_hits,
        "recall": round(n_hits / n_labelled, 3) if n_labelled else None,
        "precision_lower_bound": round(n_hits / n_retrieved, 3) if n_retrieved else None,
        "missed": [(c.case_id, list(p)) for c in per_case for p in c.missed],
        "unlabelled_retrieved": [(c.case_id, list(p)) for c in per_case for p in c.unlabelled_retrieved],
        "cases": [c.__dict__ for c in per_case],
    }
