"""Term lists and matchers used by the report checker.

These are hand-written lexicons, so every check built on them is a LOWER
BOUND: a fabricated mechanism, event or population that is phrased in words
not listed here will not be caught. A semantic LLM judge is planned as a
later, complementary layer; it does not replace these deterministic checks.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Set, Tuple


@lru_cache(maxsize=65536)
def norm(text: str) -> str:
    """Lowercase and fold British spellings / punctuation variants (cached: pure)."""
    t = (text or "").lower()
    for a, b in _FOLDS:
        t = a.sub(b, t)
    return re.sub(r"\s+", " ", t).strip()


# Idempotent folds: norm(norm(x)) == norm(x). The US form "gastroesophageal" itself
# contains "oesophag", so that fold applies only at a word start or after a doubled "o"
# ("gastrooesophageal" -> "gastroesophageal").
_FOLDS = [(re.compile(a), b) for a, b in (
    (r"haem", "hem"), (r"aemia", "emia"), (r"(?<![a-z])oedema|(?<=o)oedema|(?<=ph)oedema|(?<=x)oedema", "edema"),
    (r"(?<![a-z])oesophag|(?<=o)oesophag", "esophag"), (r"paediatr", "pediatr"),
    (r"normalised", "normalized"), (r"–", "-"), (r"—", "-"),
)]


@lru_cache(maxsize=65536)
def phrase_re(phrase: str) -> "re.Pattern[str]":
    """Whole-phrase matcher on normalized text."""
    return re.compile(r"(?<![a-z0-9])" + re.escape(norm(phrase)) + r"(?![a-z0-9])")


# ---------------------------------------------------------------- mechanisms
# Families with isoforms: a claimed isoform is supported only by a record
# isoform where one is a prefix of the other (CYP3A ~ CYP3A4, CYP2D6 !~ CYP3A4).
# A family-level claim ("CYP450", "glucuronidation") is supported by any
# mention of that family in the record.
ISOFORM_FAMILIES: Dict[str, Tuple["re.Pattern[str]", "re.Pattern[str]"]] = {
    # family: (isoform pattern with group 1 = isoform, family-level pattern)
    "CYP": (re.compile(r"\bcyp\s*-?\s*(\d{1,2}[a-z]{1,2}\d{0,3})\b"),
            re.compile(r"\bcytochrome\s*p\s*-?\s*450\b|\bcyp\s*-?\s*450\b|\bcyp\b(?!\s*-?\s*\d)")),
    "OATP": (re.compile(r"\boatp\s*-?\s*(\d[a-z]\d{0,2})\b"), re.compile(r"\boatps?\b(?!\s*-?\s*\d)")),
    "UGT": (re.compile(r"\bugt\s*-?\s*(\d[a-z]\d{0,2})\b"),
            re.compile(r"\bugts?\b(?!\s*-?\s*\d)|\bglucuronid\w*")),
}

# Families without isoforms: supported if the family pattern occurs in the record.
MECHANISM_FAMILIES: Dict[str, "re.Pattern[str]"] = {
    "P-glycoprotein": re.compile(r"\bp\s*-?\s*glycoprotein\b|\bp\s*-?\s*gp\b|\babcb1\b|\bmdr1\b"),
    "BCRP": re.compile(r"\bbcrp\b|\babcg2\b"),
    "QT": re.compile(r"\bqtc?\b|\btorsades?\b"),
    "serotonergic": re.compile(r"\bserotonerg\w*|\bserotonin\b|\b5-?ht\d?\w*\b"),
    "MAO": re.compile(r"\bmonoamine oxidase\b|\bmaois?\b|\bmao\b"),
    "protein binding": re.compile(r"\bprotein[- ]binding\b|\bdisplac\w*\b"),
    "enzyme induction": re.compile(r"\binduc(?:er|ers|es|tion|ing)\b"),
    "clearance/elimination": re.compile(r"\bclearance\b|\belimination\b|\bexcretion\b|\btubular secretion\b"),
    "absorption/chelation": re.compile(r"\bchelat\w*\b|\babsorption\b"),
    "CNS depression": re.compile(r"\bcns depress\w*\b|\bcentral nervous system depress\w*\b|\bsedat\w*\b"),
    "anticholinergic": re.compile(r"\banticholinergic\w*\b"),
    "potassium handling": re.compile(r"\bpotassium[- ]sparing\b|\bk[- ]sparing\b|\bpotassium retention\b"),
    "platelet function": re.compile(r"\bplatelets?\b|\bantiplatelet\b"),
    "vitamin K": re.compile(r"\bvitamin k\b"),
}


def mechanism_terms(text: str) -> Dict[str, Set[str]]:
    """{family: set of isoforms found (or {"*"} for a family-level mention)}."""
    t = norm(text)
    found: Dict[str, Set[str]] = {}
    for fam, (iso_re, fam_re) in ISOFORM_FAMILIES.items():
        isos = {m.group(1).upper() for m in iso_re.finditer(t)}
        if fam == "CYP" and "450" in isos:  # "CYP450" is family-level
            isos.discard("450")
            isos.add("*")
        if fam_re.search(t):
            isos.add("*")
        if isos:
            found[fam] = isos
    for fam, rx in MECHANISM_FAMILIES.items():
        if rx.search(t):
            found[fam] = {"*"}
    return found


def unsupported_mechanisms(claim: str, support: str) -> List[str]:
    """Mechanism terms in `claim` that `support` (record text) doesn't back."""
    claimed, have = mechanism_terms(claim), mechanism_terms(support)
    missing = []
    for fam, isos in claimed.items():
        rec = have.get(fam)
        if not rec:
            missing.extend(fam if i == "*" else f"{fam}{i}" for i in sorted(isos))
            continue
        rec_isos = rec - {"*"}
        for iso in sorted(isos - {"*"}):
            if not any(iso.startswith(r) or r.startswith(iso) for r in rec_isos):
                missing.append(f"{fam}{iso}")
    return missing


