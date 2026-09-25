"""Retrieval scored against the hand-labelled ``known_interaction_pairs``.

This is the independent check. The internal-consistency metrics in
``metrics.Evaluator`` derive ground truth from the same normalizer and table
the retriever uses, so they are 1.0 by construction. Here the ground truth is
what a person wrote down in ``test_cases.py``.

Caveats that belong next to any number this produces:
- Labels are partial. Many cases list only the headline interaction, and 14
  of the original 48 list none, nor do the 8 look-alike cases (LA-*), so precision here is a lower bound: an "unlabelled
  retrieved" pair is not necessarily wrong.
- Labels are mapped to canonical keys through the local vocabulary (exact
  alias match only), e.g. "lithium carbonate" -> "lithium". A label name that
  isn't in the vocabulary is kept as-is and can never be hit.
- Every miss is classified: a *source gap* (the pair is in no loaded table, so
  no pipeline could retrieve it) or a *pipeline miss* (the pair is in a table
  but wasn't retrieved: a normalization, planning or lookup failure).
- Name the data profile (sample / public / research) next to any number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Set, Tuple

Pair = Tuple[str, str]


def canonical_pair(a: str, b: str, alias_map: Mapping[str, str]) -> Pair:
    ca = alias_map.get(a.strip().lower(), a.strip().lower())
    cb = alias_map.get(b.strip().lower(), b.strip().lower())
    return tuple(sorted((ca, cb)))


def pair_sources(interactions) -> Dict[Pair, List[str]]:
    """Canonical pair -> sorted list of sources with at least one record, from an
    interactions table (columns drug_a_name, drug_b_name, source)."""
    a = interactions["drug_a_name"].fillna("").astype(str).str.strip().str.lower()
    b = interactions["drug_b_name"].fillna("").astype(str).str.strip().str.lower()
    lo, hi = a.where(a <= b, b), b.where(a <= b, a)
    out: Dict[Pair, Set[str]] = {}
    for x, y, s in zip(lo, hi, interactions["source"].astype(str)):
        out.setdefault((x, y), set()).add(s)
    return {k: sorted(v) for k, v in out.items()}


def classify_miss(pair: Pair, sources_by_pair: Mapping[Pair, List[str]]) -> str:
    """"source_gap" if no loaded table has the pair, else "pipeline_miss"."""
    return "pipeline_miss" if sources_by_pair.get(tuple(pair)) else "source_gap"


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
    sources_by_pair: Optional[Mapping[Pair, List[str]]] = None,
) -> Dict:
    """Micro-averaged recall/precision of retrieved pairs vs. hand labels.

    ``retrieve_pairs(input_drugs)`` returns the set of canonical pairs for which
    the system retrieved at least one interaction record. With ``sources_by_pair``
    (see pair_sources) every miss is classified as a source gap or a pipeline miss.
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
    missed = [(c.case_id, list(p)) for c in per_case for p in c.missed]
    split: Dict = {}
    if sources_by_pair is not None:
        gaps = [m for m in missed if classify_miss(tuple(m[1]), sources_by_pair) == "source_gap"]
        pipe = [m for m in missed if classify_miss(tuple(m[1]), sources_by_pair) == "pipeline_miss"]
        split = {
            "source_gaps": len(gaps), "pipeline_misses": len(pipe),
            "missed_source_gap": gaps,
            "missed_pipeline": [(cid, p, sources_by_pair[tuple(p)]) for cid, p in pipe],
            # recall over the labelled pairs that some loaded table actually contains
            "pipeline_recall": round(n_hits / (n_hits + len(pipe)), 3) if n_hits + len(pipe) else None,
        }
    return {
        "num_cases": len(per_case),
        "labelled_pairs": n_labelled,
        "retrieved_pairs": n_retrieved,
        "hits": n_hits,
        "recall": round(n_hits / n_labelled, 3) if n_labelled else None,
        "precision_lower_bound": round(n_hits / n_retrieved, 3) if n_retrieved else None,
        "missed": missed,
        **split,
        "unlabelled_retrieved": [(c.case_id, list(p)) for c in per_case for p in c.unlabelled_retrieved],
        "cases": [c.__dict__ for c in per_case],
    }
