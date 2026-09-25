"""Trajectory evaluation: step scoring, fault suite, invariants, and seeded bugs they must catch."""
from __future__ import annotations

from dataclasses import replace

import pytest

from src.data.storage import read_table
from src.evaluation import trajectory as T
from src.evaluation.seeded_bugs import SEEDED_BUGS
from src.evaluation.test_cases import TEST_CASES
from src.graph import Settings, build_components

SUBSET = [c for c in TEST_CASES if c.case_id in ("GER-01", "TXT-04", "EDG-01", "EDG-06", "END-01")]


@pytest.fixture(scope="module")
def harness(test_data_dir, sample_ingest_report):
    s = Settings(data_dir=test_data_dir, mode="deterministic")
    c = build_components(s)
    return T.Harness.build(s, c, read_table(s.to_config().paths.processed_dir / "drug_vocabulary.parquet"))


def test_step_scoring_all_cases_complete(harness):
    out = T.run_step_scoring(harness)
    for config in ("deterministic", "llm_mode_without_key"):
        summary = out["step_scoring"][config]["summary"]
        assert summary["overall"]["completion"] == 1.0, summary["failing"]
        assert summary["suspected_label_misses"] == {"EDG-03": [["atorvastatin", "lisinopril"]]}
    assert out["step_scoring"]["llm_mode_with_key"] is None
    assert all(all(ok for ok, _ in inv.values()) for inv in out["invariant_runs"])


def test_step_scoring_catches_a_wrong_normalization(harness):
    case = next(c for c in TEST_CASES if c.case_id == "MH-02")
    wrong = replace(case, expected_resolved={"lithium": "lithium citrate"})
    state = harness.graph(mode="deterministic").run(case.input_drugs)
    row = T.score_steps(wrong, state, mode="deterministic", llm_available=False, alias_map=harness.alias_map,
                        disclaimer=harness.components.generator.cfg.disclaimer,
                        provenance=harness.components.generator.provenance)
    assert not row["normalize"] and not row["completed"] and "lithium citrate" in row["reasons"]["normalize"]


@pytest.mark.parametrize("outcomes,expected", [
    (("pass",), (["generate_llm", "validate", "finalize"], "llm")),
    (("err_t", "pass"), (["generate_llm", "generate_llm", "validate", "finalize"], "llm_retry")),
    (("err_t", "err_t"), (["generate_llm", "generate_llm", "template", "finalize"], "deterministic_fallback")),
    (("err_nt",), (["generate_llm", "template", "finalize"], "deterministic_fallback")),
    (("fail", "pass"), (["generate_llm", "validate", "generate_llm", "validate", "finalize"], "llm_retry")),
    (("fail", "fail"), (["generate_llm", "validate", "generate_llm", "validate", "template", "finalize"],
                        "deterministic_fallback")),
])
def test_expected_path_restates_the_spec(outcomes, expected):
    path, source = T.expected_path(outcomes, eligible=True, llm_mode=True, faers_visit=False, max_attempts=2)
    assert (path[3:], source) == expected and path[:3] == ["normalize", "plan", "retrieve"]


def test_fault_suite_subset_meets_every_invariant(harness):
    runs = T.run_fault_suite(harness, SUBSET)["runs"]
    s = T.summarize_faults(runs)
    assert set(s["invariant_pass_rate"].values()) == {1.0}
    assert (s["path_match_rate"], s["source_match_rate"], s["recovery_rate"]) == (1.0, 1.0, 1.0), s["mismatches"]
    assert {r["scenario"] for r in runs} >= {sc.name for sc in T.SCENARIOS}


# Which invariant must catch which seeded bug (at least these; others may also break).
CATCHES = {
    "validate_always_passes": {"final_report_valid", "no_unvalidated_llm_text"},
    "retry_limit_off_by_one": {"llm_attempts_within_budget"},
    "fallback_returns_rejected_draft": {"exhausted_fallback_matches_deterministic", "no_unvalidated_llm_text"},
    "faers_always_consulted": {"faers_only_when_needed"},
    "plan_drops_a_pair": {"plan_complete"},
    "non_transient_errors_retried": {"non_transient_never_retried"},
}


@pytest.mark.parametrize("bug", sorted(SEEDED_BUGS))
def test_each_seeded_bug_breaks_an_invariant(harness, bug):
    with SEEDED_BUGS[bug]():
        runs = T.run_fault_suite(harness, SUBSET)["runs"]
    rates = T.summarize_faults(runs)["invariant_pass_rate"]
    broken = {k for k, v in rates.items() if v < 1.0}
    assert CATCHES[bug] <= broken, (bug, rates)
    # ...and the bug is gone once the context manager exits
    assert set(T.summarize_faults(T.run_fault_suite(harness, SUBSET[:1])["runs"])["invariant_pass_rate"].values()) == {1.0}


def test_gate_exit_code(tmp_path, monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("eval_trajectory", root / "scripts" / "eval_trajectory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(sys, "argv", ["eval_trajectory.py", "--output-dir", str(tmp_path), "--min-invariant-pass", "1.0"])
    assert mod.main() == 0 and (tmp_path / "trajectory.md").exists()
    monkeypatch.setattr(sys, "argv", ["eval_trajectory.py", "--output-dir", str(tmp_path), "--min-invariant-pass", "1.01"])
    assert mod.main() == 1