# --------------------------------------------------------------- populations
POPULATIONS: Dict[str, "re.Pattern[str]"] = {
    "elderly": re.compile(r"\belderly\b|\bolder (?:adults?|patients?|people)\b|\bgeriatric\w*\b"),
    "pediatric": re.compile(r"\bpediatric\w*\b|\bchild(?:ren)?\b|\binfants?\b|\bneonat\w*\b|\badolescen\w*\b"),
    "pregnancy/lactation": re.compile(r"\bpregnan\w*\b|\blactat\w*\b|\bbreast-?feeding\b"),
    "renal impairment": re.compile(r"\brenal (?:impairment|insufficiency|disease)\b|\bkidney disease\b|"
                                   r"\bckd\b|\bimpaired renal\b|\bdialysis\b"),
    "hepatic impairment": re.compile(r"\bhepatic (?:impairment|insufficiency|disease)\b|\bliver disease\b|"
                                     r"\bcirrho\w*\b|\bimpaired hepatic\b"),
}


def populations(text: str) -> Set[str]:
    t = norm(text)
    return {name for name, rx in POPULATIONS.items() if rx.search(t)}


# -------------------------------------------------------------------- events
# Synonym groups: a claimed event is supported if the record names the same
# phrase or any member of the same group.
EVENT_GROUPS: List[Set[str]] = [
    {"bleeding", "hemorrhage", "bleed", "bleeds"},
    {"hyperkalemia", "high potassium", "elevated potassium"},
    {"hypokalemia", "low potassium"},
    {"hypoglycemia", "low blood sugar"},
    {"qt prolongation", "prolonged qt", "qt interval prolongation", "torsades de pointes"},
    {"serotonin syndrome"},
    {"rhabdomyolysis"},
    {"myopathy"},
    {"respiratory depression"},
    {"cns depression"},
    {"bradycardia"},
    {"hypotension"},
    {"acute kidney injury", "kidney injury", "renal failure", "kidney failure", "nephrotoxicity",
     "renal dysfunction"},
    {"hepatotoxicity", "liver injury", "liver toxicity"},
    {"lactic acidosis"},
    {"seizure", "seizures", "convulsions"},
    {"bronchospasm"},
    {"digoxin toxicity"},
    {"lithium toxicity"},
    {"methotrexate toxicity"},
    {"theophylline toxicity"},
    {"contraceptive failure"},
    {"serotonin toxicity"},
]
_GROUP_OF: Dict[str, int] = {norm(t): i for i, g in enumerate(EVENT_GROUPS) for t in g}


