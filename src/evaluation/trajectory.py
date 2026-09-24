"""Trajectory evaluation: score every step of a run, not just the final report.

Three parts, all offline and without API keys:
- Step scoring (A): each of the 48 cases, per step (normalize, plan, retrieve,
  route, finalize); task completion = every step correct.
- Fault suite (B): scripted fake LLMs built from each case's deterministic
  report with the checker's fault types. Each scenario has an expected path and
  report_source, and every run is checked against orchestration invariants.
- Invariants are computed independently of the graph's own claims: the final
  report is re-validated with src.verification.validate_report, the plan is
  recomputed from the resolved drugs, error classes are re-classified with
  src.llm.is_transient_llm_error, and the fake LLM and FAERS stub keep their
  own call logs. That's what lets seeded bugs (src/evaluation/seeded_bugs.py)
  show up.

All data is synthetic sample data. With fake LLMs, latency measures
orchestration overhead only.
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from itertools import combinations
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.agents.generator import STATISTICAL_HEADING, Generator
from src.data.canonical import build_alias_map
from src.evaluation.hand_labels import canonical_pair
from src.evaluation.test_cases import SUSPECTED_LABEL_ERRORS, TEST_CASES, TestCase
from src.graph.simulated import inject_cyp3a4
from src.llm import is_transient_llm_error
from src.observability import Tracing
from src.verification import Evidence, validate_report

STEPS = ("normalize", "plan", "retrieve", "route", "finalize")
FINDING_HEADINGS = ("## Major Findings", "## Moderate Findings", "## Minor Findings", "## Severity Not Graded")
LATENCY_LABEL = "orchestration overhead only (fake LLMs, synthetic sample data, no network)"


def _clean_name(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip()).lower()


def _body(report: str) -> str:
    """Report text without the disclaimer/provenance footer."""
    return report.split("\n---\n**Disclaimer.**")[0]


# ================================================================ A: steps

def expected_route(case_resolved_unique: int, mode: str, llm_available: bool) -> str:
    if case_resolved_unique < 2:
        return "deterministic_insufficient_input"
    if mode == "deterministic":
        return "deterministic"
    return "deterministic_no_llm" if not llm_available else "llm"


def score_steps(case: TestCase, state: Dict[str, Any], *, mode: str, llm_available: bool,
                alias_map: Dict[str, str], disclaimer: str, provenance: str,
                profile: str = "sample") -> Dict[str, Any]:
    out: Dict[str, Any] = {"case_id": case.case_id, "subset": case.case_id.split("-")[0]}
    reasons: Dict[str, str] = {}

    # 1. normalize: every input resolves to its expected drug, or stays unresolved when it should.
    by_input = {_clean_name(r["query"]): r for r in state["resolved"]}
    exp_resolved, exp_unresolved = case.expectations(profile)
    expected_res = {_clean_name(k): v for k, v in exp_resolved.items()}
    expected_unres = {_clean_name(q) for q in exp_unresolved}
    bad = []
    for q in (_clean_name(x) for x in case.input_drugs):
        r = by_input.get(q)
        if r is None:
            bad.append(f"{q!r}: missing")
        elif q in expected_unres:
            if r["resolved"]:
                bad.append(f"{q!r}: resolved to {r['generic_name']!r}, expected unresolved")
        elif not r["resolved"]:
            bad.append(f"{q!r}: unresolved")
        elif q in expected_res and r["generic_name"] != expected_res[q]:
            bad.append(f"{q!r}: {r['generic_name']!r} != expected {expected_res[q]!r}")
    out["normalize"] = not bad
    if bad:
        reasons["normalize"] = "; ".join(bad)

    # 2. plan: exactly C(k,2) pairs for the k unique resolved drugs (recomputed here).
    names = sorted({r["generic_name"].lower() for r in state["resolved"] if r["resolved"] and r["generic_name"]})
    expected_pairs = [list(p) for p in combinations(names, 2)]
    plan_pairs = sorted(state["plan"]["pairs"])
    plan_node = next(t for t in state["trajectory"] if t["node"] == "plan")
    out["plan"] = plan_pairs == expected_pairs and plan_node["status"] == "ok"
    if not out["plan"]:
        reasons["plan"] = f"{len(plan_pairs)} pairs (status {plan_node['status']}), expected {len(expected_pairs)}"

    # 3. retrieve: partition holds, and hand-labelled pairs are retrieved.
    retrieval = state.get("retrieval")
    labelled = {canonical_pair(a, b, alias_map) for a, b in case.known_interaction_pairs}
    suspected = {canonical_pair(a, b, alias_map) for a, b in SUSPECTED_LABEL_ERRORS.get(case.case_id, [])}
    if retrieval is None:   # routed to the template before retrieval (fewer than 2 drugs)
        missed, part_ok = sorted(labelled), not plan_pairs
    else:
        with_records = {tuple(x["pair"]) for x in retrieval["interactions"]}
        no_data = {tuple(p) for p in retrieval["no_data_pairs"]}
        planned = {tuple(p) for p in plan_pairs}
        part_ok = with_records.isdisjoint(no_data) and with_records | no_data == planned
        missed = sorted(labelled - with_records)
    missed_real = [p for p in missed if p not in suspected]
    out["retrieve"] = part_ok and not missed_real
    out["suspected_label_misses"] = [list(p) for p in missed if p in suspected]
    if not out["retrieve"]:
        reasons["retrieve"] = ("partition broken; " if not part_ok else "") + (
            f"missed labelled {missed_real}" if missed_real else "")

    # 4. route
    exp = expected_route(len(names), mode, llm_available)
    out["route"] = state["report_source"] == exp
    if not out["route"]:
        reasons["route"] = f"{state['report_source']} != expected {exp}"

    # 5. finalize: independent validation; disclaimer and provenance exactly once.
    report = state["report"]
    v = validate_report(report, Evidence.from_dict(state["evidence"]), final=True)
    counts = (report.count(disclaimer), report.count(provenance))
    out["finalize"] = v.passed and counts == (1, 1)
    if not out["finalize"]:
        reasons["finalize"] = f"validation {sorted(v.codes())}, disclaimer/provenance counts {counts}"

    out["completed"] = all(out[s] for s in STEPS)
    out["reasons"] = reasons
    return out


def summarize_steps(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def acc(rs):
        n = len(rs)
        return {**{s: round(sum(r[s] for r in rs) / n, 4) for s in STEPS},
                "completion": round(sum(r["completed"] for r in rs) / n, 4), "cases": n}
    subsets = defaultdict(list)
    for r in rows:
        subsets[r["subset"]].append(r)
    return {
        "overall": acc(rows),
        "per_subset": {k: acc(v) for k, v in sorted(subsets.items())},
        "failing": [{"case_id": r["case_id"], "failed_steps": [s for s in STEPS if not r[s]], "reasons": r["reasons"]}
                    for r in rows if not r["completed"]],
        "suspected_label_misses": {r["case_id"]: r["suspected_label_misses"] for r in rows
                                   if r["suspected_label_misses"]},
    }


# ======================================================= B: fault scenarios

class FakeBadRequest(Exception):
    """A non-transient API error (like the Sonnet 5 temperature 400)."""
    status_code = 400


class ScriptedFakeLLM:
    """Returns (or raises) scripted items in order, logging every call."""

    def __init__(self, items: List[Any]):
        self.items, self.calls, self.raised, self.returned, self.last_usage = list(items), 0, [], [], None

    def complete(self, system, messages, **kw):
        self.calls += 1
        item = self.items.pop(0) if self.items else FakeBadRequest("script exhausted")
        self.last_usage = {"input_tokens": 0, "output_tokens": 0}   # fake: no real tokens
        if isinstance(item, BaseException):
            self.raised.append((self.calls, item))
            raise item
        self.returned.append(item)
        return item


class CountingFaers:
    enabled = True

    def __init__(self):
        self.calls = 0

    def retrieve_pair(self, a, b):
        self.calls += 1
        return []   # consulted, but no signals, so the report text is unchanged


CLAIM_HEADINGS = FINDING_HEADINGS + (f"## {STATISTICAL_HEADING}",)


def _finding_line_indices(lines: List[str]) -> List[int]:
    """Cited claim lines: curated findings and statistical signals."""
    out, in_findings = [], False
    for i, ln in enumerate(lines):
        if ln.startswith("## "):
            in_findings = ln in CLAIM_HEADINGS
        elif in_findings and ln.startswith("- ") and " [" in ln:
            out.append(i)
    return out


def fault_mechanism(body: str, isoform: str = "CYP3A4") -> Optional[str]:
    if isoform == "CYP3A4":
        return inject_cyp3a4(body)
    lines = body.splitlines()
    for i in _finding_line_indices(lines):
        if isoform not in lines[i]:
            j = lines[i].find(" [")
            lines[i] = lines[i][:j] + f" via {isoform} inhibition" + lines[i][j:]
            return "\n".join(lines)
    return None


def fault_omit_major(body: str) -> Optional[str]:
    lines = body.splitlines()
    if "## Major Findings" not in lines:
        return None
    first = lines[lines.index("## Major Findings") + 1]
    m = re.match(r"- \*\*([^*]+) \+ ([^*]+)\*\*", first)
    if not m:
        return None
    pair = {m.group(1), m.group(2)}

    def is_pair_line(ln: str) -> bool:   # records print in their source's drug order: match both
        mm = re.match(r"- \*\*([^*]+) \+ ([^*]+)\*\*", ln)
        return bool(mm) and {mm.group(1), mm.group(2)} == pair

    kept = [ln for ln in lines if not is_pair_line(ln)]
    # drop severity headings left empty
    out = []
    for i, ln in enumerate(kept):
        if ln in FINDING_HEADINGS and (i + 1 >= len(kept) or not kept[i + 1].startswith("- ")):
            continue
        out.append(ln)
    return "\n".join(out)


def fault_absence_safe(body: str) -> Optional[str]:
    lines = body.splitlines()
    if "### No Curated Interaction Data" not in lines:
        return None
    for i in range(lines.index("### No Curated Interaction Data") + 1, len(lines)):
        if lines[i].startswith("- "):
            lines[i] += " — no known interaction; safe to combine"
            return "\n".join(lines)
    return None


def fault_phantom(body: str) -> Optional[str]:
    lines = body.splitlines()
    idx = _finding_line_indices(lines)
    if not idx:
        return None
    lines[idx[0]] = re.sub(r"\[([A-Za-z]+):[^\]]+\]", r"[\1:TS-99999999]", lines[idx[0]], count=1)
    return "\n".join(lines)


def fault_severity_flip(body: str) -> Optional[str]:
    flip = {"## Major Findings": "## Minor Findings", "## Moderate Findings": "## Major Findings",
            "## Minor Findings": "## Major Findings", "## Severity Not Graded": "## Major Findings"}
    lines = body.splitlines()
    for i, ln in enumerate(lines):
        if ln in flip:
            lines[i] = flip[ln]
            return "\n".join(lines)
    return None


def fault_signal_severity(body: str) -> Optional[str]:
    """Attach a severity word to the first statistical signal (signals have no severity)."""
    lines, in_signals = body.splitlines(), False
    for i, ln in enumerate(lines):
        if ln.startswith("## "):
            in_signals = ln == f"## {STATISTICAL_HEADING}"
        elif in_signals and ln.startswith("- ") and ": PRR " in ln:
            lines[i] = ln.replace(": PRR ", " (major risk): PRR ", 1)
            return "\n".join(lines)
    return None


def fault_uncited(body: str) -> Optional[str]:
    lines = body.splitlines()
    idx = _finding_line_indices(lines)
    if not idx:
        return None
    lines[idx[0]] = re.sub(r" \[[^\]]+\]", "", lines[idx[0]])
    return "\n".join(lines)


@dataclass(frozen=True)
class Scenario:
    name: str
    build: Callable[[str], Optional[List[Any]]]    # clean body -> scripted items, or None (not applicable)
    outcomes: Tuple[str, ...]                      # per attempt: pass | fail | err_t | err_nt


def _two(f1, f2=None):
    def build(body):
        a, b = f1(body), (f2(body) if f2 else body)
        return None if a is None or b is None else [a, b]
    return build


SCENARIOS: List[Scenario] = [
    Scenario("clean", lambda b: [b], ("pass",)),
    Scenario("transient_error_once", lambda b: [TimeoutError("read timeout"), b], ("err_t", "pass")),
    Scenario("transient_error_always", lambda b: [TimeoutError("t1"), TimeoutError("t2")], ("err_t", "err_t")),
    Scenario("non_transient_error_once", lambda b: [FakeBadRequest("temperature is not supported"), b],
             ("err_nt",)),
    Scenario("mechanism_once", _two(fault_mechanism), ("fail", "pass")),
    Scenario("mechanism_always", _two(fault_mechanism, lambda b: fault_mechanism(b, "CYP2D6")), ("fail", "fail")),
    Scenario("omit_major_once", _two(fault_omit_major), ("fail", "pass")),
    Scenario("absence_safe_once", _two(fault_absence_safe), ("fail", "pass")),
    Scenario("phantom_citation_once", _two(fault_phantom), ("fail", "pass")),
    Scenario("severity_flip_once", _two(fault_severity_flip), ("fail", "pass")),
    Scenario("uncited_claim_once", _two(fault_uncited), ("fail", "pass")),
    Scenario("signal_severity_once", _two(fault_signal_severity), ("fail", "pass")),
    Scenario("different_fault_on_retry", _two(fault_mechanism, fault_uncited), ("fail", "fail")),
    Scenario("retry_repeats_rejected_draft", _two(fault_mechanism, fault_mechanism), ("fail", "fail")),
]


def expected_path(outcomes: Tuple[str, ...], *, eligible: bool, llm_mode: bool, faers_visit: bool,
                  max_attempts: int) -> Tuple[List[str], str]:
    """The spec, restated independently of the graph: node sequence and report_source."""
    if not eligible:
        return ["normalize", "plan", "template", "finalize"], "deterministic_insufficient_input"
    pre = ["normalize", "plan", "retrieve"] + (["faers"] if faers_visit else [])
    if not llm_mode:
        return pre + ["template", "finalize"], "deterministic"
    path = list(pre)
    for attempt, o in enumerate(outcomes[:max_attempts], start=1):
        path.append("generate_llm")
        if o in ("pass", "fail"):
            path.append("validate")
        if o == "pass":
            return path + ["finalize"], "llm" if attempt == 1 else "llm_retry"
        if o == "err_nt":
            break
    return path + ["template", "finalize"], "deterministic_fallback"


# ============================================================== invariants

INVARIANTS = ("ends_at_finalize", "plan_complete", "partition_holds", "faers_only_when_needed",
              "llm_attempts_within_budget", "non_transient_never_retried", "no_unvalidated_llm_text",
              "exhausted_fallback_matches_deterministic", "final_report_valid", "every_node_timed",
              "state_json_serializable")


@dataclass
class RunContext:
    state: Dict[str, Any]
    baseline_report: str               # this case's deterministic-mode report
    max_attempts: int
    faers_enabled: bool
    generator: Generator
    llm: Optional[ScriptedFakeLLM] = None
    faers: Optional[CountingFaers] = None


def check_invariants(ctx: RunContext) -> Dict[str, Tuple[bool, str]]:
    s, res = ctx.state, {}
    nodes = [t["node"] for t in s["trajectory"]]

    res["ends_at_finalize"] = (nodes[-1:] == ["finalize"], f"last node {nodes[-1:]}")

    names = sorted({r["generic_name"].lower() for r in s["resolved"] if r["resolved"] and r["generic_name"]})
    exp = [list(p) for p in combinations(names, 2)]
    res["plan_complete"] = (sorted(s["plan"]["pairs"]) == exp, f"{len(s['plan']['pairs'])} pairs vs {len(exp)}")

    r = s.get("retrieval")
    if r is None:
        res["partition_holds"] = (not s["plan"]["pairs"], "no retrieval but pairs planned")
    else:
        rec = {tuple(x["pair"]) for x in r["interactions"]}
        nod = {tuple(p) for p in r["no_data_pairs"]}
        planned = {tuple(p) for p in s["plan"]["pairs"]}
        res["partition_holds"] = (rec.isdisjoint(nod) and rec | nod == planned, "records/no-data partition broken")

    needs_faers = ctx.faers_enabled and bool(r and r["no_data_pairs"])
    stub_calls = ctx.faers.calls if ctx.faers else 0
    ok = ("faers" in nodes) == needs_faers and (stub_calls > 0) == (needs_faers and bool(ctx.faers))
    res["faers_only_when_needed"] = (ok, f"faers node {'faers' in nodes}, stub calls {stub_calls}, needed {needs_faers}")

    calls = ctx.llm.calls if ctx.llm else 0
    gen_nodes = nodes.count("generate_llm")
    ok = s.get("llm_attempts", 0) <= ctx.max_attempts and calls <= ctx.max_attempts and gen_nodes <= ctx.max_attempts
    res["llm_attempts_within_budget"] = (ok, f"attempts {s.get('llm_attempts', 0)}, calls {calls}, "
                                             f"generate_llm nodes {gen_nodes}, max {ctx.max_attempts}")

    retried = [i for i, e in (ctx.llm.raised if ctx.llm else []) if not is_transient_llm_error(e) and i < calls]
    res["non_transient_never_retried"] = (not retried, f"calls after non-transient error at call(s) {retried}")

    report, source = s["report"], s["report_source"]
    evidence = Evidence.from_dict(s["evidence"])
    if source in ("llm", "llm_retry"):
        drafts = [ctx.generator.finalize(d) for d in (ctx.llm.returned if ctx.llm else [])]
        ok = report in drafts and validate_report(report, evidence, final=True).passed
        res["no_unvalidated_llm_text"] = (ok, "LLM report shown that isn't an independently valid draft")
    else:
        rejected = [ctx.generator.finalize(d) for d in (ctx.llm.returned if ctx.llm else [])
                    if not validate_report(ctx.generator.finalize(d), evidence, final=True).passed]
        res["no_unvalidated_llm_text"] = (report not in rejected, "a rejected LLM draft reached the report")

    if source == "deterministic_fallback":
        res["exhausted_fallback_matches_deterministic"] = (report == ctx.baseline_report,
                                                           "fallback report differs from deterministic mode")
    else:
        res["exhausted_fallback_matches_deterministic"] = (True, "n/a")

    v = validate_report(report, evidence, final=True)
    res["final_report_valid"] = (v.passed, f"findings {sorted(v.codes())}")

    res["every_node_timed"] = (bool(s["trajectory"]) and all(isinstance(t.get("ms"), (int, float)) and t["ms"] >= 0
                                                             for t in s["trajectory"]), "node without timing")
    try:
        json.dumps(s)
        res["state_json_serializable"] = (True, "")
    except (TypeError, ValueError) as exc:
        res["state_json_serializable"] = (False, str(exc))
    return res


# ================================================================= drivers

@dataclass
class Harness:
    """Shared, loaded components plus per-case deterministic baselines."""
    graph_cls: Any
    settings: Any
    components: Any
    alias_map: Dict[str, str]
    profile: str = "sample"
    baselines: Dict[str, str] = field(default_factory=dict)
    eligible: Dict[str, bool] = field(default_factory=dict)
    has_no_data: Dict[str, bool] = field(default_factory=dict)

    @classmethod
    def build(cls, settings, components, vocab_df, profile: str = "sample"):
        from src.graph import PharmGuardGraph
        h = cls(PharmGuardGraph, settings, components, build_alias_map(vocab_df), profile)
        det = PharmGuardGraph(replace(settings, mode="deterministic"), components, Tracing())
        for case in TEST_CASES:
            s = det.run(case.input_drugs)
            h.baselines[case.case_id] = s["report"]
            h.eligible[case.case_id] = len(s["plan"]["resolved"]) >= 2
            h.has_no_data[case.case_id] = bool(s.get("retrieval") and s["retrieval"]["no_data_pairs"])
        return h

    def graph(self, *, mode="llm", llm=None, faers=None, faers_enabled=False, llm_available=None):
        c = self.components
        c = replace(c, generator=Generator(c.generator.cfg, llm=llm, provenance=c.generator.provenance)
                    if llm is not None else c.generator,
                    llm_available=(llm is not None) if llm_available is None else llm_available,
                    faers=faers or c.faers)
        return self.graph_cls(replace(self.settings, mode=mode, faers_enabled=faers_enabled), c, Tracing())


def run_step_scoring(h: Harness) -> Dict[str, Any]:
    configs = {"deterministic": dict(mode="deterministic"),
               "llm_mode_without_key": dict(mode="llm", llm_available=False)}
    out, invariant_runs = {}, []
    for name, kw in configs.items():
        g = h.graph(**kw)
        rows = []
        for case in TEST_CASES:
            state = g.run(case.input_drugs)
            rows.append(score_steps(case, state, mode=kw["mode"], llm_available=False, alias_map=h.alias_map,
                                    disclaimer=g.components.generator.cfg.disclaimer,
                                    provenance=g.components.generator.provenance, profile=h.profile))
            invariant_runs.append(check_invariants(RunContext(state, h.baselines[case.case_id],
                                                              h.settings.max_llm_attempts, False,
                                                              g.components.generator)))
        out[name] = {"summary": summarize_steps(rows), "rows": rows}
    out["llm_mode_with_key"] = None   # "—": no API key; LLM mode is exercised by the fault suite
    return {"step_scoring": out, "invariant_runs": invariant_runs}


def run_fault_suite(h: Harness, cases: Optional[List[TestCase]] = None) -> Dict[str, Any]:
    cases = cases or TEST_CASES
    runs, skipped = [], Counter()
    for case in cases:
        body = _body(h.baselines[case.case_id])
        for faers_enabled in (False, True):
            scenarios = SCENARIOS if not faers_enabled else [SCENARIOS[0]]   # FAERS pass: clean scenario
            for sc in scenarios:
                items = sc.build(body)
                if items is None:
                    skipped[sc.name] += 1
                    continue
                llm, faers = ScriptedFakeLLM(items), (CountingFaers() if faers_enabled else None)
                g = h.graph(llm=llm, faers=faers, faers_enabled=faers_enabled)
                state = g.run(case.input_drugs)
                exp_path, exp_source = expected_path(
                    sc.outcomes, eligible=h.eligible[case.case_id], llm_mode=True,
                    faers_visit=faers_enabled and h.has_no_data[case.case_id],
                    max_attempts=h.settings.max_llm_attempts)
                inv = check_invariants(RunContext(state, h.baselines[case.case_id], h.settings.max_llm_attempts,
                                                  faers_enabled, g.components.generator, llm, faers))
                runs.append({
                    "case_id": case.case_id, "scenario": sc.name + ("+faers" if faers_enabled else ""),
                    "recoverable": sc.outcomes[-1] == "pass" and len(sc.outcomes) > 1 and h.eligible[case.case_id]
                    and "err_nt" not in sc.outcomes,
                    "path": [t["node"] for t in state["trajectory"]], "expected_path": exp_path,
                    "report_source": state["report_source"], "expected_source": exp_source,
                    "llm_calls": llm.calls, "invariants": {k: v[0] for k, v in inv.items()},
                    "violations": {k: v[1] for k, v in inv.items() if not v[0]},
                    "node_ms": [(t["node"], t["ms"]) for t in state["trajectory"]],
                    "latency_ms": round(state["latency_seconds"] * 1000, 3),
                })
    return {"runs": runs, "skipped": dict(skipped)}


def _pct(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    vs = sorted(values)
    return round(vs[min(len(vs) - 1, int(round(q * (len(vs) - 1))))], 3)


def summarize_faults(runs: List[Dict[str, Any]], extra_invariant_runs: List[Dict] = ()) -> Dict[str, Any]:
    inv_rows = [r["invariants"] for r in runs] + [{k: v[0] for k, v in x.items()} for x in extra_invariant_runs]
    per_scenario = {}
    for name in sorted({r["scenario"] for r in runs}, key=lambda n: [s.name for s in SCENARIOS].index(n.split("+")[0])):
        rs = [r for r in runs if r["scenario"] == name]
        per_scenario[name] = {
            "runs": len(rs),
            "path_match": round(sum(r["path"] == r["expected_path"] for r in rs) / len(rs), 4),
            "source_match": round(sum(r["report_source"] == r["expected_source"] for r in rs) / len(rs), 4),
            "invariants_all_pass": round(sum(all(r["invariants"].values()) for r in rs) / len(rs), 4),
            "llm_calls_mean": round(statistics.mean(r["llm_calls"] for r in rs), 3),
            "expected_source": Counter(r["expected_source"] for r in rs).most_common(1)[0][0],
        }
    recoverable = [r for r in runs if r["recoverable"]]
    node_ms = defaultdict(list)
    for r in runs:
        for n, ms in r["node_ms"]:
            node_ms[n].append(ms)
    return {
        "runs": len(runs),
        "invariant_pass_rate": {k: round(sum(x[k] for x in inv_rows) / len(inv_rows), 4) for k in INVARIANTS},
        "invariant_runs": len(inv_rows),
        "path_match_rate": round(sum(r["path"] == r["expected_path"] for r in runs) / len(runs), 4),
        "source_match_rate": round(sum(r["report_source"] == r["expected_source"] for r in runs) / len(runs), 4),
        "recovery_rate": round(sum(r["report_source"] == "llm_retry" for r in recoverable) / len(recoverable), 4)
        if recoverable else None,
        "llm_calls_per_case": round(statistics.mean(r["llm_calls"] for r in runs), 3),
        "latency_label": LATENCY_LABEL,
        "latency_ms_per_node": {n: {"p50": _pct(v, 0.5), "p95": _pct(v, 0.95)} for n, v in sorted(node_ms.items())},
        "latency_ms_end_to_end": {"p50": _pct([r["latency_ms"] for r in runs], 0.5),
                                  "p95": _pct([r["latency_ms"] for r in runs], 0.95)},
        "per_scenario": per_scenario,
        "mismatches": [{k: r[k] for k in ("case_id", "scenario", "path", "expected_path", "report_source",
                                          "expected_source", "violations")}
                       for r in runs if r["path"] != r["expected_path"] or r["report_source"] != r["expected_source"]
                       or r["violations"]],
    }
