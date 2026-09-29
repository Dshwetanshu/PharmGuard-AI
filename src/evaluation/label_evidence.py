"""FDA labeling as an independent reference for drug pairs (openFDA drug label API; public domain).

For a pair (A, B), A's current label is searched for B and B's for A, in the sections
Boxed Warning, Contraindications, Warnings and Precautions (or Warnings, Precautions)
and Drug Interactions. B counts as named if its generic name, a salt form or a brand
name (RxNorm / Drugs@FDA aliases) appears as a whole word, e.g. as the example in
"strong CYP3A4 inhibitors (e.g., clarithromycin)". A class named without the drug
("hormonal contraceptives") does not count.

The label chosen for a drug: single-ingredient labels whose generic name maps to the
drug through the vocabulary; an NDA label first, then the most recent effective date.

The wording around each match is classified **heuristically** (keyword rules below).
The context is the text around the match up to the nearest sentence end, semicolon,
bullet or section reference such as "(7.2)", so a neighbouring list item's advice
isn't attributed to it. In a PLR drug-interaction table, where the drug is listed
under "Examples:" after the row's "Intervention:", the row's Intervention text is
added. Classes, from strongest to weakest: contraindicated > avoid / not recommended >
monitor / adjust > mentioned without guidance > not mentioned. The strongest class
over both labels and all sections is the pair's label evidence.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

LABEL_ENDPOINT = "https://api.fda.gov/drug/label.json"
SECTIONS = [("boxed_warning", "Boxed Warning"), ("contraindications", "Contraindications"),
            ("warnings_and_cautions", "Warnings and Precautions"), ("warnings", "Warnings"),
            ("precautions", "Precautions"), ("drug_interactions", "Drug Interactions")]
CLASSES = ("contraindicated", "avoid_or_not_recommended", "monitor_or_adjust", "mentioned_without_guidance",
           "not_mentioned")
CLASS_TEXT = {"contraindicated": "contraindicated", "avoid_or_not_recommended": "avoid / not recommended",
              "monitor_or_adjust": "monitor / adjust", "mentioned_without_guidance": "mentioned without guidance",
              "not_mentioned": "not mentioned"}
STRENGTH = {c: i for i, c in enumerate(CLASSES)}          # lower = stronger
# For comparing with DDInter grades (also heuristic).
AS_SEVERITY = {"contraindicated": "Major", "avoid_or_not_recommended": "Major", "monitor_or_adjust": "Moderate",
               "mentioned_without_guidance": None, "not_mentioned": None}

_AVOID = re.compile(r"\bavoid\w*|\bnot recommended\b|\bshould not be (?:used|taken|given|administered|co-?administered|"
                    r"combined)|\bdo not (?:use|take|administer|co-?administer|combine|prescribe)\b|\bmust not\b")
_MONITOR = re.compile(r"\bmonitor\w*|\badjust\w*|\breduc\w* (?:the )?(?:dose|dosage)|\b(?:decreas|reduc)\w* by \d|\bdose (?:reduction|adjustment)|"
                      r"\blower (?:the )?(?:dose|dosage)|\bdo not exceed\b|\blimit\w*|\bcaution\w*|\bconsider\w*|"
                      r"\bclosely\b|\btitrat\w*|\bseparate\w*|\bask a doctor\b|\bask a pharmacist\b|\breserve\b|"
                      r"\binterrupt\w*|\bdiscontinu\w*|\bsuspend\w*|\bhours (?:before|after)\b")


@dataclass
class Label:
    drug: str
    set_id: str
    version: str
    effective_time: str
    application_number: str
    brand: str
    sections: Dict[str, str]


@dataclass
class Match:
    label_drug: str
    other_drug: str
    set_id: str
    version: str
    section: str
    alias: str
    snippet: str
    klass: str


@dataclass
class PairEvidence:
    pair: Tuple[str, str]
    klass: str
    labels_found: Dict[str, Optional[Dict[str, str]]]
    best: Optional[Match]
    matches: List[Match] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pair"] = list(self.pair)
        return d


def label_url(drug: str, limit: int = 100) -> str:
    from urllib.parse import urlencode
    return LABEL_ENDPOINT + "?" + urlencode({"search": 'openfda.generic_name:"' + drug.replace('"', "") + '"',
                                             "limit": str(limit)})


def choose_label(drug: str, results: Sequence[dict], to_canonical: Callable[[str], Optional[str]]) -> Optional[Label]:
    cands = []
    for r in results:
        names = (r.get("openfda") or {}).get("generic_name") or []
        if len(names) != 1 or to_canonical(names[0].lower().strip()) != drug:
            continue
        app = ((r.get("openfda") or {}).get("application_number") or [""])[0]
        sections = {k: " ".join(r[k]) for k, _ in SECTIONS if r.get(k)}
        if not sections:
            continue
        cands.append((app.startswith("NDA"), r.get("effective_time", ""), r, app, sections))
    if not cands:
        return None
    _, eff, r, app, sections = max(cands, key=lambda c: (c[0], c[1]))
    brand = ((r.get("openfda") or {}).get("brand_name") or [""])[0]
    return Label(drug, r["set_id"], str(r.get("version", "")), eff, app, brand, sections)


_BOUNDARY = re.compile(r"[.;•]\s|\(\s*\d+(?:\.\d+)*\s*\)|\[see [^\]]*\]", re.I)


def context(text: str, start: int, end: int, before: int = 250, after: int = 250) -> str:
    """The clause around text[start:end], cut at the nearest boundary on each side."""
    left = text[max(0, start - before):start]
    cuts = list(_BOUNDARY.finditer(left))
    if cuts:
        left = left[cuts[-1].end():]
    right = text[end:end + after]
    m = _BOUNDARY.search(right)
    if m:
        right = right[:m.start()]
    ctx = (left + text[start:end] + right).strip()
    back = text[max(0, start - 3000):start]
    ex = back.lower().rfind("examples")
    if ex >= 0 and back.lower().rfind("clinical impact") < ex:
        iv = back.lower().rfind("intervention", 0, ex)
        if iv >= 0:
            ctx = back[iv:ex].strip() + " … " + ctx
    return ctx


def classify(section_key: str, sentence: str) -> str:
    t = sentence.lower()
    if section_key == "contraindications" or "contraindicat" in t:
        return "contraindicated"
    if _AVOID.search(t):
        return "avoid_or_not_recommended"
    if _MONITOR.search(t):
        return "monitor_or_adjust"
    return "mentioned_without_guidance"


def _snippet(sentence: str, alias: str, width: int = 170) -> str:
    i = sentence.lower().find(alias)
    lo, hi = max(0, i - width // 2), min(len(sentence), i + len(alias) + width // 2)
    return ("…" if lo else "") + sentence[lo:hi].strip() + ("…" if hi < len(sentence) else "")


def find_matches(label: Label, other: str, aliases: Iterable[str]) -> List[Match]:
    names = sorted({a for a in aliases if len(a) >= 4}, key=len, reverse=True)
    rx = re.compile(r"(?<![a-z0-9-])(" + "|".join(re.escape(a) for a in names) + r")(?![a-z0-9-])")
    out = []
    for key, title in SECTIONS:
        text = label.sections.get(key)
        if not text:
            continue
        best: Optional[Match] = None
        for m in rx.finditer(text.lower()):
            ctx = context(text, m.start(), m.end())
            cand = Match(label.drug, other, label.set_id, label.version, title, m.group(1),
                         _snippet(ctx, m.group(1), width=240), classify(key, ctx))
            if best is None or STRENGTH[cand.klass] < STRENGTH[best.klass]:
                best = cand
        if best is not None:
            out.append(best)
    return out


def pair_evidence(a: str, b: str, labels: Dict[str, Optional[Label]], aliases: Dict[str, List[str]]) -> PairEvidence:
    matches: List[Match] = []
    for x, y in ((a, b), (b, a)):
        if labels.get(x) is not None:
            matches += find_matches(labels[x], y, aliases.get(y, [y]))
    found = {d: ({"set_id": l.set_id, "version": l.version, "effective_time": l.effective_time,
                  "application_number": l.application_number, "brand": l.brand} if l else None)
             for d, l in ((a, labels.get(a)), (b, labels.get(b)))}
    best = min(matches, key=lambda m: STRENGTH[m.klass]) if matches else None
    return PairEvidence((a, b), best.klass if best else "not_mentioned", found, best, matches)


def decide(expected: str, ev: PairEvidence) -> Tuple[str, str]:
    """(reference, reason). reference: "interaction", "none_weak" or "unclear".

    An expected interaction is settled only by label guidance (monitor / adjust or stronger).
    A negative control is settled (weakly) only if both labels were found and neither names
    the other drug. Everything else, including any conflict with the row's expectation, is unclear.
    """
    strong = STRENGTH[ev.klass] <= STRENGTH["monitor_or_adjust"]
    both = all(v is not None for v in ev.labels_found.values())
    if expected == "interaction":
        if strong:
            return "interaction", f"label: {CLASS_TEXT[ev.klass]}"
        if ev.klass == "mentioned_without_guidance":
            return "unclear", "named in a label, but without guidance the heuristic recognises"
        missing = [d for d, v in ev.labels_found.items() if v is None]
        return "unclear", ("no single-ingredient label found for " + ", ".join(missing)) if missing else \
            "neither label names the other drug (it may be covered only by a class)"
    if ev.klass == "not_mentioned" and both:
        return "none_weak", "not mentioned in either label (weak evidence of no interaction)"
    if not both:
        return "unclear", "no single-ingredient label found for " + ", ".join(d for d, v in ev.labels_found.items() if v is None)
    return "unclear", f"negative control, but a label says: {CLASS_TEXT[ev.klass]}"


def severity_comparison(rows: Sequence[Tuple[str, Optional[str]]]) -> Dict[str, object]:
    """rows: (label class, PharmGuard's DDInter grade or None) for settled interactions."""
    from collections import Counter
    grid = Counter((CLASS_TEXT[k], g or "no graded record") for k, g in rows)
    mapped = [(AS_SEVERITY[k], g) for k, g in rows if AS_SEVERITY[k] and g]
    agree = sum(1 for s, g in mapped if s == g)
    return {"pairs": len(rows), "grid_label_class_by_ddinter": {f"{a} / {b}": n for (a, b), n in sorted(grid.items())},
            "mapped_pairs": len(mapped), "mapped_agreement": round(agree / len(mapped), 4) if mapped else None,
            "ddinter_lower_than_label": sum(1 for s, g in mapped if {"Major": 3, "Moderate": 2, "Minor": 1}[g]
                                            < {"Major": 3, "Moderate": 2}[s]),
            "mapping": "contraindicated or avoid -> Major; monitor/adjust -> Moderate (heuristic)"}