# Record "events" that are too generic to be an event claim (DDInter falls back
# to "interaction" when a record has no condition text).
GENERIC_EVENTS = {"interaction", "interactions", "drug interaction", "adverse event", "adverse events",
                  "adverse reaction", "side effect", "side effects"}


def find_events(text: str, extra_phrases: Iterable[str] = ()) -> List[str]:
    """Event phrases in text (lexicon + evidence events), longest match wins."""
    t = norm(text)
    spans = []
    for p in _event_phrases(tuple(extra_phrases)):
        if p not in t:            # cheap substring filter before the boundary-aware regex
            continue
        for m in phrase_re(p).finditer(t):
            spans.append((m.start(), m.end(), p))
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    kept: List[Tuple[int, int, str]] = []
    for s in spans:
        if any(k[0] <= s[0] and s[1] <= k[1] for k in kept):
            continue
        kept.append(s)
    return [p for _, _, p in kept]


@lru_cache(maxsize=1024)
def _event_phrases(extra_phrases: Tuple[str, ...]) -> Tuple[str, ...]:
    phrases = {norm(p) for p in _GROUP_OF} | {norm(p) for p in extra_phrases if p}
    return tuple(sorted(phrases - GENERIC_EVENTS))


def event_supported(event: str, support: str) -> bool:
    """True if the record text names the event, a synonym, or (for compound
    phrases like "gastrointestinal bleeding") every lexicon event inside it."""
    s = norm(support)
    e = norm(event)
    if phrase_re(e).search(s):
        return True

    def group_present(g: int) -> bool:
        return any(phrase_re(term).search(s) for term in EVENT_GROUPS[g])

    if e in _GROUP_OF:
        return group_present(_GROUP_OF[e])
    inner = {_GROUP_OF[norm(x)] for x in find_events(e) if norm(x) in _GROUP_OF}
    return bool(inner) and all(group_present(g) for g in inner)


# ------------------------------------------------------------------ severity
TIERS = ("major", "moderate", "minor")
_TIER_CONTEXT = re.compile(
    r"\b(major|moderate|minor)\b(?=\s*(?:[)\]:]|-?\s*(?:severity|interaction|risk|finding|tier|level|grade)))"
    r"|(?:severity|tier|graded?|classified as|rated)\s*(?:[:=]|of|is|as)?\s*\b(major|moderate|minor)\b"
    r"|\(\s*(major|moderate|minor)\s*\)",
)
_NOT_GRADED = re.compile(r"\bnot graded\b|\bungraded\b|\bseverity (?:is )?unknown\b")


# Any wording that grades clinical severity. A statistical signal (PRR) has no
# severity, so none of these may be attached to one. Negated forms ("not graded
# for clinical severity") are removed first.
_SEVERITY_WORD = re.compile(
    r"\b(?:major|moderate|minor|mild|severe|severity|serious|dangerous|life-threatening|contraindicat\w*|"
    r"clinically (?:significant|relevant|important)|high-risk|high risk|low-risk|low risk)\b"
)
_SEVERITY_NEGATED = re.compile(
    r"\b(?:not|never) (?:graded|rated|classified|a grade|an? (?:clinical )?severity grade)"
    r"(?: (?:for|of|by) (?:clinical )?severity)?\b|\bseverity (?:is )?not graded\b|"
    r"\bno (?:clinical )?severity(?: grade)?\b|\bnot graded\b"
)


