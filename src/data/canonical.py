"""Canonical drug keys shared by the normalizer and every data table.

The local drug vocabulary is the single source of truth: each alias
(``name_lower``) maps to exactly one canonical ``generic_name``. At ingest,
every drug name in the interaction, side-effect and review tables is rewritten
through the same alias map, so the key DrugNormalizer produces for a user's
input is the key stored in the tables.

Names are only ever rewritten through explicit vocabulary entries, never by
string rules such as salt stripping: potassium chloride and sodium bicarbonate
are real active ingredients.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd


def _clean(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip().lower()


def ensure_self_aliases(vocab: pd.DataFrame) -> pd.DataFrame:
    """Return vocab with an alias row for every canonical name that lacks one.

    Without this, a canonical name like "lithium carbonate" (reachable only via
    the alias "lithium") would not resolve to itself by exact match.
    """
    vocab = vocab.copy()
    vocab["name_lower"] = vocab["name_lower"].map(_clean)
    vocab["generic_name"] = vocab["generic_name"].map(_clean)
    known = set(vocab["name_lower"])
    missing = (
        vocab[~vocab["generic_name"].isin(known) & (vocab["generic_name"] != "")]
        .drop_duplicates(subset=["generic_name"])
        .assign(name_lower=lambda d: d["generic_name"])
    )
    return pd.concat([vocab, missing], ignore_index=True)


def build_alias_map(vocab: pd.DataFrame) -> Dict[str, str]:
    """alias -> canonical generic name. Later rows win, matching DrugNormalizer."""
    alias_map: Dict[str, str] = {}
    for name, generic in zip(vocab["name_lower"], vocab["generic_name"]):
        name, generic = _clean(name), _clean(generic)
        if name and generic:
            alias_map[name] = generic
    return alias_map


def canonicalize_columns(df: pd.DataFrame, columns: Sequence[str], alias_map: Mapping[str, str]) -> pd.DataFrame:
    """Rewrite drug-name columns to canonical names. Unknown names are left as-is
    (lowercased) so that find_join_integrity_issues can report them."""
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = df[col].map(lambda v: alias_map.get(_clean(v), _clean(v)))
    return df


@dataclass(frozen=True)
class JoinIssue:
    table: str
    column: str
    name: str
    resolves_to: Optional[str]  # None = not in the vocabulary at all


def find_join_integrity_issues(
    tables: Mapping[str, Tuple[pd.DataFrame, Sequence[str]]],
    alias_map: Mapping[str, str],
) -> List[JoinIssue]:
    """Every drug name in the given tables must resolve to itself through the
    local vocabulary (exact alias match, no fuzzy matching, no network)."""
    issues = []
    for table, (df, columns) in tables.items():
        for col in columns:
            if df is None or col not in df.columns:
                continue
            for name in sorted({_clean(v) for v in df[col]} - {""}):
                target = alias_map.get(name)
                if target != name:
                    issues.append(JoinIssue(table, col, name, target))
    return issues
