"""LLM judge for claim faithfulness, plus a blind human audit of its verdicts.

Each clinical claim in a report (as src/verification finds them) is judged on its
own: the judge sees only the claim text and the records the claim cites, and
returns {"verdict": "supported" | "unsupported" | "contradicted", "rationale"}.

- The judge prompt is a versioned file (prompts/judge_v1.txt); its sha256 goes
  into every result.
- The judge must be a different provider from the generator unless
  allow_same_provider is set, and results record which was the case.
- Faithfulness = supported / judged claims, per generation provider. A claim
  citing a record that isn't in the evidence is "unsupported" without a call;
  claims with no citation aren't judged (the checker counts them as UNCITED_CLAIM).
- export_blind() writes a seeded random share of judged claims to a CSV with the
  verdicts hidden (kept in a separate key file); score_audit() reads the filled
  CSV back and reports percent agreement and Cohen's kappa.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.verification.checker import _drug_names, _is_clinical
from src.verification.evidence import Evidence, NormalizedRecord
from src.verification.parser import parse_report

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
DEFAULT_PROMPT = PROMPT_DIR / "judge_v1.txt"
VERDICTS = ("supported", "unsupported", "contradicted")


@dataclass
class Claim:
    claim_id: str
    report_id: str
    text: str
    citations: List[str]
    records: List[Dict[str, Any]]       # the cited records, as the judge sees them
    missing_citations: List[str] = field(default_factory=list)


@dataclass
class Judgement:
    claim_id: str
    verdict: str                        # one of VERDICTS, or "invalid" (unparseable judge output)
    rationale: str
    called_judge: bool


def prompt_info(path: Path = DEFAULT_PROMPT) -> Dict[str, str]:
    text = Path(path).read_text()
    return {"file": f"src/evaluation/prompts/{Path(path).name}", "sha256": hashlib.sha256(text.encode()).hexdigest()}


def record_view(r: NormalizedRecord) -> Dict[str, Any]:
    """What the judge is shown of a record: its fields, no report text."""
    view = {"citation": r.citation, "source": r.source, "kind": r.kind, "drugs": r.drugs, "event": r.event}
    for k, v in (("severity", r.severity), ("prr", r.prr), ("mechanism", r.mechanism)):
        if v not in (None, ""):
            view[k] = v
    for k in ("reports", "report_count"):
        if r.detail.get(k) is not None:
            view[k] = r.detail[k]
    return view


def extract_claims(report: str, evidence: Evidence, report_id: str) -> List[Claim]:
    """The cited clinical claims of a report, each with the records it cites."""
    parsed = parse_report(report, evidence.aliases)
    events = sorted({r.event for r in evidence.records.values() if r.event})
    names = _drug_names(evidence)
    out = []
    for u in parsed.units:
        if u.section == "disclaimer" or not u.citations or not _is_clinical(u, events, names):
            continue
        recs, missing = [], []
        for c in u.citations:
            rec = evidence.get(c.source, c.record_id)
            if rec is None:
                missing.append(f"[{c.source}:{c.record_id}]")
            else:
                recs.append(record_view(rec))
        out.append(Claim(f"{report_id}:L{u.line}", report_id, u.text,
                         [f"[{c.source}:{c.record_id}]" for c in u.citations], recs, missing))
    return out


def check_providers(generator_provider: str, judge_provider: str, allow_same_provider: bool) -> Dict[str, Any]:
    same = generator_provider == judge_provider
    if same and not allow_same_provider:
        raise ValueError(f"the judge ({judge_provider}) must be a different provider from the generator "
                         f"({generator_provider}); pass allow_same_provider to override, and disclose it")
    return {"generator_provider": generator_provider, "judge_provider": judge_provider,
            "same_provider": same, "same_provider_allowed": allow_same_provider}


_JSON = re.compile(r"\{.*\}", re.S)


def parse_verdict(text: str) -> Optional[Dict[str, str]]:
    m = _JSON.search(text or "")
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    v = str(obj.get("verdict", "")).strip().lower()
    if v not in VERDICTS:
        return None
    return {"verdict": v, "rationale": str(obj.get("rationale", "")).strip()}


class ClaimJudge:
    """Judges claims one at a time with an LLM client (.complete(system, messages))."""

    def __init__(self, llm, prompt_path: Path = DEFAULT_PROMPT):
        self.llm = llm
        self.system = Path(prompt_path).read_text()
        self.calls = 0
        self.usage = Counter()

    @staticmethod
    def user_message(claim: Claim) -> str:
        return ("CLAIM:\n" + claim.text + "\n\nCITED RECORDS (JSON):\n"
                + json.dumps(claim.records, indent=1, sort_keys=True, default=str))

    def judge(self, claim: Claim) -> Judgement:
        if claim.missing_citations and not claim.records:
            return Judgement(claim.claim_id, "unsupported",
                             "cites no record in the evidence: " + ", ".join(claim.missing_citations), False)
        self.calls += 1
        text = self.llm.complete(system=self.system, messages=[{"role": "user", "content": self.user_message(claim)}])
        usage = getattr(self.llm, "last_usage", None) or {}
        self.usage.update({k: int(v) for k, v in usage.items()})
        v = parse_verdict(text)
        if v is None:
            return Judgement(claim.claim_id, "invalid", (text or "")[:200], True)
        if claim.missing_citations and v["verdict"] == "supported":
            # A claim that also cites a phantom record can't be fully supported.
            return Judgement(claim.claim_id, "unsupported",
                             v["rationale"] + " (also cites " + ", ".join(claim.missing_citations)
                             + ", which is not in the evidence)", True)
        return Judgement(claim.claim_id, v["verdict"], v["rationale"], True)


def faithfulness(judgements: Sequence[Judgement]) -> Dict[str, Any]:
    counts = Counter(j.verdict for j in judgements)
    judged = sum(counts[v] for v in VERDICTS)
    r = lambda n: round(n / judged, 4) if judged else None
    return {"claims": len(judgements), "judged": judged, "invalid_judge_output": counts["invalid"],
            "supported": counts["supported"], "unsupported": counts["unsupported"],
            "contradicted": counts["contradicted"],
            "faithfulness": r(counts["supported"]), "unsupported_rate": r(counts["unsupported"]),
            "contradicted_rate": r(counts["contradicted"])}


# ---------------------------------------------------------------- blind audit

AUDIT_COLUMNS = ["audit_id", "claim", "cited_records", "human_verdict", "human_notes"]


def export_blind(claims: Sequence[Claim], judgements: Sequence[Judgement], csv_path: Path, key_path: Path,
                 fraction: float = 0.2, seed: int = 20260928) -> int:
    """Write a seeded random `fraction` of judged claims for a human, verdicts hidden. Returns the row count."""
    by_id = {c.claim_id: c for c in claims}
    judged = [j for j in judgements if j.verdict in VERDICTS]
    k = max(1, round(fraction * len(judged))) if judged else 0
    sample = random.Random(seed).sample(judged, k)
    csv_path, key_path = Path(csv_path), Path(key_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    key: Dict[str, Dict[str, str]] = {}
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=AUDIT_COLUMNS)
        w.writeheader()
        for i, j in enumerate(sample, start=1):
            aid = f"A{i:03d}"
            c = by_id[j.claim_id]
            w.writerow({"audit_id": aid, "claim": c.text,
                        "cited_records": json.dumps(c.records, sort_keys=True, default=str),
                        "human_verdict": "", "human_notes": ""})
            key[aid] = {"claim_id": j.claim_id, "judge_verdict": j.verdict}
    key_path.write_text(json.dumps({"fraction": fraction, "seed": seed, "rows": key}, indent=2) + "\n")
    return len(sample)


def cohen_kappa(a: Sequence[str], b: Sequence[str], labels: Sequence[str] = VERDICTS) -> Optional[float]:
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[l] * cb[l] for l in labels) / (n * n)
    return None if pe == 1 else (po - pe) / (1 - pe)


def score_audit(csv_path: Path, key_path: Path) -> Dict[str, Any]:
    key = json.loads(Path(key_path).read_text())["rows"]
    human, judge, blank, bad = [], [], 0, []
    with Path(csv_path).open(newline="") as f:
        for row in csv.DictReader(f):
            v = (row.get("human_verdict") or "").strip().lower()
            if not v:
                blank += 1
                continue
            if v not in VERDICTS or row["audit_id"] not in key:
                bad.append(row["audit_id"])
                continue
            human.append(v)
            judge.append(key[row["audit_id"]]["judge_verdict"])
    n = len(human)
    k = cohen_kappa(human, judge)
    return {"rows_scored": n, "rows_blank": blank, "rows_invalid": bad,
            "percent_agreement": round(sum(h == j for h, j in zip(human, judge)) / n, 4) if n else None,
            "cohen_kappa": None if k is None else round(k, 4),
            "confusion_human_by_judge": {h: {j: sum(1 for x, y in zip(human, judge) if (x, y) == (h, j))
                                             for j in VERDICTS} for h in VERDICTS}}


def judgements_to_dicts(js: Iterable[Judgement]) -> List[Dict[str, Any]]:
    return [asdict(j) for j in js]
