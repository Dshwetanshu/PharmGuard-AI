"""Seeded orchestration bugs, used to show the trajectory invariants catch them.

Each bug is a context manager that swaps one of the graph's decision points
(src/graph/builder.py: attempts_left, faers_needed, complete_plan,
fallback_report, plus the validate_report and is_transient_llm_error it calls)
for a buggy version, then restores it. Used only by tests and by
scripts/eval_trajectory.py --seeded-bugs.
"""
from __future__ import annotations

import contextlib
from typing import Callable, Dict, Iterator

import src.graph.builder as builder
from src.verification import ValidationResult


@contextlib.contextmanager
def _swap(name: str, make: Callable[[Callable], Callable]) -> Iterator[None]:
    original = getattr(builder, name)
    setattr(builder, name, make(original))
    try:
        yield
    finally:
        setattr(builder, name, original)


def _always_pass(real):
    def validate(report, evidence, final=True):
        v = real(report, evidence, final=final)
        return ValidationResult(passed=True, findings=[], stats=v.stats)
    return validate


def _off_by_one(real):
    return lambda state, settings: state["llm_attempts"] <= settings.max_llm_attempts


def _returns_rejected_draft(real):
    return lambda c, p, result, state: state.get("draft") or real(c, p, result, state)


def _faers_always(real):
    return lambda state, settings: True


def _drops_a_pair(real):
    def complete(p):
        p, patched = real(p)
        if p.pairs:
            p.pairs = p.pairs[:-1]
        return p, patched
    return complete


def _retries_everything(real):
    return lambda exc: True


SEEDED_BUGS: Dict[str, Callable[[], contextlib.AbstractContextManager]] = {
    "validate_always_passes": lambda: _swap("validate_report", _always_pass),
    "retry_limit_off_by_one": lambda: _swap("attempts_left", _off_by_one),
    "fallback_returns_rejected_draft": lambda: _swap("fallback_report", _returns_rejected_draft),
    "faers_always_consulted": lambda: _swap("faers_needed", _faers_always),
    "plan_drops_a_pair": lambda: _swap("complete_plan", _drops_a_pair),
    "non_transient_errors_retried": lambda: _swap("is_transient_llm_error", _retries_everything),
}
