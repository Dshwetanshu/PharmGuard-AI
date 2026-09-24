"""Synthetic fixtures and fault injectors for validating the report checker.

Every record ID starts with "FX-" so fixture data can never be mistaken for
the sample data or a real dataset. The record contents are made up for the
purpose of exercising the checker; they are not clinical claims.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

from src.agents.generator import STATISTICAL_HEADING, Generator, hidden_notice
from src.agents.planner import Planner
from src.agents.retriever import RetrievalResult, select_pair_records
from src.config import Config
from src.data.normalizer import ResolvedDrug
from src.retrieval.faers_retriever import FaersRecord
from src.retrieval.interaction_retriever import InteractionRecord
from src.verification import Evidence, build_evidence
from src.verification.lexicon import event_supported, unsupported_mechanisms

CFG = Config()
PROVENANCE = "Data: synthetic FX- fixture records, not real clinical data."


def _ix(rid, src, a, b, event, sev, prr=None, mech=None):
    a, b = sorted((a, b))
    return InteractionRecord(rid, a, b, None, None, event, sev, prr, None, src, mech)


@dataclass
class Scenario:
    name: str
    drugs: List[str]
    unresolved: List[str]
    records: List[InteractionRecord]
    faers: List[FaersRecord]
    aliases: Dict[str, str]


SCENARIOS: List[Scenario] = [
    Scenario(
        "cardiac", ["verapamil", "digoxin", "simvastatin", "clarithromycin", "metformin"], ["notadrug_fx"],
        [
            # Canonical case: the source says P-glycoprotein, not CYP3A4.
            _ix("FX-0001", "DDInter", "verapamil", "digoxin", "digoxin toxicity", "Major",
                mech="Verapamil inhibits P-glycoprotein, raising digoxin levels"),
            _ix("FX-0002", "TWOSIDES", "clarithromycin", "simvastatin", "rhabdomyolysis", "Major", 19.7),
            _ix("FX-0003", "TWOSIDES", "clarithromycin", "digoxin", "digoxin toxicity", "Moderate", 6.1),
            _ix("FX-0004", "DDInter", "simvastatin", "verapamil", "myopathy", "Moderate",
                mech="Verapamil inhibits CYP3A4 metabolism of simvastatin"),
            _ix("FX-0005", "TWOSIDES", "metformin", "verapamil", "hypoglycemia", "Minor", 2.4),
        ],
        [FaersRecord("FX-F001", "metformin", "simvastatin", "nausea", 42, "Minor")],
        {"calan": "verapamil", "lanoxin": "digoxin", "zocor": "simvastatin"},
    ),
    Scenario(
        "anticoagulation", ["warfarin", "amiodarone", "ciprofloxacin", "sertraline"], [],
        [
            _ix("FX-0101", "TWOSIDES", "amiodarone", "warfarin", "prolonged prothrombin time", "Major", 11.2),
            _ix("FX-0102", "DDInter", "amiodarone", "warfarin", "increased anticoagulant effect", "Major",
                mech="Amiodarone inhibits CYP2C9 and CYP3A4 metabolism of warfarin"),
            _ix("FX-0103", "TWOSIDES", "amiodarone", "ciprofloxacin", "QT prolongation", "Major", 11.8),
            # False-positive guard: the event name contains the word "minor".
            _ix("FX-0104", "TWOSIDES", "sertraline", "warfarin", "minor bleeding", "Moderate", 4.2),
            _ix("FX-0105", "DDInter", "ciprofloxacin", "warfarin", "interaction", "Unknown",
                mech="Ciprofloxacin may increase INR"),
            # Four signals for one pair: three are shown, one is counted as "+1 more not shown".
            _ix("FX-0106", "TWOSIDES", "amiodarone", "warfarin", "INR increased", "Moderate", 9.4),
            _ix("FX-0107", "TWOSIDES", "amiodarone", "warfarin", "haematoma", "Moderate", 7.2),
            _ix("FX-0108", "TWOSIDES", "amiodarone", "warfarin", "epistaxis", "Minor", 3.1),
        ],
        [FaersRecord("FX-F101", "amiodarone", "sertraline", "dizziness", 7, "Minor")],
        {"coumadin": "warfarin", "cipro": "ciprofloxacin"},
    ),
    Scenario(
        "renal", ["lithium", "ibuprofen", "hydrochlorothiazide", "lisinopril"], ["zzz_fx_unknown"],
        [
            _ix("FX-0201", "DDInter", "ibuprofen", "lithium", "lithium toxicity", "Major",
                mech="NSAIDs reduce renal lithium clearance"),
            _ix("FX-0202", "TWOSIDES", "ibuprofen", "lisinopril", "acute kidney injury", "Moderate", 5.9),
            _ix("FX-0203", "TWOSIDES", "lisinopril", "lithium", "lithium toxicity", "Moderate", 4.4),
            _ix("FX-0204", "TWOSIDES", "hydrochlorothiazide", "lithium", "lithium toxicity", "Major", 16.8),
        ],
        [FaersRecord("FX-F201", "hydrochlorothiazide", "ibuprofen", "renal failure", 30, "Minor")],
        {"advil": "ibuprofen", "hctz": "hydrochlorothiazide"},
    ),
]


def build(s: Scenario, records=None) -> Tuple[object, RetrievalResult]:
    """Plan + RetrievalResult for a scenario (optionally with mutated records)."""
    records = s.records if records is None else records
    resolved = [ResolvedDrug(d, d, None, None, 100.0, True, "exact") for d in s.drugs]
    resolved += [ResolvedDrug(q, None, None, None, 0.0, False, "unresolved") for q in s.unresolved]
    plan = Planner().plan(resolved)
    result = RetrievalResult()
    by_pair: Dict[tuple, List[InteractionRecord]] = {}
    for r in records:
        by_pair.setdefault(tuple(sorted((r.drug_a, r.drug_b))), []).append(r)
    for pair, recs in by_pair.items():   # the same selection the Retriever applies
        result.interactions[pair], hidden = select_pair_records(recs)
        if hidden:
            result.hidden_signals[pair] = hidden
    result.no_data_pairs = [p for p in plan.pairs if p not in result.interactions]
    for f in s.faers:
        key = tuple(sorted((f.drug_a, f.drug_b)))
        if key in result.no_data_pairs:
            result.faers_signals.setdefault(key, []).append(f)
    return plan, result


def evidence_for(s: Scenario) -> Evidence:
    plan, result = build(s)
    return build_evidence(plan, result, s.aliases, CFG.disclaimer)


def render_prose(s: Scenario, plan, result) -> str:
    """LLM-style report: sentences instead of bullets, brand names, inline tier
    words, 1-decimal PRRs. Same section headings as the template (the system
    prompt requires them)."""
    gen = Generator(CFG, provenance=PROVENANCE)
    brand = {v: k for k, v in s.aliases.items()}
    lines = ["# PharmGuard Interaction Report", "", "## Summary",
             f"{plan.num_drugs} medications, {plan.num_pairs} pairs and {result.total_interactions} "
             "interaction records were reviewed.", ""]
    headings = {"Major": "Major Findings", "Moderate": "Moderate Findings",
                "Minor": "Minor Findings", "Unknown": "Severity Not Graded"}
    n = 0
    for tier, heading in headings.items():
        recs = [r for r in result.curated_records
                if (r.severity if r.severity in ("Major", "Moderate", "Minor") else "Unknown") == tier]
        if not recs:
            continue
        lines.append(f"## {heading}")
        for r in recs:
            cite = r.citation()
            a = f"{brand[r.drug_a].title()} ({r.drug_a})" if r.drug_a in brand else r.drug_a.capitalize()
            prr = f", PRR {r.prr:.1f}" if r.prr is not None else ""
            if n % 3 == 0 or tier == "Unknown":
                text = f"{a} with {r.drug_b}: {r.condition}{prr} {cite}."
                if r.mechanism:
                    text += f' Mechanism per source: "{r.mechanism}" {cite}.'
            elif n % 3 == 1:
                text = f"Combining {a} and {r.drug_b} is associated with {r.condition}{prr} {cite}."
                if r.mechanism:
                    text += f' The source attributes this to: "{r.mechanism}" {cite}.'
            else:
                text = (f"The {r.drug_a} + {r.drug_b} pairing carries a {tier.lower()}-severity signal "
                        f"for {r.condition}{prr} {cite}.")
                if r.mechanism:
                    text += f' Source mechanism: "{r.mechanism}" {cite}.'
            lines += [text, ""]
            n += 1
    if result.statistical_signals:
        lines.append(f"## {STATISTICAL_HEADING}")
        for pair, rs in result.interactions.items():
            for r in (r for r in rs if r.is_statistical):
                cite = r.citation()
                a = f"{brand[r.drug_a].title()} ({r.drug_a})" if r.drug_a in brand else r.drug_a.capitalize()
                prr = f"PRR {r.prr:.1f}" if r.prr is not None else "no PRR given"
                if n % 2 == 0:
                    text = f"{a} with {r.drug_b}: reporting signal for {r.condition}, {prr} {cite}."
                else:
                    text = (f"Co-reports of {a} and {r.drug_b} show a disproportionality signal for "
                            f"{r.condition} ({prr}) {cite}.")
                lines += [text, ""]
                n += 1
            if result.hidden_signals.get(pair):
                lines += [f"For {pair[0]} and {pair[1]}, {hidden_notice(result.hidden_signals[pair])}.", ""]
    lines.append("## Coverage Notes")
    if plan.unresolved:
        lines += ["### Unresolved Inputs",
                  "Not recognised, so excluded: " + ", ".join(u.query for u in plan.unresolved) + ".", ""]
    if result.no_data_pairs:
        lines.append("### No Curated Interaction Data")
        lines += [f"No interaction data available in the queried sources for {a} + {b}."
                  for a, b in result.no_data_pairs] + [""]
    lines += gen._faers_section(result)
    return gen._with_disclaimer(lines)


STYLES = ("template", "prose")


def render(s: Scenario, records=None, style: str = "template") -> str:
    plan, result = build(s, records)
    if style == "prose":
        return render_prose(s, plan, result)
    return Generator(CFG, provenance=PROVENANCE).generate_deterministic(plan, result)


def template(s: Scenario, records=None) -> str:
    return render(s, records, "template")


# ------------------------------------------------------------ fault injectors
Injection = Tuple[str, str]          # (site description, mutated report)
FINDING_HEADINGS = ("## Major Findings", "## Moderate Findings", "## Minor Findings", "## Severity Not Graded")
SIGNAL_HEADING = f"## {STATISTICAL_HEADING}"


def _finding_lines(report: str, headings=FINDING_HEADINGS + (SIGNAL_HEADING,)) -> List[Tuple[int, str]]:
    """Cited claim lines under the given headings (default: curated findings and signals)."""
    out, in_findings = [], False
    for i, line in enumerate(report.splitlines()):
        if line.startswith("## "):
            in_findings = line in headings
        elif in_findings and "[" in line:
            out.append((i, line))
    return out


def _with_line(report: str, i: int, new: str) -> str:
    lines = report.splitlines()
    lines[i] = new
    return "\n".join(lines)


def _before_citation(line: str, insert: str) -> str:
    """Insert text before the line's first citation (prose lines may have two)."""
    j = line.find(" [")
    return line[:j] + insert + line[j:]


