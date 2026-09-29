"""The one-command LLM evaluation (src/evaluation/llm_eval.py, scripts/run_llm_eval.py) with fake LLMs."""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from src.agents.generator import Generator
from src.evaluation.llm_eval import Throttled, call_budget, evaluate_provider
from src.evaluation.test_cases import TEST_CASES
from src.graph import PharmGuardGraph, Settings, build_components
from src.graph.simulated import inject_cyp3a4
from tests.test_judge import RuleJudgeLLM
from src.evaluation.judge import ClaimJudge

ROOT = Path(__file__).resolve().parent.parent


class TemplateEchoLLM:
    """A fake generator: returns the template body for the drugs in the prompt; the first draft of
    every case with a finding carries a fabricated CYP3A4 mechanism (so the retry path runs)."""

    def __init__(self, det_graph):
        self.det, self.seen, self.calls = det_graph, set(), 0
        self.last_usage = {"input_tokens": 1000, "output_tokens": 200}

    def complete(self, system, messages, **kw):
        self.calls += 1
        block = re.search(r"<medication_list>\n(.*?)\n</medication_list>", messages[0]["content"], re.S).group(1)
        drugs = [x[2:] for x in block.splitlines()]
        body = self.det.run(drugs)["report"].split("\n---\n**Disclaimer.**")[0]
        key = tuple(drugs)
        if key not in self.seen:
            self.seen.add(key)
            bad = inject_cyp3a4(body)
            if bad:
                return bad
        return body


@pytest.fixture(scope="module")
def graphs(test_data_dir, sample_ingest_report):
    base = Settings(data_dir=test_data_dir, mode="deterministic")
    comps = build_components(base)
    det = PharmGuardGraph(base, comps)
    fake = TemplateEchoLLM(det)
    s = replace(base, mode="llm", llm_provider="gemini", llm_configured=True)
    c = replace(comps, generator=Generator(s.to_config(), llm=fake, provenance=comps.generator.provenance),
                llm_available=True, llm_label="fake")
    return det, PharmGuardGraph(s, c), fake


def test_one_run_gives_every_llm_number(graphs):
    det, llm, fake = graphs
    cases = [c for c in TEST_CASES if c.case_id in ("GER-01", "TXT-04", "EDG-01", "CV-01")]
    judge = ClaimJudge(RuleJudgeLLM())
    r = evaluate_provider(det, llm, cases, judge, "gemini", "gemini:fake")
    runs = r["llm_runs"]
    # Every case with a finding fails its first draft (fabrication) and recovers on the retry.
    assert runs["first_draft_pass_rate"] == 0.0 and runs["recovery_on_retry"] == 1.0 and runs["fallback_rate"] == 0.0
    assert runs["tokens_per_report"] == 2400.0 and dict(runs["top_finding_codes"])["UNSUPPORTED_MECHANISM"] >= 1
    assert r["checks"]["llm_first_draft"]["semantic_hallucination_rate"] > 0
    assert r["checks"]["llm_shown"]["semantic_hallucination_rate"] == 0 == r["checks"]["template"]["semantic_hallucination_rate"]
    assert r["judge"]["llm_shown"]["faithfulness"] == 1.0 and r["judge"]["template"]["faithfulness"] == 1.0
    assert r["judge"]["calls"] == r["judge"]["llm_shown"]["judged"] + r["judge"]["template"]["judged"]
    assert set(r["latency_ms_p50"]) == {"deterministic", "llm_mode"}
    assert r["llm_reports_shown"] == runs["report_sources"].get("llm_retry", 0) + runs["report_sources"].get("llm", 0)


def test_call_budget():
    assert call_budget(template_claims=100, cases=10, max_attempts=2) == {
        "generation_calls_max": 20, "generation_calls_min": 10, "judge_calls_est": 200, "total_max": 220}


