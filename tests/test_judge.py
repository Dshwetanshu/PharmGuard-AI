"""LLM judge (src/evaluation/judge.py), with fake LLMs only."""
from __future__ import annotations

import csv
import hashlib
import json

import pytest

from src.evaluation import judge as J
from src.graph import PharmGuardGraph, Settings
from src.graph.simulated import inject_cyp3a4
from src.verification import Evidence, validate_report


class RuleJudgeLLM:
    """A fake judge: 'contradicted' if a Major/Moderate/Minor word in the claim isn't the cited severity,
    'unsupported' if the claim says CYP3A4 and no record does, else 'supported'."""
    def __init__(self, reply=None):
        self.reply, self.calls, self.last_usage = reply, [], {"input_tokens": 100, "output_tokens": 20}

    def complete(self, system, messages, **kw):
        self.calls.append((system, messages))
        if self.reply is not None:
            return self.reply
        msg = messages[0]["content"]
        claim = msg.split("CLAIM:\n", 1)[1].split("\n\nCITED RECORDS", 1)[0]
        recs = json.loads(msg.split("CITED RECORDS (JSON):\n", 1)[1])
        sev = {r.get("severity") for r in recs}
        for word in ("Major", "Moderate", "Minor"):
            if word in claim and sev <= {"Major", "Moderate", "Minor"} and word not in sev:
                return json.dumps({"verdict": "contradicted", "rationale": f"records say {sev}"})
        if "CYP3A4" in claim and not any("CYP3A4" in (r.get("mechanism") or "") for r in recs):
            return '```json\n{"verdict": "unsupported", "rationale": "no CYP3A4 in the records"}\n```'
        return '{"verdict": "supported", "rationale": "matches the record"}'


@pytest.fixture(scope="module")
def state(test_data_dir, sample_ingest_report):
    g = PharmGuardGraph(Settings(data_dir=test_data_dir, mode="deterministic"))
    return g.run(["lisinopril", "spironolactone", "aspirin"])


def test_prompt_is_versioned_and_hashed():
    info = J.prompt_info()
    assert info["file"] == "src/evaluation/prompts/judge_v1.txt"
    assert info["sha256"] == hashlib.sha256(J.DEFAULT_PROMPT.read_bytes()).hexdigest()
    assert '"supported" | "unsupported" | "contradicted"' in J.DEFAULT_PROMPT.read_text()


def test_claims_are_the_checkers_cited_clinical_claims(state):
    ev = Evidence.from_dict(state["evidence"])
    claims = J.extract_claims(state["report"], ev, "GER-X")
    stats = validate_report(state["report"], ev).stats
    assert len(claims) == stats["clinical_claims"] and claims
    assert all(c.records and not c.missing_citations for c in claims)
    assert all(set(c.records[0]) >= {"citation", "source", "drugs", "event"} for c in claims)
    assert len({c.claim_id for c in claims}) == len(claims)


def test_judge_sees_only_the_claim_and_its_records(state):
    ev = Evidence.from_dict(state["evidence"])
    claim = J.extract_claims(state["report"], ev, "r")[0]
    llm = RuleJudgeLLM()
    J.ClaimJudge(llm).judge(claim)
    system, messages = llm.calls[0]
    assert system == J.DEFAULT_PROMPT.read_text() and len(messages) == 1
    body = messages[0]["content"]
    assert claim.text in body and "Disclaimer" not in body and "How your entries were read" not in body
    other = [c for c in J.extract_claims(state["report"], ev, "r") if c.citations != claim.citations]
    assert all(c not in body for oc in other for c in oc.citations)


def test_template_claims_are_supported_and_a_fabrication_is_not(state):
    ev = Evidence.from_dict(state["evidence"])
    judge = J.ClaimJudge(RuleJudgeLLM())
    clean = [judge.judge(c) for c in J.extract_claims(state["report"], ev, "clean")]
    assert J.faithfulness(clean)["faithfulness"] == 1.0
    bad_report = inject_cyp3a4(state["report"])
    bad = [judge.judge(c) for c in J.extract_claims(bad_report, ev, "bad")]
    f = J.faithfulness(bad)
    assert f["unsupported"] == 1 and f["judged"] == len(bad) and f["faithfulness"] == round((len(bad) - 1) / len(bad), 4)
    assert judge.usage["input_tokens"] == 100 * judge.calls