def _shown(s: Scenario) -> List[int]:
    """Indices of s.records that the report shows (hidden signals can't be mutated visibly)."""
    _, result = build(s)
    ids = {r.record_id for rs in result.interactions.values() for r in rs}
    return [k for k, r in enumerate(s.records) if r.record_id in ids]


def _record_for(line: str, s: Scenario) -> InteractionRecord:
    rid = re.search(r":(FX-\d+)\]", line).group(1)
    return next(r for r in s.records if r.record_id == rid)


def mechanism_injection(s: Scenario, style: str = 'template') -> List[Injection]:
    out, base = [], render(s, style=style)
    for i, line in _finding_lines(base):
        rec = _record_for(line, s)
        support = f"{rec.condition} {rec.mechanism or ''}"
        term = next(t for t in ("CYP3A4", "P-glycoprotein", "CYP2D6", "OATP1B1")
                    if unsupported_mechanisms(t, support))
        out.append((rec.record_id, _with_line(base, i, _before_citation(line, f" via {term} inhibition"))))
    return out


def canonical_pgp_to_cyp3a4(s: Scenario, style: str = 'template') -> List[Injection]:
    base = render(s, style=style)
    if "P-glycoprotein" not in base:
        return []
    return [("FX-0001 P-glycoprotein -> CYP3A4", base.replace("inhibits P-glycoprotein", "inhibits CYP3A4"))]