def test_throttle_spaces_calls():
    t = [0.0]
    waits = []
    th = Throttled(RuleJudgeLLM('{"verdict": "supported"}'), 2.0, sleep=lambda w: (waits.append(w), t.__setitem__(0, t[0] + w)),
                   clock=lambda: t[0])
    for _ in range(3):
        th.complete("s", [{"role": "user", "content": "CLAIM:\nx\n\nCITED RECORDS (JSON):\n[]"}])
    assert waits == [2.0, 2.0] and th.calls == 3


def _script(*args, env_extra=None):
    import os
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env.update({"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "GOOGLE_API_KEY": "", **(env_extra or {})})
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "run_llm_eval.py"), *args], cwd=ROOT,
                          capture_output=True, text=True, env=env, timeout=300)


def test_script_without_keys_runs_nothing_and_says_so(tmp_path):
    p = _script("--profile", "sample", "--providers", "gemini", "--judge-provider", "anthropic",
                "--output-dir", str(tmp_path))
    assert p.returncode == 2 and "no API key" in p.stdout and not list(tmp_path.iterdir())


def test_plan_makes_no_calls_and_counts_claims(tmp_path):
    p = _script("--profile", "sample", "--plan", "--subset", "GER")
    assert p.returncode == 0, p.stderr
    assert "4 cases on the sample build" in p.stdout and "generation calls" in p.stdout


def test_research_build_is_refused():
    p = _script("--profile", "research", "--plan")
    assert p.returncode != 0 and "invalid choice" in p.stderr


def test_markdown_discloses_a_same_provider_judge_and_leaves_the_audit_unscored(graphs):
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_llm_eval
    from src.evaluation.judge import check_providers, prompt_info
    det, llm, _ = graphs
    r = evaluate_provider(det, llm, [c for c in TEST_CASES if c.case_id == "GER-01"], ClaimJudge(RuleJudgeLLM()),
                          "gemini", "gemini:fake")
    r["judge_disclosure"] = check_providers("gemini", "gemini", True)
    r.pop("_claims"), r.pop("_judgements")
    out = {"command": "python scripts/run_llm_eval.py", "date": "2026-09-29", "simulated": True,
           "data": {"data": "Data: synthetic.", "provenance_sha256": "0" * 64}, "judge_prompt": prompt_info(),
           "judge_model": "fake", "providers": [r], "audit": {"rows": 3, "fraction": 0.2, "seed": 1, "csv": "x.csv"}}
    md = run_llm_eval.to_markdown(out)
    assert "(SIMULATED LLM)" in md and "scripted fake" in md
    assert "same provider as the generator" in md
    assert "Cohen's κ: — until a human fills it in" in md
    assert prompt_info()["sha256"] in md


def test_cache_resumes_without_repeating_calls(tmp_path):
    from src.evaluation.llm_eval import CachedLLM
    inner = RuleJudgeLLM('{"verdict": "supported"}')
    msg = [{"role": "user", "content": "x"}]
    a = CachedLLM(inner, "gemini:m", tmp_path)
    assert a.complete("s", msg) == '{"verdict": "supported"}' and len(inner.calls) == 1
    b = CachedLLM(RuleJudgeLLM("never"), "gemini:m", tmp_path)          # a new process, same cache
    assert b.complete("s", msg) == '{"verdict": "supported"}' and (b.hits, b.misses) == (1, 0)
    assert b.last_usage == inner.last_usage
    assert CachedLLM(RuleJudgeLLM("other"), "anthropic:m", tmp_path).complete("s", msg) == "other"


def test_template_judging_can_be_skipped(graphs):
    det, llm, _ = graphs
    r = evaluate_provider(det, llm, [c for c in TEST_CASES if c.case_id == "GER-01"], ClaimJudge(RuleJudgeLLM()),
                          "gemini", "gemini:fake", judge_template=False)
    assert r["judge"]["template"] is None and r["judge"]["calls"] == r["judge"]["llm_shown"]["judged"]
