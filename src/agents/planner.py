"""Planner agent.

Decomposes a normalized medication list into a structured retrieval plan:
  - All unique unordered pairs (combinatorial enumeration)
  - Per-drug side-effect lookups
  - Any drugs flagged as unresolved (surfaced, not suppressed)

The plan is deterministic — no LLM involved at this stage. This is intentional:
enumerating pairs is a combinatorial task where an LLM is strictly worse than
a for-loop, and using an LLM here would introduce hallucination risk for zero
gain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import List, Tuple

from src.data.normalizer import ResolvedDrug


@dataclass
class RetrievalPlan:
    resolved: List[ResolvedDrug]
    unresolved: List[ResolvedDrug]
    pairs: List[Tuple[str, str]] = field(default_factory=list)
    side_effect_lookups: List[str] = field(default_factory=list)

    @property
    def num_drugs(self) -> int:
        return len(self.resolved)

    @property
    def num_pairs(self) -> int:
        return len(self.pairs)

    def summary(self) -> str:
        lines = [
            f"Resolved drugs: {self.num_drugs}",
            f"Unresolved inputs: {len(self.unresolved)}",
            f"Pairs to query: {self.num_pairs}",
        ]
        if self.unresolved:
            lines.append(
                "Unresolved: " + ", ".join(u.query for u in self.unresolved)
            )
        return "\n".join(lines)


class Planner:
    def plan(self, resolved: List[ResolvedDrug]) -> RetrievalPlan:
        ok = [d for d in resolved if d.resolved and d.generic_name]
        bad = [d for d in resolved if not (d.resolved and d.generic_name)]

        # Deduplicate by canonical name (a brand + its generic map to same pair)
        seen = set()
        unique = []
        for d in ok:
            key = (d.generic_name or "").lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(d)

        names = [d.generic_name.lower() for d in unique]
        pairs = list(combinations(sorted(names), 2))

        return RetrievalPlan(
            resolved=unique,
            unresolved=bad,
            pairs=pairs,
            side_effect_lookups=names,
        )