def severity_words(text: str) -> List[str]:
    """Severity wording in text (callers mask the record's own event text first)."""
    return [m.group(0) for m in _SEVERITY_WORD.finditer(_SEVERITY_NEGATED.sub(" ", norm(text)))]


def claimed_tiers(text: str) -> Set[str]:
    """Severity tiers asserted in text. Bare words ("minor bleeding") are not
    tiers; a tier word needs severity context. Callers mask record event and
    mechanism text first so an event name can't be read as a tier."""
    t = norm(text)
    out = {next(g for g in m.groups() if g).capitalize() for m in _TIER_CONTEXT.finditer(t)}
    if _NOT_GRADED.search(t):
        out.add("not graded")
    return out


# ------------------------------------------------------------ absence/safety
_SAFETY = [
    re.compile(r"\bsafe(?:ly|ty)?\b(?! ?(?:data|information))"),
    re.compile(r"\bno (?:known |significant |clinically (?:significant|relevant) |documented |reported )?"
               r"interactions?\b(?! (?:data|records?|evidence|information))"),
    re.compile(r"\b(?:do|does|will|did) not interact\b|\bdon'?t interact\b|\bnon-?interacting\b"),
    re.compile(r"\bno (?:clinically )?(?:relevant |significant )?(?:risk|concern)s?\b"),
    re.compile(r"\bcan be (?:safely )?(?:taken|used|combined|co-?administered|given) together\b"),
    re.compile(r"\bcompatible\b"),
]
_NEGATION = re.compile(r"(?:\bnot\b|n't\b|\bno evidence\b|\bnor\b|\bneither\b)[^.;]{0,40}$")


def asserts_safety(text: str) -> Optional[str]:
    """Return the phrase if text describes a combination as safe / non-interacting."""
    t = norm(text)
    for rx in _SAFETY:
        for m in rx.finditer(t):
            if rx is _SAFETY[0] and _NEGATION.search(t[: m.start()]):
                continue  # "does not mean ... safe"
            return m.group(0)
    return None


_ABSENCE_OF_DATA = re.compile(
    r"\bno (?:curated )?(?:interaction )?(?:data|records?|evidence|information)\b|\bnot found\b|"
    r"\bno record\b|\bnot (?:in|covered by) the (?:queried )?sources\b"
)


def declares_absence(text: str) -> bool:
    return bool(_ABSENCE_OF_DATA.search(norm(text)))


# ------------------------------------------------------------- clinical cues
CLINICAL_CUE = re.compile(
    r"\b(?:risk|increas\w*|decreas\w*|rais\w*|lower\w*|reduc\w*|toxic\w*|inhibit\w*|induc\w*|potentiat\w*|"
    r"interact\w*|effect\w*|levels?|concentrations?|exposure|adverse|monitor\w*|avoid\w*|contraindicat\w*|"
    r"prolong\w*|caus\w*|lead\w*|result\w*|danger\w*|serious|severe|fatal)\b"
)

PRR_RE = re.compile(
    r"\b(?:prr|proportional reporting ratio)\b\s*(?:\(prr\)\s*)?(?:=|:|of|is|was|~|≈|at)?\s*(\d+(?:\.\d+)?)"
)
REPORT_COUNT_RE = re.compile(r"\b(\d[\d,]*)\s+(?:spontaneous\s+)?(?:faers\s+)?reports?\b")
_COUNT = r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+)(?![\d.])"
CO_REPORT_RE = re.compile(_COUNT + r"\s+co-?reports?\b|\bco-?reports?\s*(?:[:=]|of)?\s*" + _COUNT)
# "+N more not shown": statistical signals retrieved for a pair but not selected.
HIDDEN_COUNT_RE = re.compile(r"\+\s*(\d+)\s+more\b[^.;\n]{0,40}?\bnot shown\b")
