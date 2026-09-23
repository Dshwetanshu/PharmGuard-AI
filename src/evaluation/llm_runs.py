"""Summarise LLM-mode graph runs: first-draft pass rate, retry recovery, fallback, tokens, finding codes.

Input is the list of final graph states (src/graph). Cases that never reach
the LLM (fewer than 2 drugs) are excluded from the LLM rates and counted
separately.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from src.verification import aggregate_stats


def _rate(n: int, d: int) -> Optional[float]:
    return round(n / d, 4) if d else None


def summarize_llm_states(states: List[Dict[str, Any]]) -> Dict[str, Any]:
    eligible = [s for s in states if s.get("drafts")]
    first_pass = [s for s in eligible if s["drafts"][0].get("passed")]
    first_fail = [s for s in eligible if not s["drafts"][0].get("passed")]
    recovered = [s for s in first_fail if s["report_source"] == "llm_retry"]
    fallback = [s for s in eligible if s["report_source"] == "deterministic_fallback"]
    tokens = [sum((d.get("usage") or {}).get("input_tokens", 0) + (d.get("usage") or {}).get("output_tokens", 0)
                  for d in s["drafts"]) for s in eligible if any(d.get("usage") for d in s["drafts"])]
    codes = Counter(c for s in eligible for d in s["drafts"] for c in d.get("finding_codes", []))
    errors = Counter(d["error"].split(":")[0] for s in eligible for d in s["drafts"] if d.get("error"))
    first_stats = [s["drafts"][0]["stats"] for s in eligible if s["drafts"][0].get("stats")]
    return {
        "cases": len(states),
        "llm_eligible_cases": len(eligible),
        "not_eligible_insufficient_input": sum(s["report_source"] == "deterministic_insufficient_input"
                                               for s in states),
        "first_draft_pass_rate": _rate(len(first_pass), len(eligible)),
        "recovery_on_retry": _rate(len(recovered), len(first_fail)),
        "fallback_rate": _rate(len(fallback), len(eligible)),
        "tokens_per_report": round(sum(tokens) / len(tokens), 1) if tokens else None,
        "report_sources": dict(Counter(s["report_source"] for s in states)),
        "top_finding_codes": codes.most_common(10),
        "llm_errors": dict(errors),
        "first_draft_checks": aggregate_stats(first_stats) if first_stats else None,
    }
