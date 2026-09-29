"""Every real-model number from one run: LLM-mode graph runs, the checker, the judge, and the
deterministic-vs-LLM comparison. scripts/run_llm_eval.py is the command; this module is
testable with fake LLMs.

Per generation provider:
- first-draft pass rate, recovery on retry, fallback rate, tokens per report, top finding
  codes (src/evaluation/llm_runs.py);
- checker metrics on the first drafts and on the reports users would see;
- faithfulness from the judge on the LLM reports that were shown (report_source llm or
  llm_retry), and on the template reports of the same cases (a check on the judge: the
  template only restates record fields);
- end-to-end graph latency per mode.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from statistics import median
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.evaluation.judge import ClaimJudge, Claim, Judgement, extract_claims, faithfulness, judgements_to_dicts
from src.evaluation.llm_runs import summarize_llm_states
from src.verification import Evidence, aggregate_stats

LLM_SOURCES = ("llm", "llm_retry")


class Throttled:
    """Wraps an LLM client so calls are at least min_interval seconds apart (free-tier RPM limits)."""

    def __init__(self, llm, min_interval: float, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.llm, self.min_interval, self._sleep, self._clock = llm, min_interval, sleep, clock
        self._last: Optional[float] = None
        self.calls = 0

    @property
    def last_usage(self):
        return getattr(self.llm, "last_usage", None)

    def complete(self, system, messages, **kw):
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()
        self.calls += 1
        return self.llm.complete(system=system, messages=messages, **kw)


class CachedLLM:
    """Stores each response on disk, keyed by provider, model, system prompt and messages, so a run
    stopped by a daily quota resumes without repeating calls. Errors are never cached."""

    def __init__(self, llm, label: str, cache_dir: Path):
        self.llm, self.label, self.dir = llm, label, Path(cache_dir)
        self.hits = self.misses = 0
        self.last_usage = None

    def complete(self, system, messages, **kw):
        key = hashlib.sha256(json.dumps([self.label, system, messages], sort_keys=True).encode()).hexdigest()
        path = self.dir / f"{key[:40]}.json"
        if path.exists():
            self.hits += 1
            blob = json.loads(path.read_text())
            self.last_usage = blob.get("usage")
            return blob["text"]
        self.misses += 1
        text = self.llm.complete(system=system, messages=messages, **kw)
        self.last_usage = getattr(self.llm, "last_usage", None)
        self.dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"label": self.label, "text": text, "usage": self.last_usage}))
        return text


def _p50(xs: Sequence[float]) -> Optional[float]:
    return round(median(xs) * 1000, 1) if xs else None


def judge_states(states: Sequence[Dict[str, Any]], judge: ClaimJudge, case_ids: Sequence[str],
                 prefix: str) -> Dict[str, Any]:
    claims: List[Claim] = []
    for cid, s in zip(case_ids, states):
        claims += extract_claims(s["report"], Evidence.from_dict(s["evidence"]), f"{prefix}:{cid}")
    js: List[Judgement] = [judge.judge(c) for c in claims]
    return {"claims": claims, "judgements": js, "summary": faithfulness(js)}


def evaluate_provider(det_graph, llm_graph, cases, judge: Optional[ClaimJudge], provider: str,
                      model: str, judge_template: bool = True) -> Dict[str, Any]:
    """Run every case in both modes; judge the shown LLM reports and the template reports."""
    det_states, llm_states, ids = [], [], []
    for case in cases:
        try:
            d = det_graph.run(case.input_drugs)
            l = llm_graph.run(case.input_drugs)
        except ValueError:
            continue
        det_states.append(d)
        llm_states.append(l)
        ids.append(case.case_id)
    runs = summarize_llm_states(llm_states)
    shown = [(cid, s) for cid, s in zip(ids, llm_states) if s["report_source"] in LLM_SOURCES]
    out: Dict[str, Any] = {
        "provider": provider, "model": model, "cases": len(ids),
        "llm_runs": runs,
        "checks": {"template": aggregate_stats([s["final_validation"]["stats"] for s in det_states]),
                   "llm_first_draft": runs["first_draft_checks"],
                   "llm_shown": (aggregate_stats([s["final_validation"]["stats"] for _, s in shown])
                                 if shown else None)},
        "latency_ms_p50": {"deterministic": _p50([s["latency_seconds"] for s in det_states]),
                           "llm_mode": _p50([s["latency_seconds"] for s in llm_states])},
        "llm_reports_shown": len(shown),
    }
    if judge is not None:
        j_llm = judge_states([s for _, s in shown], judge, [c for c, _ in shown], f"{provider}:llm")
        j_tpl = (judge_states(det_states, judge, ids, "template") if judge_template
                 else {"claims": [], "judgements": [], "summary": None})
        out["judge"] = {"llm_shown": j_llm["summary"], "template": j_tpl["summary"],
                        "calls": judge.calls, "usage": dict(judge.usage)}
        out["_claims"] = j_llm["claims"] + j_tpl["claims"]
        out["_judgements"] = j_llm["judgements"] + j_tpl["judgements"]
        out["judgements"] = judgements_to_dicts(out["_judgements"])
    return out


def call_budget(template_claims: int, cases: int, max_attempts: int, judge_template: bool = True) -> Dict[str, int]:
    """Upper bound on paid calls per generation provider, from the template reports' claim count
    (an LLM report is assumed to have about as many claims)."""
    gen = cases * max_attempts
    judge = template_claims * (2 if judge_template else 1)
    return {"generation_calls_max": gen, "generation_calls_min": cases, "judge_calls_est": judge,
            "total_max": gen + judge}
