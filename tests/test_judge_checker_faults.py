"""scripts/judge_checker_faults.py: which claims count as known-bad, and the tallies (fake judge, offline)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import judge_checker_faults as jcf  # noqa: E402
from src.evaluation.judge import ClaimJudge  # noqa: E402


class FakeLLM:
    """'contradicted' for any claim with an injected term, else 'supported'."""
    def complete(self, system, messages, **kw):
        text = messages[0]["content"].split("CITED RECORDS")[0]
        bad = any(t in text for t in (" inhibition", "particularly in", "hepatic enzyme blockade"))
        return json.dumps({"verdict": "contradicted" if bad else "supported", "rationale": "fake"})


def test_known_bad_claims_are_the_injected_lines_not_reworded_neighbours():
    items, not_judgeable = jcf.fault_claims()
    faults = [(n, c) for g, n, _, _, c in items if g == "fault"]
    assert all(" inhibition" in c.text for n, c in faults if n == "mechanism_injection")
    assert all("particularly in" in c.text for n, c in faults if n == "population_injection")
    # a prose severity flip only moves the line under another heading: its sentence is true, so it isn't counted
    assert all(any(g in c.text for g in ("Major", "Moderate", "Minor")) for n, c in faults if n == "severity_flip")
    assert {"omitted_major", "uncited_claim", "missing_hidden_count"} <= set(not_judgeable)
    assert sum(g == "blind_spot" for g, *_ in items) == 2 * len(jcf.BLIND_SPOTS)
    assert all(c.records for g, *_, c in items if g == "control")


def test_tallies_separate_llm_calls_from_phantom_citations():
    items, _ = jcf.fault_claims()
    judge = ClaimJudge(FakeLLM())
    s = jcf.summarize(jcf.run(judge, items))
    phantom = s["fault"]["by_name"]["phantom_citation"]
    assert phantom["claims"] == 0 and s["fault"]["rated_without_call"] > 0   # phantom-only claims: no call
    assert judge.calls == sum(t["claims"] for g in s.values() for t in [g["llm_judged"]])
    assert s["control"]["llm_judged"]["supported"] == s["control"]["llm_judged"]["claims"]
    assert s["fault"]["by_name"]["mechanism_injection"]["contradicted"] == s["fault"]["by_name"]["mechanism_injection"]["claims"]
    md = jcf.to_markdown({"command": "x", "run_on": "d", "judge": "fake", "judge_prompt": {"file": "f", "sha256": "s"},
                          "calls": judge.calls, "usage": {}, "not_judgeable": {}, "summary": s, "rows": jcf.run(judge, items)})
    assert "Known-bad claims rated unsupported or contradicted" in md
