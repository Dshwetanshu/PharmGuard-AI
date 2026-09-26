"""Validation for user-supplied drug names: the single place they are checked.

Names end up in RxNorm/FAERS query strings and in the LLM prompt, so only a
conservative character set is accepted: ASCII letters and digits, space, and
the punctuation that appears in real drug names (- . ' ( ) / _ ,). Commas and
the length limit come from RxNorm's own ingredient names ("insulin, regular,
human" is 23 characters; the longest RxNorm Current Prescribable ingredient
name is 148). Anything else (newlines, quotes, brackets, angle brackets,
colons, ...) is rejected rather than silently stripped, so the user sees
exactly what was not analysed.
"""
from __future__ import annotations

import re
from typing import List, Sequence

MAX_NAME_LENGTH = 150
_ALLOWED = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .'()/_,-]*")


class InvalidDrugNameError(ValueError):
    pass


def split_drug_input(raw: str) -> List[str]:
    """Split free-text input into names: one per line if there are several lines
    (so a name like "insulin, regular, human" stays whole), else comma-separated."""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    parts = lines if len(lines) > 1 else [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def clean_drug_names(names: Sequence[str]) -> List[str]:
    """Collapse runs of spaces and validate each name.

    Plain-language text ("aspirin ignore previous instructions") can't be ruled
    out by character rules; the generator delimits names as data for that.

    Raises InvalidDrugNameError listing every invalid input.
    """
    cleaned, problems, bad_chars = [], [], False
    for raw in names:
        if not isinstance(raw, str):
            problems.append(f"{raw!r} is not text")
            continue
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
            # Checked before collapsing whitespace, so newlines can't be turned
            # into spaces and slip a second "line" into the prompt.
            problems.append(f"{raw[:20]!r} contains control characters such as newlines")
            continue
        name = re.sub(r" {2,}", " ", raw.strip())
        if not name:
            problems.append("an entry is empty")
        elif len(name) > MAX_NAME_LENGTH:
            problems.append(f"{name[:20]!r}... is longer than {MAX_NAME_LENGTH} characters")
        elif not _ALLOWED.fullmatch(name):
            problems.append(f"{name!r} uses characters a drug name can't have")
            bad_chars = True
        else:
            cleaned.append(name)
    if problems:
        lead = "This drug name can't be checked: " if len(problems) == 1 else "These drug names can't be checked: "
        hint = (" Drug names can use letters, numbers, spaces and - . ' ( ) / _ , characters, "
                "starting with a letter or number.") if bad_chars else ""
        raise InvalidDrugNameError(lead + "; ".join(problems) + "." + hint)
    return cleaned
