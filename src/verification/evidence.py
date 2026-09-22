"""Evidence adapter: RetrievalResult (+ FAERS) -> flat, JSON-serializable records.

Everything here is plain str/float/int/list/dict with string keys (no tuple
keys, no dataclass instances in the serialized form), so it can be stored as
LangGraph state and round-tripped through JSON.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional

TIERS = ("Major", "Moderate", "Minor")


def citation_key(source: str, record_id: str) -> str:
    """Lookup key for a citation. Sources are case-insensitive, IDs are not."""
    return f"{source.strip().lower()}:{record_id.strip()}"


@dataclass
class NormalizedRecord:
    record_id: str
    source: str
    kind: str                      # "interaction" | "faers" | "side_effect"
    drug_a: str
    drug_b: Optional[str]          # None for single-drug side-effect records
    event: str
    severity: Optional[str]        # Major/Moderate/Minor/"not graded"; None for FAERS and side effects
    prr: Optional[float]
    mechanism: Optional[str]
    detail: Dict[str, Any] = field(default_factory=dict)   # e.g. {"report_count": 600}

    @property
    def citation(self) -> str:
        return f"[{self.source}:{self.record_id}]"

    @property
    def drugs(self) -> List[str]:
        return [d for d in (self.drug_a, self.drug_b) if d]

    def support_text(self) -> str:
        """All record text a claim citing this record may draw on."""
        return " ".join(x for x in (self.event, self.mechanism or "") if x)


@dataclass
class Evidence:
    records: Dict[str, NormalizedRecord]          # citation_key -> record
    drugs: List[str]                              # canonical names analysed
    pairs_with_records: List[List[str]]           # curated interaction pairs, sorted
    no_data_pairs: List[List[str]]
    unresolved_inputs: List[str]
    aliases: Dict[str, str]                       # lowercase alias -> canonical name
    disclaimer: Optional[str] = None

    def get(self, source: str, record_id: str) -> Optional[NormalizedRecord]:
        return self.records.get(citation_key(source, record_id))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["records"] = {k: asdict(v) for k, v in self.records.items()}
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Evidence":
        d = dict(d)
        d["records"] = {k: NormalizedRecord(**v) for k, v in d["records"].items()}
        return cls(**d)


def _severity(value: Optional[str]) -> str:
    return value if value in TIERS else "not graded"


def build_evidence(plan, result, aliases: Optional[Mapping[str, str]] = None,
                   disclaimer: Optional[str] = None) -> Evidence:
    """Adapt a RetrievalPlan + RetrievalResult into an Evidence bundle.

    ``aliases`` maps lowercase alias -> canonical name (e.g. from
    DrugNormalizer.aliases_for). It is filtered to the drugs in this request;
    each canonical name is always an alias of itself.
    """
    records: Dict[str, NormalizedRecord] = {}

    def add(rec: NormalizedRecord) -> None:
        records[citation_key(rec.source, rec.record_id)] = rec

    for (a, b), recs in result.interactions.items():
        for r in recs:
            detail = {"frequency": r.frequency} if r.frequency is not None else {}
            add(NormalizedRecord(r.record_id, r.source, "interaction", a, b, r.condition,
                                 _severity(r.severity), r.prr, r.mechanism, detail))
    for (a, b), sigs in result.faers_signals.items():
        for s in sigs:
            add(NormalizedRecord(s.record_id, s.source, "faers", a, b, s.condition, None, None, None,
                                 {"report_count": int(s.report_count), "query_url": s.source_url}))
    for drug, ses in result.side_effects.items():
        for s in ses:
            add(NormalizedRecord(s.record_id, s.source, "side_effect", drug, None, s.side_effect,
                                 None, None, None, {"umls_cui": s.umls_cui} if s.umls_cui else {}))

    drugs = [d.generic_name.lower() for d in plan.resolved if d.generic_name]
    relevant = set(drugs) | {x for r in records.values() for x in r.drugs}
    alias_map = {n: n for n in relevant}
    for alias, canonical in (aliases or {}).items():
        if str(canonical).lower() in relevant:
            alias_map[str(alias).strip().lower()] = str(canonical).lower()

    return Evidence(
        records=records,
        drugs=drugs,
        pairs_with_records=[list(p) for p in sorted(result.interactions)],
        no_data_pairs=[list(p) for p in result.no_data_pairs],
        unresolved_inputs=[u.query for u in plan.unresolved],
        aliases=alias_map,
        disclaimer=disclaimer,
    )


def records_for(evidence: Evidence, drugs: Iterable[str]) -> List[NormalizedRecord]:
    """Records "about" the mentioned drugs: pair records whose drugs are all
    mentioned (or that contain the single mentioned drug), plus side effects."""
    ds = set(drugs)
    out = []
    for r in evidence.records.values():
        rd = set(r.drugs)
        if (len(ds) == 1 and ds & rd) or (len(ds) > 1 and rd <= ds):
            out.append(r)
    return out
