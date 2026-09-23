"""PharmGuard as a LangGraph state machine with deterministic planning and bounded LLM retry.

This is a port of the orchestration in src/pipeline.py. DrugNormalizer,
Planner, Retriever, both generators, the FAERS fallback and src/verification
are reused unchanged; the graph owns control flow and adds the retry loop.

    normalize -> plan -> (fewer than 2 drugs) -> template
                      -> retrieve -> (FAERS enabled) -> faers
                                  -> deterministic mode / no LLM -> template
                                  -> generate_llm -> validate -> pass -> finalize
                                                              -> fail, attempts left -> generate_llm (with findings)
                                                              -> fail, no attempts left -> template
    template -> finalize

Nodes are plain synchronous functions (the RxNorm and FAERS calls block) over a
JSON-serializable TypedDict state. Every node appends {node, status, ms, detail}
to the trajectory. The topology is defined only in build_graph().
"""
from __future__ import annotations

import operator
import time
from dataclasses import dataclass
from itertools import combinations
from math import comb
from typing import Annotated, Any, Callable, Dict, List, Optional, Tuple, TypedDict

from langgraph.graph import END, START, StateGraph

from src.agents.generator import Generator
from src.agents.planner import Planner
from src.agents.retriever import Retriever
from src.data.normalizer import DrugNormalizer, ResolvedDrug
from src.graph.serde import empty_result, jsonable, plan_from_dict, plan_to_dict, result_from_dict, result_to_dict
from src.graph.settings import Settings
from src.input_validation import clean_drug_names
from src.pipeline import request_evidence
from src.retrieval.faers_retriever import FaersRetriever
from src.retrieval.interaction_retriever import InteractionRetriever
from src.retrieval.side_effect_retriever import SideEffectRetriever
from src.verification import Evidence, ValidationResult, validate_report

MAX_DRUGS = 12

REPORT_SOURCES = {
    "llm": "Written by the LLM; the first draft passed validation against the retrieved evidence.",
    "llm_retry": "Written by the LLM; the first draft failed validation and the retry passed.",
    "deterministic": "Deterministic template report (LLM mode was not selected).",
    "deterministic_fallback": "Deterministic template report: the LLM report failed validation "
                              "or the LLM call failed.",
    "deterministic_no_llm": "Deterministic template report: no LLM API key is configured.",
    "deterministic_insufficient_input": "Deterministic template report: fewer than two drugs were "
                                        "recognised, so there are no pairs to analyse.",
}


class GraphState(TypedDict, total=False):
    input_drugs: List[str]
    resolved: List[Dict[str, Any]]          # ResolvedDrug dicts, one per input
    plan: Dict[str, Any]                    # serde.plan_to_dict
    retrieval: Dict[str, Any]               # serde.result_to_dict (exact records, for the generators)
    evidence: Dict[str, Any]                # Evidence.to_dict() (normalized records, for validation)
    llm_attempts: int
    llm_error: Optional[str]                # error of the latest attempt, if it raised
    draft: Optional[str]                    # latest LLM draft
    feedback: Optional[str]                 # checker findings for the next attempt
    drafts: List[Dict[str, Any]]            # per attempt: passed, finding codes, stats, usage, error
    report: str
    report_source: str
    final_validation: Dict[str, Any]
    trajectory: Annotated[List[Dict[str, Any]], operator.add]   # append-only


@dataclass
class Components:
    normalizer: DrugNormalizer
    planner: Planner
    retriever: Retriever                    # interactions + side effects only; FAERS is its own node
    faers: FaersRetriever
    generator: Generator
    llm_available: bool


def build_components(settings: Settings, llm=None) -> Components:
    """Load data and build the reused components from explicit settings.
    `llm` is an optional client with .complete(system, messages) (tests pass fakes)."""
    cfg = settings.to_config()
    return Components(
        normalizer=DrugNormalizer(cfg).load(),
        planner=Planner(),
        retriever=Retriever(InteractionRetriever(cfg).load(), SideEffectRetriever(cfg).load()),
        faers=FaersRetriever(enabled=settings.faers_enabled),
        generator=Generator(cfg, llm=llm),
        llm_available=settings.llm_configured or llm is not None,
    )


def retry_feedback(v: ValidationResult) -> str:
    lines = ["The automatic checker rejected your previous report (the assistant turn above). "
             "Return the complete corrected report. Fix every finding below, follow every rule in the "
             "system prompt, and use only the evidence in the first message.", "", "Findings:"]
    lines += [f"- [{f.code}] line {f.line if f.line is not None else '-'}: {f.message}" for f in v.findings]
    return "\n".join(lines)


def _normalizer_method(d: ResolvedDrug) -> str:
    if d.method == "exact":
        return "exact" if d.query.strip().lower() == (d.generic_name or "") else "alias"
    return {"rxnorm_api": "rxnorm", "rxnorm_not_in_local_vocab": "rxnorm_no_local_match"}.get(d.method, d.method)


