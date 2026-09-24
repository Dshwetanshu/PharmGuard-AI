"""JSON-safe conversion of the pipeline's objects for graph state.

State holds plain dicts/lists only (no tuple keys, no numpy scalars), so the
whole final state passes json.dumps. The generators still take RetrievalPlan /
RetrievalResult objects; nodes rebuild them from state with the *_from_dict
helpers. Pairs are [a, b] lists.
"""
from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from typing import Any, Dict

from src.agents.planner import RetrievalPlan
from src.agents.retriever import RetrievalResult
from src.data.normalizer import ResolvedDrug
from src.retrieval.faers_retriever import FaersRecord
from src.retrieval.interaction_retriever import InteractionRecord
from src.retrieval.side_effect_retriever import SideEffectRecord


def jsonable(value: Any) -> Any:
    """Recursively convert to JSON-safe values (numpy scalars -> Python, NaN -> None)."""
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):  # numpy scalar
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def plan_to_dict(plan: RetrievalPlan) -> Dict[str, Any]:
    return jsonable({"resolved": plan.resolved, "unresolved": plan.unresolved,
                     "pairs": [list(p) for p in plan.pairs], "side_effect_lookups": plan.side_effect_lookups})


def plan_from_dict(d: Dict[str, Any]) -> RetrievalPlan:
    return RetrievalPlan(
        resolved=[ResolvedDrug(**r) for r in d["resolved"]],
        unresolved=[ResolvedDrug(**r) for r in d["unresolved"]],
        pairs=[tuple(p) for p in d["pairs"]],
        side_effect_lookups=list(d["side_effect_lookups"]),
    )


def result_to_dict(result: RetrievalResult) -> Dict[str, Any]:
    return jsonable({
        "interactions": [{"pair": list(p), "records": recs} for p, recs in result.interactions.items()],
        "side_effects": [{"drug": d, "records": recs} for d, recs in result.side_effects.items()],
        "faers": [{"pair": list(p), "records": recs} for p, recs in result.faers_signals.items()],
        "no_data_pairs": [list(p) for p in result.no_data_pairs],
        "hidden_signals": [{"pair": list(p), "count": n} for p, n in result.hidden_signals.items()],
    })


def result_from_dict(d: Dict[str, Any]) -> RetrievalResult:
    return RetrievalResult(
        interactions={tuple(x["pair"]): [InteractionRecord(**r) for r in x["records"]] for x in d["interactions"]},
        side_effects={x["drug"]: [SideEffectRecord(**r) for r in x["records"]] for x in d["side_effects"]},
        faers_signals={tuple(x["pair"]): [FaersRecord(**r) for r in x["records"]] for x in d["faers"]},
        no_data_pairs=[tuple(p) for p in d["no_data_pairs"]],
        hidden_signals={tuple(x["pair"]): int(x["count"]) for x in d.get("hidden_signals", [])},
    )


def empty_result() -> Dict[str, Any]:
    return result_to_dict(RetrievalResult())
