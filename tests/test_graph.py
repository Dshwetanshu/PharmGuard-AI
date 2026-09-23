"""LangGraph orchestration: routing, retry loop, trajectory, state, parity with the legacy pipeline."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.agents.generator import Generator
from src.evaluation.test_cases import TEST_CASES
from src.graph import PharmGuardGraph, Settings, build_components
from src.retrieval.faers_retriever import FaersRecord

DRUGS = ["lisinopril", "spironolactone", "aspirin"]


class FakeLLM:
    """Returns (or raises) scripted responses in order; records every call."""

    def __init__(self, *responses):
        self.responses, self.calls, self.last_usage = list(responses), [], None

    def complete(self, system, messages, **kw):
        self.calls.append(messages)
        item = self.responses.pop(0)
        self.last_usage = {"input_tokens": 1000 + len(self.calls), "output_tokens": 200}
        if isinstance(item, Exception):
            raise item
        return item


class StubFaers:
    enabled = True

    def retrieve_pair(self, a, b):
        return [FaersRecord("FAERS-abc123", a, b, "nausea", 600, "Major")]


@pytest.fixture(scope="module")
def settings(test_data_dir, sample_ingest_report):
    return Settings(data_dir=test_data_dir, mode="llm", llm_configured=False)


@pytest.fixture(scope="module")
def components(settings):
    return build_components(settings)


def graph(settings, components, llm=None, faers=None, **overrides):
    s = replace(settings, **overrides)
    c = replace(components,
                generator=Generator(components.generator.cfg, llm=llm) if llm else components.generator,
                llm_available=llm is not None or s.llm_configured,
                faers=faers or components.faers)
    return PharmGuardGraph(s, c)


def nodes(state):
    return [t["node"] for t in state["trajectory"]]


@pytest.fixture(scope="module")
def good_draft(sample_pipeline):
    return sample_pipeline.run(DRUGS, use_llm=False).report.split("\n---\n")[0]


@pytest.fixture(scope="module")
def bad_draft(good_draft):
    return good_draft.replace("hyperkalemia (PRR=14.20)", "hyperkalemia via CYP3A4 inhibition (PRR=14.20)")


# ---------------------------------------------------------------- LLM paths

def test_happy_path(settings, components, good_draft):
    llm = FakeLLM(good_draft)
    s = graph(settings, components, llm).run(DRUGS)
    assert s["report_source"] == "llm" and s["llm_attempts"] == 1
    assert nodes(s) == ["normalize", "plan", "retrieve", "generate_llm", "validate", "finalize"]
    assert s["final_validation"]["passed"] is True
    gen = s["trajectory"][3]["detail"]
    assert gen["usage"] == {"input_tokens": 1001, "output_tokens": 200} and gen["attempt"] == 1
    json.dumps(s)


def test_llm_error_once_then_success(settings, components, good_draft):
    s = graph(settings, components, FakeLLM(RuntimeError("503"), good_draft)).run(DRUGS)
    assert s["report_source"] == "llm_retry" and s["llm_attempts"] == 2
    assert [t["status"] for t in s["trajectory"] if t["node"] == "generate_llm"] == ["error", "ok"]
    assert s["drafts"][0]["error"].startswith("RuntimeError")


def test_llm_error_always_falls_back(settings, components, sample_pipeline):
    s = graph(settings, components, FakeLLM(RuntimeError("down"), RuntimeError("down"))).run(DRUGS)
    assert s["report_source"] == "deterministic_fallback" and s["llm_attempts"] == 2
    assert s["report"] == sample_pipeline.run(DRUGS, use_llm=False).report


def test_fail_then_pass_sends_findings_and_rejected_draft(settings, components, good_draft, bad_draft):
    llm = FakeLLM(bad_draft, good_draft)
    s = graph(settings, components, llm).run(DRUGS)
    assert s["report_source"] == "llm_retry"
    assert [t["status"] for t in s["trajectory"] if t["node"] == "validate"] == ["fail", "pass"]
    retry = llm.calls[1]
    assert [m["role"] for m in retry] == ["user", "assistant", "user"]
    assert "CYP3A4" in retry[1]["content"]                       # the rejected draft
    assert "[UNSUPPORTED_MECHANISM]" in retry[2]["content"] and "CYP3A4" in retry[2]["content"]
    assert s["trajectory"][-3]["detail"]["with_feedback"] is True


def test_fail_twice_falls_back(settings, components, bad_draft, sample_pipeline):
    s = graph(settings, components, FakeLLM(bad_draft, bad_draft)).run(DRUGS)
    assert s["report_source"] == "deterministic_fallback"
    assert [d["finding_codes"] for d in s["drafts"]] == [["UNSUPPORTED_MECHANISM"]] * 2
    assert "CYP3A4" not in s["report"]
    assert s["report"] == sample_pipeline.run(DRUGS, use_llm=False).report


def test_max_attempts_is_configurable(settings, components, good_draft, bad_draft):
    s = graph(settings, components, FakeLLM(bad_draft, bad_draft, good_draft), max_llm_attempts=3).run(DRUGS)
    assert s["report_source"] == "llm_retry" and s["llm_attempts"] == 3


# ---------------------------------------------------------- template routes

def test_deterministic_mode_never_calls_llm(settings, components):
    llm = FakeLLM()
    s = graph(settings, components, llm, mode="deterministic").run(DRUGS)
    assert s["report_source"] == "deterministic" and llm.calls == []
    assert "generate_llm" not in nodes(s)


def test_no_llm_configured(settings, components):
    s = graph(settings, components).run(DRUGS)
    assert s["report_source"] == "deterministic_no_llm"
    assert nodes(s) == ["normalize", "plan", "retrieve", "template", "finalize"]


@pytest.mark.parametrize("drugs", [["metformin"], ["lisinopril", "fictional_drug_xyz"], ["lipitor", "atorvastatin"]])
def test_fewer_than_two_drugs_go_straight_to_template(settings, components, good_draft, drugs):
    s = graph(settings, components, FakeLLM(good_draft)).run(drugs)
    assert s["report_source"] == "deterministic_insufficient_input"
    assert nodes(s) == ["normalize", "plan", "template", "finalize"]
    assert s["final_validation"]["passed"] is True


def test_faers_on_and_off(settings, components):
    on = graph(settings, components, faers=StubFaers(), faers_enabled=True).run(["metformin", "levothyroxine"])
    assert "faers" in nodes(on)
    assert on["trajectory"][nodes(on).index("faers")]["detail"] == {
        "consulted_pairs": 1, "pairs_with_signals": 1, "route": "template"}
    assert on["retrieval"]["no_data_pairs"] == [["levothyroxine", "metformin"]]
    assert "FAERS Spontaneous Reports (unvalidated)" in on["report"] and "[FAERS:FAERS-abc123]" in on["report"]
    off = graph(settings, components, faers=StubFaers()).run(["metformin", "levothyroxine"])
    assert "faers" not in nodes(off) and "FAERS" not in off["report"]


# ------------------------------------------------------ trajectory & checks

def test_trajectory_records_branch_decisions(settings, components):
    s = graph(settings, components).run(["Prinivil", "spironolactone", "metfromin", "fictional_drug_xyz"])
    for t in s["trajectory"]:
        assert set(t) == {"node", "status", "ms", "detail"}
    methods = {i["input"]: i["method"] for i in s["trajectory"][0]["detail"]["inputs"]}
    assert methods == {"Prinivil": "alias", "spironolactone": "exact", "metfromin": "fuzzy",
                       "fictional_drug_xyz": "unresolved"}
    assert s["trajectory"][1]["detail"]["expected_pairs"] == 3
    assert s["trajectory"][2]["detail"]["faers_consulted"] is False


def test_plan_and_retrieve_invariants_are_patched_and_logged(settings, components):
    class BadPlanner:
        def plan(self, resolved):
            from src.agents.planner import Planner
            p = Planner().plan(resolved)
            p.pairs = p.pairs[:1]      # drop pairs
            return p

    class BadRetriever:
        def execute(self, plan):
            r = components.retriever.execute(plan)
            r.no_data_pairs = r.no_data_pairs[1:] + list(r.interactions)[:1]   # one "neither", one "both"
            return r

    g = PharmGuardGraph(settings, replace(components, planner=BadPlanner(), retriever=BadRetriever()))
    s = g.run(["lisinopril", "spironolactone", "metformin"])
    plan_t, ret_t = s["trajectory"][1], s["trajectory"][2]
    assert plan_t["status"] == "patched" and len(s["plan"]["pairs"]) == 3
    assert ret_t["status"] == "patched" and ret_t["detail"]["patched_both"] and ret_t["detail"]["patched_neither"]
    with_records = {tuple(x["pair"]) for x in s["retrieval"]["interactions"]}
    no_data = {tuple(p) for p in s["retrieval"]["no_data_pairs"]}
    assert with_records.isdisjoint(no_data) and with_records | no_data == {tuple(p) for p in s["plan"]["pairs"]}


def test_settings_do_not_read_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMGUARD_TOP_K", "99")
    monkeypatch.setenv("PHARMGUARD_FAERS_ENABLED", "true")
    cfg = Settings(data_dir=tmp_path).to_config()
    assert (cfg.retrieval.top_k, cfg.retrieval.faers_enabled, cfg.paths.data_dir) == (5, False, tmp_path)


# -------------------------------------------------------------------- parity

def test_deterministic_graph_matches_legacy_pipeline_for_all_48_cases(settings, components, sample_pipeline):
    g = graph(settings, components, mode="deterministic")
    mismatches = []
    for case in TEST_CASES:
        s = g.run(case.input_drugs)
        json.dumps(s)
        if s["report"] != sample_pipeline.run(case.input_drugs, use_llm=False).report:
            mismatches.append(case.case_id)
    assert mismatches == []


def test_mermaid_diagram_in_docs_is_current(settings, components):
    doc = (Path(__file__).resolve().parent.parent / "docs" / "graph.md").read_text()
    mermaid = graph(settings, components).compiled.get_graph().draw_mermaid()
    assert f"```mermaid\n{mermaid.strip()}\n```" in doc