def build_graph(settings: Settings, c: Components):
    """Define the topology and compile the graph. The only place edges are declared."""

    def timed(name: str, fn: Callable[[GraphState], Tuple[Dict[str, Any], str, Dict[str, Any]]]):
        def node(state: GraphState) -> Dict[str, Any]:
            t0 = time.perf_counter()
            update, status, detail = fn(state)
            ms = round((time.perf_counter() - t0) * 1000, 2)
            update["trajectory"] = [{"node": name, "status": status, "ms": ms, "detail": jsonable(detail)}]
            return update
        return node

    def evidence(plan, result) -> Dict[str, Any]:
        return jsonable(request_evidence(c.normalizer, c.generator.cfg.disclaimer, plan, result).to_dict())

    # ---------------------------------------------------------------- routes
    def route_after_plan(state: GraphState) -> str:
        return "template" if len(state["plan"]["resolved"]) < 2 else "retrieve"

    def route_generation(state: GraphState) -> str:
        if settings.mode == "deterministic" or not c.llm_available:
            return "template"
        return "generate_llm"

    def route_after_retrieve(state: GraphState) -> str:
        return "faers" if settings.faers_enabled else route_generation(state)

    def route_after_generate(state: GraphState) -> str:
        if state.get("llm_error") is None:
            return "validate"
        return "generate_llm" if state["llm_attempts"] < settings.max_llm_attempts else "template"

    def route_after_validate(state: GraphState) -> str:
        if state.get("report_source") in ("llm", "llm_retry"):
            return "finalize"
        return "generate_llm" if state["llm_attempts"] < settings.max_llm_attempts else "template"

    # ----------------------------------------------------------------- nodes
    def normalize(state):
        resolved = c.normalizer.resolve_many(state["input_drugs"])
        inputs = [{"input": d.query, "method": _normalizer_method(d), "resolved_to": d.generic_name,
                   "confidence": d.confidence} for d in resolved]
        detail = {"inputs": inputs, "resolved": sum(d.resolved for d in resolved),
                  "unresolved": sum(not d.resolved for d in resolved), "rxnorm_enabled": settings.rxnorm_enabled}
        return {"resolved": jsonable(resolved)}, "ok", detail

    def plan(state):
        p = c.planner.plan([ResolvedDrug(**d) for d in state["resolved"]])
        k = p.num_drugs
        expected = list(combinations(sorted(d.generic_name.lower() for d in p.resolved), 2))
        patched = sorted(p.pairs) != expected or len(p.pairs) != comb(k, 2)
        if patched:
            p.pairs = expected
        update = {"plan": plan_to_dict(p)}
        detail = {"unique_drugs": k, "pairs": len(p.pairs), "expected_pairs": comb(k, 2), "patched": patched,
                  "route": route_after_plan(update)}
        return update, ("patched" if patched else "ok"), detail

    def retrieve(state):
        p = plan_from_dict(state["plan"])
        result = c.retriever.execute(p)
        both = [pr for pr in p.pairs if pr in result.interactions and pr in result.no_data_pairs]
        neither = [pr for pr in p.pairs if pr not in result.interactions and pr not in result.no_data_pairs]
        result.no_data_pairs = [pr for pr in result.no_data_pairs if pr not in result.interactions] + neither
        update = {"retrieval": result_to_dict(result), "evidence": evidence(p, result)}
        detail = {"pairs_with_records": len(result.interactions), "no_data_pairs": len(result.no_data_pairs),
                  "records": result.total_interactions, "faers_consulted": settings.faers_enabled,
                  "patched_both": both, "patched_neither": neither, "route": route_after_retrieve(state)}
        return update, ("patched" if both or neither else "ok"), detail

    def faers(state):
        p, result = plan_from_dict(state["plan"]), result_from_dict(state["retrieval"])
        for a, b in result.no_data_pairs:   # same pairs as the legacy Retriever's FAERS step
            signals = c.faers.retrieve_pair(a, b)
            if signals:
                result.faers_signals[(a, b)] = signals
        update = {"retrieval": result_to_dict(result), "evidence": evidence(p, result)}
        detail = {"consulted_pairs": len(result.no_data_pairs), "pairs_with_signals": len(result.faers_signals),
                  "route": route_generation(state)}
        return update, "ok", detail

    def generate_llm(state):
        attempt = state.get("llm_attempts", 0) + 1
        feedback = state.get("feedback")
        p, result = plan_from_dict(state["plan"]), result_from_dict(state["retrieval"])
        drafts = list(state.get("drafts", []))
        detail = {"attempt": attempt, "model": f"{settings.llm_provider}:{settings.model_id}",
                  "with_feedback": bool(feedback)}
        try:
            text = c.generator.generate(p, result, prior_draft=state.get("draft") if feedback else None,
                                        feedback=feedback)
        except Exception as exc:  # any LLM failure consumes an attempt
            err = f"{type(exc).__name__}: {str(exc)[:200]}"
            drafts.append({"attempt": attempt, "error": err, "passed": False})
            detail.update(error=err, usage=getattr(c.generator.llm, "last_usage", None))
            return {"llm_attempts": attempt, "llm_error": err, "drafts": drafts}, "error", detail
        usage = getattr(c.generator.llm, "last_usage", None)
        drafts.append({"attempt": attempt, "usage": usage})
        detail["usage"] = usage
        return {"llm_attempts": attempt, "llm_error": None, "draft": text, "drafts": drafts}, "ok", detail

    def validate(state):
        attempt = state["llm_attempts"]
        v = validate_report(state["draft"], Evidence.from_dict(state["evidence"]), final=True)
        drafts = list(state["drafts"])
        drafts[-1] = {**drafts[-1], "passed": v.passed, "finding_codes": sorted(v.codes()), "stats": v.stats}
        update: Dict[str, Any] = {"drafts": drafts}
        if v.passed:
            update.update(report=state["draft"], report_source="llm" if attempt == 1 else "llm_retry", feedback=None)
        else:
            update["feedback"] = retry_feedback(v)
        detail = {"attempt": attempt, "passed": v.passed, "finding_codes": sorted(v.codes()),
                  "findings": len(v.findings), "route": route_after_validate({**state, **update})}
        return update, ("pass" if v.passed else "fail"), detail

    def template(state):
        p = plan_from_dict(state["plan"])
        result = result_from_dict(state.get("retrieval") or empty_result())
        if p.num_drugs < 2:
            reason = "deterministic_insufficient_input"
        elif settings.mode == "deterministic":
            reason = "deterministic"
        elif not c.llm_available:
            reason = "deterministic_no_llm"
        else:
            reason = "deterministic_fallback"
        update = {"report": c.generator.generate_deterministic(p, result), "report_source": reason}
        if "evidence" not in state:
            update["evidence"] = evidence(p, result)
        return update, "ok", {"reason": reason, "llm_attempts": state.get("llm_attempts", 0)}

    def finalize(state):
        report = c.generator.finalize(state["report"])   # disclaimer + provenance, exactly once
        v = validate_report(report, Evidence.from_dict(state["evidence"]), final=True)
        detail = {"report_source": state["report_source"], "final_validation_passed": v.passed,
                  "finding_codes": sorted(v.codes())}
        return {"report": report, "final_validation": v.to_dict()}, ("ok" if v.passed else "invalid"), detail

    # -------------------------------------------------------------- topology
    g = StateGraph(GraphState)
    for name, fn in [("normalize", normalize), ("plan", plan), ("retrieve", retrieve), ("faers", faers),
                     ("generate_llm", generate_llm), ("validate", validate), ("template", template),
                     ("finalize", finalize)]:
        g.add_node(name, timed(name, fn))
    g.add_edge(START, "normalize")
    g.add_edge("normalize", "plan")
    g.add_conditional_edges("plan", route_after_plan, {"template": "template", "retrieve": "retrieve"})
    g.add_conditional_edges("retrieve", route_after_retrieve,
                            {"faers": "faers", "template": "template", "generate_llm": "generate_llm"})
    g.add_conditional_edges("faers", route_generation, {"template": "template", "generate_llm": "generate_llm"})
    g.add_conditional_edges("generate_llm", route_after_generate,
                            {"validate": "validate", "generate_llm": "generate_llm", "template": "template"})
    g.add_conditional_edges("validate", route_after_validate,
                            {"finalize": "finalize", "generate_llm": "generate_llm", "template": "template"})
    g.add_edge("template", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


class PharmGuardGraph:
    """A compiled graph plus the components it runs on."""

    def __init__(self, settings: Settings, components: Optional[Components] = None):
        self.settings = settings
        self.components = components or build_components(settings)
        self.compiled = build_graph(settings, self.components)

    def with_mode(self, mode: str) -> "PharmGuardGraph":
        """Same components (data loaded once), different mode."""
        return PharmGuardGraph(self.settings.with_mode(mode), self.components)

    def run(self, drug_names: List[str]) -> Dict[str, Any]:
        """Validate the input list, run the graph, return the final (JSON-serializable) state."""
        if not drug_names:
            raise ValueError("At least one drug must be provided.")
        if len(drug_names) > MAX_DRUGS:
            raise ValueError("MVP supports up to %d drugs. Got %d." % (MAX_DRUGS, len(drug_names)))
        names = clean_drug_names(drug_names)  # raises InvalidDrugNameError
        t0 = time.perf_counter()
        state = self.compiled.invoke({"input_drugs": names, "trajectory": []},
                                     {"recursion_limit": 12 + 2 * self.settings.max_llm_attempts})
        state = dict(state)
        state["latency_seconds"] = round(time.perf_counter() - t0, 4)
        return state