def test_severity_flip_is_contradicted(state):
    ev = Evidence.from_dict(state["evidence"])
    flipped = state["report"].replace("curated severity: Major", "curated severity: Minor", 1)
    js = [J.ClaimJudge(RuleJudgeLLM()).judge(c) for c in J.extract_claims(flipped, ev, "f")]
    assert J.faithfulness(js)["contradicted"] == 1


def test_phantom_citation_is_unsupported_without_a_call(state):
    ev = Evidence.from_dict(state["evidence"])
    claim = J.Claim("r:L1", "r", "lisinopril + spironolactone — hyperkalemia", ["[DDInter:DDI-nope]"], [],
                    ["[DDInter:DDI-nope]"])
    llm = RuleJudgeLLM()
    j = J.ClaimJudge(llm).judge(claim)
    assert (j.verdict, j.called_judge, llm.calls) == ("unsupported", False, [])
    mixed = J.Claim("r:L2", "r", "x", ["[A:1]", "[B:2]"], [{"citation": "[A:1]"}], ["[B:2]"])
    assert J.ClaimJudge(RuleJudgeLLM()).judge(mixed).verdict == "unsupported"


@pytest.mark.parametrize("reply,expected", [
    ('{"verdict": "Supported", "rationale": "ok"}', "supported"),
    ('Sure! {"verdict": "contradicted", "rationale": "x"} Hope that helps.', "contradicted"),
    ('{"verdict": "maybe"}', "invalid"),
    ("not json", "invalid"),
])
def test_judge_output_parsing(reply, expected):
    claim = J.Claim("r:L1", "r", "x", ["[A:1]"], [{"citation": "[A:1]"}])
    j = J.ClaimJudge(RuleJudgeLLM(reply)).judge(claim)
    assert j.verdict == expected
    if expected == "invalid":
        assert J.faithfulness([j]) == {**J.faithfulness([j]), "judged": 0, "invalid_judge_output": 1,
                                       "faithfulness": None}


def test_same_provider_judge_needs_the_flag_and_is_disclosed():
    with pytest.raises(ValueError, match="different provider"):
        J.check_providers("gemini", "gemini", allow_same_provider=False)
    d = J.check_providers("gemini", "gemini", allow_same_provider=True)
    assert d["same_provider"] is True and d["same_provider_allowed"] is True
    assert J.check_providers("anthropic", "gemini", False)["same_provider"] is False


def test_cohen_kappa_by_hand():
    # po = 3/4; pe = (2*1 + 1*2 + 1*1) / 16 = 5/16; kappa = (0.75 - 0.3125) / 0.6875
    a = ["supported", "supported", "unsupported", "contradicted"]
    b = ["supported", "unsupported", "unsupported", "contradicted"]
    assert J.cohen_kappa(a, b) == pytest.approx(0.4375 / 0.6875)
    assert J.cohen_kappa(a, a) == pytest.approx(1.0) and J.cohen_kappa([], []) is None


def test_blind_export_hides_verdicts_and_the_audit_scores_agreement(state, tmp_path):
    ev = Evidence.from_dict(state["evidence"])
    claims = []
    for i in range(4):
        claims += J.extract_claims(state["report"], ev, f"R{i}")
    judge = J.ClaimJudge(RuleJudgeLLM())
    js = [judge.judge(c) for c in claims]
    js[0].verdict = "unsupported"
    n = J.export_blind(claims, js, tmp_path / "audit.csv", tmp_path / "key.json", fraction=0.2, seed=1)
    assert n == round(0.2 * len(js))
    text = (tmp_path / "audit.csv").read_text()
    rows = list(csv.DictReader(text.splitlines()))
    assert list(rows[0]) == J.AUDIT_COLUMNS and all(r["human_verdict"] == "" for r in rows)
    assert "supported" not in {r["claim"] for r in rows} and "judge_verdict" not in text
    key = json.loads((tmp_path / "key.json").read_text())["rows"]
    assert set(key) == {r["audit_id"] for r in rows}
    # A human who agrees on every row but one.
    for i, r in enumerate(rows):
        v = key[r["audit_id"]]["judge_verdict"]
        r["human_verdict"] = v if i else ("contradicted" if v != "contradicted" else "supported")
    rows[-1]["human_verdict"] = ""                     # one left blank
    with (tmp_path / "audit.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=J.AUDIT_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    s = J.score_audit(tmp_path / "audit.csv", tmp_path / "key.json")
    assert (s["rows_scored"], s["rows_blank"]) == (n - 1, 1)
    assert s["percent_agreement"] == round((n - 2) / (n - 1), 4)
