"""Report parser: markdown report -> sections, claim units, citations, drug mentions.

Sections follow the template's headings (src/agents/generator.py), which the
LLM system prompt also requires. A "unit" is one bullet or table row, or one
sentence of a paragraph. Citation-only fragments are attached to the previous
sentence, so "Risk of X. [TWOSIDES:TS-1]" is one cited claim.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Tuple

from src.verification import lexicon

FINDING_SECTIONS = {"major": "Major", "moderate": "Moderate", "minor": "Minor", "not_graded": "not graded"}
STATISTICAL_SECTION = "statistical"   # "Statistical reporting signals (not graded for clinical severity)"
DECLARATION_SECTIONS = {"no_data", "unresolved", "coverage", "inputs"}

_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")
_BRACKET = re.compile(r"\[([^\[\]]{1,300})\](?!\()")
_CITE_PART = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_ \-]*?)\s*:\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)\s*$")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[*\"(])")
_ABBREV = re.compile(r"\b(?:e\.g|i\.e|vs|st|approx|dr|fig|etc)\.$", re.I)
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}")


@dataclass
class Citation:
    source: str
    record_id: str
    raw: str


@dataclass
class Unit:
    line: int                       # 1-based line number in the report
    section: str
    text: str                       # text with citations and markdown emphasis removed
    raw: str
    citations: List[Citation] = field(default_factory=list)
    drugs: List[str] = field(default_factory=list)   # canonical names, in order of appearance
    is_bullet: bool = False
    # Drugs the unit is about: its own mentions, or, for a drug-less follow-up
    # sentence ("This is Major [X]"), the previous sentence's on the same line.
    context_drugs: List[str] = field(default_factory=list)


@dataclass
class ParsedReport:
    units: List[Unit]
    sections_seen: List[str]
    disclaimer_lines: List[int]
    text: str


def classify_heading(title: str) -> str:
    t = lexicon.norm(title)
    if "faers" in t or "spontaneous" in t:
        return "faers"
    if "statistical" in t or "reporting signal" in t:   # before "not graded": it's in this heading too
        return STATISTICAL_SECTION
    if "entries were read" in t or "how your entries" in t:
        return "inputs"
    if "not graded" in t or "ungraded" in t or "without a severity grade" in t:
        return "not_graded"
    if "no curated" in t or "no data" in t or "no interaction data" in t:
        return "no_data"
    if "unresolved" in t:
        return "unresolved"
    if "coverage" in t:
        return "coverage"
    if "disclaimer" in t:
        return "disclaimer"
    for tier in ("major", "moderate", "minor"):
        if re.search(rf"\b{tier}\b", t):
            return tier
    if "summary" in t:
        return "summary"
    if "interaction report" in t:
        return "title"
    return "other"


def extract_citations(text: str) -> Tuple[List[Citation], str]:
    """Return citations and the text with citation brackets removed."""
    cites: List[Citation] = []

    def repl(m: "re.Match[str]") -> str:
        parts = re.split(r"[;,]|\s+and\s+", m.group(1))
        found = [_CITE_PART.match(p) for p in parts]
        if not any(found):
            return m.group(0)  # ordinary bracketed text
        for p, fm in zip(parts, found):
            if fm:
                cites.append(Citation(fm.group(1).strip(), fm.group(2).strip(), p.strip()))
        return " "

    stripped = _BRACKET.sub(repl, text)
    return cites, stripped


class DrugMatcher:
    def __init__(self, aliases: Mapping[str, str]):
        self.aliases = {lexicon.norm(a): c for a, c in aliases.items() if a}
        names = sorted(self.aliases, key=len, reverse=True)
        self._rx = (re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(n) for n in names) + r")(?![a-z0-9])")
                    if names else None)

    def find(self, text: str) -> List[str]:
        if self._rx is None:
            return []
        out: List[str] = []
        for m in self._rx.finditer(lexicon.norm(text)):
            c = self.aliases[m.group(1)]
            if c not in out:
                out.append(c)
        return out


def _clean(text: str) -> str:
    text = re.sub(r"[*_`]+", "", text)
    text = text.replace("|", " ")
    return re.sub(r"\s+", " ", text).strip()


def _split_sentences(text: str) -> List[str]:
    pieces, buf = [], ""
    for part in _SENT_SPLIT.split(text):
        if buf and _ABBREV.search(buf):
            buf = f"{buf} {part}"
            continue
        if buf:
            pieces.append(buf)
        buf = part
    if buf:
        pieces.append(buf)
    merged: List[str] = []
    for p in pieces:  # attach citation-only fragments to the previous sentence
        cites, rest = extract_citations(p)
        if merged and cites and not re.sub(r"[\s.;,]", "", rest):
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    return merged


def parse_report(report: str, aliases: Mapping[str, str]) -> ParsedReport:
    matcher = DrugMatcher(aliases)
    units: List[Unit] = []
    sections_seen: List[str] = []
    disclaimer_lines: List[int] = []
    section = "preamble"

    for i, raw_line in enumerate(report.splitlines(), start=1):
        line = raw_line.rstrip()
        if not line.strip() or line.strip() in ("---", "***", "___") or _TABLE_SEP.match(line):
            continue
        h = _HEADING.match(line)
        if h:
            section = classify_heading(h.group(2))
            sections_seen.append(section)
            continue
        if re.match(r"^\s*\**\s*disclaimer\b", line, re.I):
            section = "disclaimer"
            sections_seen.append(section)
            disclaimer_lines.append(i)
        is_bullet = bool(_BULLET.match(line)) or line.lstrip().startswith("|")
        body = _BULLET.sub("", line, count=1)
        chunks = [body] if is_bullet else _split_sentences(body)
        context: List[str] = []
        for chunk in chunks:
            cites, stripped = extract_citations(chunk)
            text = _clean(stripped)
            if not text and not cites:
                continue
            drugs = matcher.find(text)
            context = drugs or context
            units.append(Unit(i, section, text, chunk, cites, drugs, is_bullet, list(context)))
    return ParsedReport(units, sections_seen, disclaimer_lines, report)
