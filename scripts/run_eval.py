"""Run PharmGuard evaluation against the curated test suite.

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
    print(f"Evaluating {len(cases)} case(s)...")
    results = evaluator.evaluate_all(cases)

    report = results.as_dict()
    print("\n=== Aggregate ===")
    print(f"Mean recall:    {report['mean_recall']}")
    print(f"Mean precision: {report['mean_precision']}")
    print(f"Cases evaluated: {report['num_cases']}")

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2))
        print(f"\nFull report saved to {out}")


if __name__ == "__main__":
    main()
