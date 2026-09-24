"""Semantic report checker: does each claim say only what its cited record says?

``validate_report(report, evidence)`` is the single implementation used by the
runtime guardrail (src/pipeline.py), the evaluation (scripts/run_eval.py) and
the checker's own validation (scripts/validate_checker.py).

Lower bound: mechanism, population and event checks use hand-written lexicons
(src/verification/lexicon.py). A fabrication phrased outside those lexicons
passes. The checks catch contradictions with the cited record, not every
unsupported statement; an LLM judge is planned as a later layer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Set

from src.verification import lexicon
from src.verification.evidence import Evidence, NormalizedRecord, citation_key, records_for
from src.verification.parser import (
    DECLARATION_SECTIONS, FINDING_SECTIONS, STATISTICAL_SECTION, ParsedReport, Unit, parse_report,
)

PAIR_KINDS = ("interaction", "signal")   # records that belong to a drug pair

# Claim-level codes that mean "the claim says something its evidence doesn't".
FABRICATION_CODES = {
    "PHANTOM_CITATION", "MISATTRIBUTED_CITATION", "SEVERITY_MISMATCH", "NUMERIC_MISMATCH",
    "EVENT_MISATTRIBUTION", "UNSUPPORTED_MECHANISM", "UNSUPPORTED_POPULATION", "FAERS_AS_CURATED",
    "SEVERITY_ON_STATISTICAL_SIGNAL",
}
REPORT_CODES = {
    "OMITTED_INTERACTION", "OMITTED_MAJOR", "MISSING_NO_DATA_DECLARATION", "CONFLATED_ABSENCE",
    "MISSING_UNRESOLVED_DECLARATION", "MISSING_DISCLAIMER", "MISSING_HIDDEN_COUNT",
}
ALL_CODES = FABRICATION_CODES | REPORT_CODES | {"UNCITED_CLAIM"}


@dataclass
class Finding:
    code: str
    line: Optional[int]
    message: str


@dataclass
class ValidationResult:
    passed: bool
    findings: List[Finding]
    stats: Dict[str, Optional[float]]

    def to_dict(self) -> dict:
        return {"passed": self.passed, "findings": [asdict(f) for f in self.findings], "stats": self.stats}

    def codes(self) -> Set[str]:
        return {f.code for f in self.findings}


def _rate(num: int, den: int) -> Optional[float]:
    return round(num / den, 4) if den else None


def _mask(text: str, phrases: List[str]) -> str:
    t = lexicon.norm(text)
    for p in sorted({lexicon.norm(x) for x in phrases if x}, key=len, reverse=True):
        t = lexicon.phrase_re(p).sub(" ", t)
    return t


def _drug_names(ev: Evidence) -> List[str]:
    """Every alias of the analysed drugs, to mask before population/mechanism word checks
    (a drug named "calcium lactate" is not a claim about lactation)."""
    return list(ev.aliases)


def _is_clinical(u: Unit, evidence_events: List[str], drug_names: List[str] = ()) -> bool:
    if u.section in ("title", "disclaimer") or not u.context_drugs:
        return False
    t = lexicon.norm(u.text)
    t_nodrugs = _mask(t, drug_names)
    specific = bool(lexicon.find_events(t, evidence_events) or lexicon.mechanism_terms(t_nodrugs)
                    or lexicon.populations(t_nodrugs) or lexicon.PRR_RE.search(t) or lexicon.claimed_tiers(t))
    if u.section in DECLARATION_SECTIONS:
        return specific
    if u.section in FINDING_SECTIONS or u.section in ("faers", STATISTICAL_SECTION):
        # A bare "+N more not shown" line is a count, not a claim.
        return specific or not lexicon.HIDDEN_COUNT_RE.search(t)
    return specific or bool(lexicon.CLINICAL_CUE.search(t))


def _check_claim(u: Unit, ev: Evidence, evidence_events: List[str], out: List[Finding]) -> None:
    cited: List[NormalizedRecord] = []
    for c in u.citations:
        rec = ev.get(c.source, c.record_id)
        if rec is None:
            out.append(Finding("PHANTOM_CITATION", u.line, f"[{c.raw}] is not in the retrieved evidence"))
            continue
        cited.append(rec)
        mentioned, rec_drugs = set(u.context_drugs), set(rec.drugs)
        # Consistent if one set contains the other: a sentence may name only one
        # drug of the pair (a quoted mechanism) or more drugs than the record.
        if mentioned and not (mentioned <= rec_drugs or rec_drugs <= mentioned):
            out.append(Finding("MISATTRIBUTED_CITATION", u.line,
                               f"{rec.citation} is for {' + '.join(rec.drugs)}, but the claim is about "
                               f"{' + '.join(u.context_drugs)}"))
        if rec.kind == "faers" and u.section != "faers":
            out.append(Finding("FAERS_AS_CURATED", u.line,
                               f"{rec.citation} is an unvalidated FAERS report cited outside the FAERS section"))

    support_recs = cited or records_for(ev, u.context_drugs)
    support = " ".join(r.support_text() for r in support_recs)
    text = lexicon.norm(u.text)

    # Severity: from the section heading, plus explicit tier words once the cited
    # records' own event/mechanism text is masked (so "minor bleeding" isn't a tier).
    heading_tier = FINDING_SECTIONS.get(u.section)
    masked = _mask(text, [r.event for r in cited] + [r.mechanism or "" for r in cited])
    text_tiers = lexicon.claimed_tiers(masked)
    claimed = text_tiers | ({heading_tier} if heading_tier else set())
    for rec in cited:
        if rec.kind != "signal":
            continue
        if u.section in FINDING_SECTIONS:
            out.append(Finding("SEVERITY_ON_STATISTICAL_SIGNAL", u.line,
                               f"statistical signal {rec.citation} is listed under a severity heading"))
        words = lexicon.severity_words(masked)
        if words:
            out.append(Finding("SEVERITY_ON_STATISTICAL_SIGNAL", u.line,
                               f"statistical signal {rec.citation} is described with severity wording "
                               f"{sorted(set(words))}; signals are not graded for clinical severity"))
    curated = [r for r in cited if r.kind == "interaction"]
    if claimed:
        # A curated record under a severity heading must have that severity, even if the
        # line also states its own tier ("curated severity: Major" under "Minor Findings").
        wrong = [r for r in curated if r.severity not in claimed or (heading_tier and r.severity != heading_tier)]
        for rec in wrong:
            out.append(Finding("SEVERITY_MISMATCH", u.line,
                               f"claims {'/'.join(sorted(claimed))} but {rec.citation} is {rec.severity}"))
        extra = text_tiers - {r.severity for r in curated}
        if curated and extra and not wrong:
            out.append(Finding("SEVERITY_MISMATCH", u.line,
                               f"claims {'/'.join(sorted(extra))} but no cited curated record has that severity"))

    # Numbers: PRR values and FAERS report counts must match a supporting record.
    for m in lexicon.PRR_RE.finditer(text):
        val_s = m.group(1)
        decimals = len(val_s.split(".")[1]) if "." in val_s else 0
        tol = 0.5 * 10 ** -decimals + 1e-9
        prrs = [r.prr for r in support_recs if r.prr is not None]
        if not any(abs(float(val_s) - p) <= tol for p in prrs):
            have = ", ".join(f"{p:g}" for p in prrs) or "none"
            out.append(Finding("NUMERIC_MISMATCH", u.line, f"PRR {val_s} not in cited record(s) (PRR: {have})"))
    co_reports = [r.detail.get("reports") for r in support_recs if r.kind == "signal"]
    for m in lexicon.CO_REPORT_RE.finditer(text):
        n = int((m.group(1) or m.group(2)).replace(",", ""))
        if n not in co_reports:
            have = ", ".join(str(c) for c in co_reports if c is not None) or "none"
            out.append(Finding("NUMERIC_MISMATCH", u.line, f"{n} co-reports not in cited record(s) ({have})"))
    counts = [r.detail.get("report_count") for r in support_recs if r.kind == "faers"]
    if counts:
        for m in lexicon.REPORT_COUNT_RE.finditer(text):
            n = int(m.group(1).replace(",", ""))
            if n not in counts:
                out.append(Finding("NUMERIC_MISMATCH", u.line, f"{n} reports not in cited FAERS record(s) {counts}"))

    # Events named in the claim must appear in a supporting record.
    if support_recs:
        for e in lexicon.find_events(text, evidence_events):
            if not lexicon.event_supported(e, support):
                out.append(Finding("EVENT_MISATTRIBUTION", u.line,
                                   f"'{e}' is not what {' '.join(r.citation for r in support_recs[:3])} records"))

    # Mechanism and population words are checked with drug names masked; the record's
    # own event text is masked too ("drug exposure during pregnancy" names no population claim).
    no_drugs = _mask(text, _drug_names(ev))
    for term in lexicon.unsupported_mechanisms(no_drugs, support):
        out.append(Finding("UNSUPPORTED_MECHANISM", u.line, f"'{term}' is not in the cited record's mechanism"))
    for pop in sorted(lexicon.populations(no_drugs) - lexicon.populations(support)):
        out.append(Finding("UNSUPPORTED_POPULATION", u.line, f"population '{pop}' is not in the cited record"))


def validate_report(report: str, evidence: Evidence, final: bool = True) -> ValidationResult:
    """Check a report against its evidence.

    final=True also requires the canonical disclaimer exactly once (reports as
    returned to the user). Returns findings and stats; passed means no findings.
    """
    parsed: ParsedReport = parse_report(report, evidence.aliases)
    ev_events = sorted({r.event for r in evidence.records.values() if r.event})
    drug_names = _drug_names(evidence)
    findings: List[Finding] = []
    clinical = fabricated = uncited = 0
    n_cites = n_valid = 0
    cited_keys: Set[str] = set()

    for u in parsed.units:
        is_clin = _is_clinical(u, ev_events, drug_names)
        if not (is_clin or u.citations) or u.section == "disclaimer":
            continue
        unit_findings: List[Finding] = []
        _check_claim(u, evidence, ev_events, unit_findings)
        if is_clin and not u.citations:
            unit_findings.append(Finding("UNCITED_CLAIM", u.line, f"clinical claim without a citation: {u.text[:80]!r}"))
            uncited += 1
        for c in u.citations:
            n_cites += 1
            rec = evidence.get(c.source, c.record_id)
            if rec is not None:
                cited_keys.add(citation_key(rec.source, rec.record_id))
                m, rd = set(u.context_drugs), set(rec.drugs)
                if not m or m <= rd or rd <= m:
                    n_valid += 1
        if is_clin:
            clinical += 1
            if any(f.code in FABRICATION_CODES for f in unit_findings):
                fabricated += 1
        findings.extend(unit_findings)

    # ---- report-level checks
    cited = [evidence.records[k] for k in cited_keys]
    omitted = omitted_major = major_pairs = 0
    for a, b in evidence.pairs_with_records:
        pair_recs = [r for r in evidence.records.values() if r.kind in PAIR_KINDS and set(r.drugs) == {a, b}]
        pair_cited = [r for r in cited if r.kind in PAIR_KINDS and set(r.drugs) == {a, b}]
        if not pair_cited:
            omitted += 1
            findings.append(Finding("OMITTED_INTERACTION", None,
                                    f"{a} + {b} has {len(pair_recs)} record(s) but none is cited"))
        # Curated records only: a statistical signal has no severity.
        if any(r.kind == "interaction" and r.severity == "Major" for r in pair_recs):
            major_pairs += 1
            if not any(r.kind == "interaction" and r.severity == "Major" for r in pair_cited):
                omitted_major += 1
                findings.append(Finding("OMITTED_MAJOR", None, f"Major interaction {a} + {b} is never cited"))

    # Hidden statistical signals must be stated as "+N more not shown" for their pair.
    for a, b, n in evidence.hidden_signals:
        stated = [int(m.group(1)) for u in parsed.units if {a, b} <= set(u.context_drugs)
                  for m in lexicon.HIDDEN_COUNT_RE.finditer(lexicon.norm(u.text))]
        if n not in stated:
            findings.append(Finding("MISSING_HIDDEN_COUNT", None,
                                    f"{a} + {b}: {n} statistical signal(s) are not shown, but the report "
                                    + (f"states {stated}" if stated else "does not say so")
                                    + f" (expected '+{n} more not shown')"))

    declared = 0
    for a, b in evidence.no_data_pairs:
        mentions = [u for u in parsed.units if a in u.drugs and b in u.drugs]
        if any(u.section == "no_data" or lexicon.declares_absence(u.text) for u in mentions):
            declared += 1
        else:
            findings.append(Finding("MISSING_NO_DATA_DECLARATION", None, f"no-data pair {a} + {b} is not declared"))
        for u in mentions:
            phrase = lexicon.asserts_safety(u.text)
            if phrase:
                findings.append(Finding("CONFLATED_ABSENCE", u.line,
                                        f"{a} + {b} has no curated record, but the report says '{phrase}'"))

    low = lexicon.norm(report)
    for q in evidence.unresolved_inputs:
        if lexicon.norm(q) not in low:
            findings.append(Finding("MISSING_UNRESOLVED_DECLARATION", None, f"unresolved input {q!r} is not declared"))

    if final:
        n = report.count(evidence.disclaimer) if evidence.disclaimer else len(parsed.disclaimer_lines)
        if n != 1:
            findings.append(Finding("MISSING_DISCLAIMER", None, f"canonical disclaimer appears {n} times (expected 1)"))

    stats = {
        "clinical_claims": clinical,
        "fabricated_claims": fabricated,
        "uncited_claims": uncited,
        "citations": n_cites,
        "valid_citations": n_valid,
        "pairs_with_records": len(evidence.pairs_with_records),
        "omitted_pairs": omitted,
        "major_pairs": major_pairs,
        "omitted_major_pairs": omitted_major,
        "no_data_pairs": len(evidence.no_data_pairs),
        "declared_no_data_pairs": declared,
        "semantic_hallucination_rate": _rate(fabricated, clinical),
        "uncited_claim_rate": _rate(uncited, clinical),
        "citation_validity": _rate(n_valid, n_cites),
        "pair_omission_rate": _rate(omitted, len(evidence.pairs_with_records)),
        "major_omission_rate": _rate(omitted_major, major_pairs),
        "completeness": _rate(declared, len(evidence.no_data_pairs)),
    }
    return ValidationResult(passed=not findings, findings=findings, stats=stats)


_COUNTS = ("clinical_claims", "fabricated_claims", "uncited_claims", "citations", "valid_citations",
           "pairs_with_records", "omitted_pairs", "major_pairs", "omitted_major_pairs",
           "no_data_pairs", "declared_no_data_pairs")


def aggregate_stats(stats: List[Dict[str, Optional[float]]]) -> Dict[str, Optional[float]]:
    """Micro-average per-report stats: sum the counts, then recompute the rates."""
    tot = {k: sum(int(s[k]) for s in stats) for k in _COUNTS}
    return {
        "reports": len(stats),
        **tot,
        "semantic_hallucination_rate": _rate(tot["fabricated_claims"], tot["clinical_claims"]),
        "uncited_claim_rate": _rate(tot["uncited_claims"], tot["clinical_claims"]),
        "citation_validity": _rate(tot["valid_citations"], tot["citations"]),
        "pair_omission_rate": _rate(tot["omitted_pairs"], tot["pairs_with_records"]),
        "major_omission_rate": _rate(tot["omitted_major_pairs"], tot["major_pairs"]),
        "completeness": _rate(tot["declared_no_data_pairs"], tot["no_data_pairs"]),
    }