def severity_flip(s: Scenario, style: str = 'template') -> List[Injection]:
    flip = {"Major": "Minor", "Moderate": "Major", "Minor": "Major", "Unknown": "Major"}
    out = []
    for k in _shown(s):
        r = s.records[k]
        if r.is_statistical:   # a signal's PRR tier is never shown, so flipping it changes nothing
            continue
        recs = copy.deepcopy(s.records)
        recs[k].severity = flip[r.severity]
        out.append((f"{r.record_id} {r.severity}->{flip[r.severity]}", render(s, recs, style)))
    return out


def citation_swap(s: Scenario, style: str = 'template') -> List[Injection]:
    out = []
    for k in _shown(s):
        r = s.records[k]
        # Same kind (curated vs signal): taking a TWOSIDES source would turn a curated record
        # into a PRR-less signal, which the selection could hide instead of mis-citing.
        other = next((o for o in s.records if {o.drug_a, o.drug_b} != {r.drug_a, r.drug_b}
                      and o.is_statistical == r.is_statistical), None)
        if other is None:
            continue
        recs = copy.deepcopy(s.records)
        recs[k].record_id, recs[k].source = other.record_id, other.source
        out.append((f"{r.record_id} cites {other.record_id}", render(s, recs, style)))
    return out


def phantom_citation(s: Scenario, style: str = 'template') -> List[Injection]:
    out = []
    for k in _shown(s):
        r = s.records[k]
        recs = copy.deepcopy(s.records)
        recs[k].record_id = f"FX-9{k:03d}"
        out.append((f"{r.record_id} -> FX-9{k:03d}", render(s, recs, style)))
    return out


