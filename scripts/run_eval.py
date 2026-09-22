"""Run PharmGuard evaluation against the curated test suite.

Two retrieval-only checks (no LLM is called):
  1. Internal consistency: ground truth is derived from the same normalizer and
     interaction table the retriever uses, so recall/precision are 1.0 by
     construction. It only catches bugs in pair enumeration/lookup plumbing.
  2. Hand labels: retrieval scored against known_interaction_pairs in
     src/evaluation/test_cases.py (partial labels; precision is a lower bound).
All current data is synthetic sample data.

Usage:
    python scripts/run_eval.py
    python scripts/run_eval.py --output reports/eval.json
    python scripts/run_eval.py --subset GER   # only cases whose id starts with GER
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.config import config
from src.data.normalizer import DrugNormalizer
from src.data.storage import read_table
from src.retrieval.interaction_retriever import InteractionRetriever
from src.retrieval.side_effect_retriever import SideEffectRetriever
from src.agents.retriever import Retriever
from src.agents.planner import Planner
from src.data.canonical import build_alias_map
from src.evaluation.hand_labels import score_hand_labels
from src.evaluation.metrics import Evaluator
from src.evaluation.test_cases import TEST_CASES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=str, default=None, help="Path to save JSON report.")
    ap.add_argument("--subset", type=str, default=None, help="Filter case IDs by prefix.")
    args = ap.parse_args()

    normalizer = DrugNormalizer().load()
    interaction_retriever = InteractionRetriever().load()
    side_effect_retriever = SideEffectRetriever().load()
    retriever = Retriever(interaction_retriever, side_effect_retriever)

    interactions_df = read_table(config.paths.processed_dir / "interactions.parquet")

    cases = TEST_CASES
    if args.subset:
        cases = [c for c in cases if c.case_id.startswith(args.subset)]

    evaluator = Evaluator(normalizer, retriever, interactions_df)
    print(f"Evaluating {len(cases)} case(s) (retrieval only; synthetic sample data)...")
    internal = evaluator.evaluate_all(cases).as_dict()

    planner = Planner()

    def retrieve_pairs(drugs):
        plan = planner.plan(normalizer.resolve_many(drugs))
        return set(retriever.execute(plan).interactions)

    vocab = read_table(config.paths.processed_dir / "drug_vocabulary.parquet")
    hand = score_hand_labels(cases, retrieve_pairs, build_alias_map(vocab))

    report = {"internal_consistency": internal, "hand_labels": hand}

    print("\n=== Internal consistency (1.0 by construction: same normalizer + table) ===")
    print(f"Mean recall:    {internal['mean_recall']}")
    print(f"Mean precision: {internal['mean_precision']}")
    print("\n=== Hand-labelled pairs (partial labels) ===")
    print(f"Recall:                  {hand['recall']}  ({hand['hits']}/{hand['labelled_pairs']} labelled pairs retrieved)")
    print(f"Precision (lower bound): {hand['precision_lower_bound']}  "
          f"({hand['hits']}/{hand['retrieved_pairs']} retrieved pairs are labelled)")
    for case_id, pair in hand["missed"]:
        print(f"  missed: {case_id} {pair[0]} + {pair[1]}")
    print(f"Cases evaluated: {internal['num_cases']}")

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2))
        print(f"\nFull report saved to {out}")


if __name__ == "__main__":
    main()
