"""Time the interaction pair index against the old full-table scan.

Usage:
    python scripts/bench_retriever.py --data-dir data/profiles/research [--pairs 200]

Both methods are run on the same processed interactions table and the same
pairs (every pair of drugs in the evaluation cases that resolve, then random
pairs up to --pairs), and their results are checked to be identical.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.config import Config  # noqa: E402
from src.retrieval.interaction_retriever import InteractionRetriever  # noqa: E402


def old_load(df):
    key = lambda a, b: "||".join(sorted([(a or "").lower().strip(), (b or "").lower().strip()]))
    return df.assign(_pair_key=df.apply(lambda r: key(r.get("drug_a_name"), r.get("drug_b_name")), axis=1))


def old_retrieve(df, a, b, k):
    key = "||".join(sorted([a.lower().strip(), b.lower().strip()]))
    hits = df[df["_pair_key"] == key]
    if hits.empty:
        return []
    rank = {"Major": 0, "Moderate": 1, "Minor": 2, "Unknown": 3}
    hits = hits.assign(_sev=hits["severity"].map(rank).fillna(3)).sort_values(["_sev", "prr"], ascending=[True, False])
    return list(hits.head(k)["record_id"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--pairs", type=int, default=200)
    args = ap.parse_args()
    cfg = Config()
    cfg.paths.data_dir = Path(args.data_dir)
    df = pd.read_parquet(cfg.paths.processed_dir / "interactions.parquet")
    names = sorted(set(df.drug_a_name) | set(df.drug_b_name))
    from src.data.normalizer import DrugNormalizer
    from src.evaluation.test_cases import TEST_CASES
    n = DrugNormalizer(cfg)
    cfg.retrieval.rxnorm_api_enabled = False
    n.load()
    case_drugs = sorted({d.generic_name for c in TEST_CASES for d in n.resolve_many(c.input_drugs) if d.generic_name})
    pairs = list(combinations(case_drugs, 2))
    rng = random.Random(7)
    while len(pairs) < args.pairs:
        pairs.append(tuple(rng.sample(names, 2)))
    pairs = pairs[:args.pairs]

    t = time.perf_counter()
    old = old_load(df)
    old_load_s = time.perf_counter() - t
    t = time.perf_counter()
    ir = InteractionRetriever(cfg).load_from_dataframe(df)
    new_load_s = time.perf_counter() - t

    k = cfg.retrieval.top_k
    t = time.perf_counter()
    old_res = [old_retrieve(old, a, b, k) for a, b in pairs]
    old_q = (time.perf_counter() - t) / len(pairs)
    t = time.perf_counter()
    new_res = [[r.record_id for r in ir.retrieve_pair(a, b)] for a, b in pairs]
    new_q = (time.perf_counter() - t) / len(pairs)

    same = old_res == new_res
    print(f"table rows {len(df):,}; pairs queried {len(pairs)} ({sum(bool(r) for r in new_res)} with records); "
          f"identical results: {same}")
    print(f"load:        old apply {old_load_s:.2f}s  |  new index {new_load_s:.2f}s  ({old_load_s / new_load_s:.0f}x)")
    print(f"per pair:    old scan {old_q * 1000:.2f} ms  |  new index {new_q * 1000:.3f} ms  ({old_q / new_q:.0f}x)")
    print(f"66 pairs (12 drugs): old {66 * old_q * 1000:.0f} ms  |  new {66 * new_q * 1000:.1f} ms")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