def prr_distortion(s: Scenario, style: str = 'template') -> List[Injection]:
    out = []
    for k in _shown(s):   # PRR x1.5 keeps a shown signal among the top ones
        r = s.records[k]
        if r.prr is None:
            continue
        recs = copy.deepcopy(s.records)
        recs[k].prr = round(r.prr * 1.5, 2)
        out.append((f"{r.record_id} PRR {r.prr}->{recs[k].prr}", render(s, recs, style)))
    return out


def omitted_major(s: Scenario, style: str = 'template') -> List[Injection]:
    out = []
    for pair in sorted({tuple(sorted((r.drug_a, r.drug_b))) for r in s.records
                        if r.severity == "Major" and not r.is_statistical}):   # curated Major only
        recs = [r for r in s.records if tuple(sorted((r.drug_a, r.drug_b))) != pair]
        out.append((" + ".join(pair), render(s, recs, style)))
    return out


def absence_as_safety(s: Scenario, style: str = 'template') -> List[Injection]:
    base = render(s, style=style)
    plan, result = build(s)
    out = []
    lines = base.splitlines()
    for a, b in result.no_data_pairs:
        i = next(i for i, ln in enumerate(lines) if ln.rstrip(".").endswith(f"{a} + {b}"))
        out.append((f"{a} + {b}", _with_line(base, i, lines[i].rstrip(".") + " — no known interaction; safe to combine")))
    return out


def event_swap(s: Scenario, style: str = 'template') -> List[Injection]:
    events = [r.condition for r in s.records] + ["rhabdomyolysis", "serotonin syndrome", "bradycardia"]
    out = []
    for k in _shown(s):
        r = s.records[k]
        support = f"{r.condition} {r.mechanism or ''}"
        new = next(e for e in events if e != r.condition and not event_supported(e, support))
        recs = copy.deepcopy(s.records)
        recs[k].condition = new
        out.append((f"{r.record_id} {r.condition!r}->{new!r}", render(s, recs, style)))
    return out


POPULATION_PHRASES = ["elderly patients", "pregnancy", "patients with renal impairment",
                      "children", "patients with hepatic impairment"]


def population_injection(s: Scenario, style: str = 'template') -> List[Injection]:
    base, out = render(s, style=style), []
    for n, (i, line) in enumerate(_finding_lines(base)):
        phrase = POPULATION_PHRASES[n % len(POPULATION_PHRASES)]
        out.append((f"{_record_for(line, s).record_id} + {phrase}",
                    _with_line(base, i, _before_citation(line, f", particularly in {phrase}"))))
    return out


def uncited_claim(s: Scenario, style: str = 'template') -> List[Injection]:
    base, out = render(s, style=style), []
    for i, line in _finding_lines(base):
        out.append((_record_for(line, s).record_id, _with_line(base, i, re.sub(r" \[[^\]]+\]", "", line))))
    return out


def faers_as_curated(s: Scenario, style: str = 'template') -> List[Injection]:
    base = render(s, style=style)
    lines = base.splitlines()
    faers = [i for i, ln in enumerate(lines) if ln.startswith("- ") and "[FAERS:" in ln]
    head = next((i for i, ln in enumerate(lines) if ln in FINDING_HEADINGS), None)
    out = []
    for i in faers:
        moved = lines[:i] + lines[i + 1:]
        moved.insert(head + 1, lines[i])
        out.append((re.search(r"(FX-F\d+)", lines[i]).group(1), "\n".join(moved)))
    return out


SIGNAL_SEVERITY_PHRASES = ["; Major severity", ", a serious risk", ", clinically significant",
                           " (moderate interaction)", ", potentially life-threatening"]


