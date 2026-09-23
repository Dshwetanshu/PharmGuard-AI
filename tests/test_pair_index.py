"""The pair index returns exactly what the old full-table scan returned."""
from __future__ import annotations

from itertools import combinations

import pandas as pd

from src.evaluation.test_cases import TEST_CASES


def _old_scan(df: pd.DataFrame, a: str, b: str, k: int):
    """The pre-index algorithm: per-row key, boolean scan, same sort."""
    key = lambda x, y: "||".join(sorted([(x or "").lower().strip(), (y or "").lower().strip()]))
    keys = df.apply(lambda r: key(r.get("drug_a_name"), r.get("drug_b_name")), axis=1)
    hits = df[keys == key(a, b)]
    rank = {"Major": 0, "Moderate": 1, "Minor": 2, "Unknown": 3}
    hits = hits.assign(_sev=hits["severity"].map(rank).fillna(3)).sort_values(["_sev", "prr"], ascending=[True, False])
    return list(hits.head(k)["record_id"])


def test_index_matches_old_scan_for_every_planned_pair(sample_pipeline):
    ir = sample_pipeline.retriever.interactions
    df, k = ir._df, sample_pipeline.cfg.retrieval.top_k
    names = sorted({n for c in TEST_CASES for n in (d.generic_name for d in sample_pipeline.normalizer.resolve_many(
        c.input_drugs)) if n})
    checked = 0
    for a, b in combinations(names, 2):
        assert [r.record_id for r in ir.retrieve_pair(a, b)] == _old_scan(df, a, b, k), (a, b)
        assert [r.record_id for r in ir.retrieve_pair(b, a)] == _old_scan(df, a, b, k)
        checked += 1
    assert checked > 1000