def severity_on_signal(s: Scenario, style: str = 'template') -> List[Injection]:
    """A severity word attached to a statistical signal, or the signal moved under a severity heading."""
    base, out = render(s, style=style), []
    lines = base.splitlines()
    for n, (i, line) in enumerate(_finding_lines(base, (SIGNAL_HEADING,))):
        rid = _record_for(line, s).record_id
        phrase = SIGNAL_SEVERITY_PHRASES[n % len(SIGNAL_SEVERITY_PHRASES)]
        out.append((f"{rid} + {phrase.strip(' ,;()')!r}", _with_line(base, i, _before_citation(line, phrase))))
        head = next((j for j, ln in enumerate(lines) if ln in FINDING_HEADINGS), None)
        if head is not None and n == 0:
            moved = lines[:i] + lines[i + 1:]
            moved.insert(head + 1, line)
            out.append((f"{rid} moved under {lines[head][3:]}", "\n".join(moved)))
    return out


def missing_hidden_count(s: Scenario, style: str = 'template') -> List[Injection]:
    """The "+N more not shown" statement is dropped or states the wrong N."""
    base, out = render(s, style=style), []
    lines = base.splitlines()
    for i, line in enumerate(lines):
        m = re.search(r"\+(\d+) more not shown", line)
        if not m:
            continue
        out.append((f"drop '{m.group(0)}'", "\n".join(lines[:i] + lines[i + 1:])))
        wrong = line.replace(m.group(0), hidden_notice(int(m.group(1)) + 1))
        out.append((f"'{m.group(0)}' -> +{int(m.group(1)) + 1}", _with_line(base, i, wrong)))
    return out


FAULTS: Dict[str, Tuple[Callable[[Scenario], List[Injection]], str]] = {
    "mechanism_injection": (mechanism_injection, "UNSUPPORTED_MECHANISM"),
    "canonical_pgp_to_cyp3a4": (canonical_pgp_to_cyp3a4, "UNSUPPORTED_MECHANISM"),
    "severity_flip": (severity_flip, "SEVERITY_MISMATCH"),
    "citation_swap": (citation_swap, "MISATTRIBUTED_CITATION"),
    "phantom_citation": (phantom_citation, "PHANTOM_CITATION"),
    "prr_distortion": (prr_distortion, "NUMERIC_MISMATCH"),
    "omitted_major": (omitted_major, "OMITTED_MAJOR"),
    "absence_as_safety": (absence_as_safety, "CONFLATED_ABSENCE"),
    "event_swap": (event_swap, "EVENT_MISATTRIBUTION"),
    "population_injection": (population_injection, "UNSUPPORTED_POPULATION"),
    "uncited_claim": (uncited_claim, "UNCITED_CLAIM"),
    "faers_as_curated": (faers_as_curated, "FAERS_AS_CURATED"),
    "severity_on_signal": (severity_on_signal, "SEVERITY_ON_STATISTICAL_SIGNAL"),
    "missing_hidden_count": (missing_hidden_count, "MISSING_HIDDEN_COUNT"),
}


# ------------------------------------------------------------- blind spots
# Fabrications worded outside the lexicons. These are EXPECTED to be missed;
# they are reported to document that the checker is a lower bound, not tuned
# away. Each returns (site, mutated report) on the cardiac scenario.
def _cardiac_line(report: str, rid: str) -> Tuple[int, str]:
    return next((i, ln) for i, ln in enumerate(report.splitlines()) if f":{rid}]" in ln)


def _probe(rid: str, insert: str) -> Callable[[str], str]:
    def f(style: str) -> str:
        base = render(SCENARIOS[0], style=style)
        i, line = _cardiac_line(base, rid)
        return _with_line(base, i, _before_citation(line, insert))
    return f


BLIND_SPOTS: Dict[str, Tuple[Callable[[str], str], str]] = {
    "mechanism outside lexicon ('hepatic enzyme blockade')":
        (_probe("FX-0002", " through hepatic enzyme blockade"), "UNSUPPORTED_MECHANISM"),
    "population outside lexicon ('patients over 80')":
        (_probe("FX-0002", ", especially in patients over 80"), "UNSUPPORTED_POPULATION"),
    "unquantified magnitude ('risk roughly triples')":
        (_probe("FX-0002", "; the risk roughly triples"), "NUMERIC_MISMATCH"),
    "event outside lexicon ('muscle breakdown')":
        (lambda style: render(SCENARIOS[0], [
            InteractionRecord(r.record_id, r.drug_a, r.drug_b, None, None,
                              "muscle breakdown" if r.record_id == "FX-0003" else r.condition,
                              r.severity, r.prr, None, r.source, r.mechanism)
            for r in SCENARIOS[0].records], style), "EVENT_MISATTRIBUTION"),
    "reversed direction ('lowering digoxin levels')":
        (lambda style: render(SCENARIOS[0], style=style).replace("raising digoxin levels", "lowering digoxin levels"),
         "UNSUPPORTED_MECHANISM"),
}
