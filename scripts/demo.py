"""Simple CLI demo for PharmGuard.

Usage:
    python scripts/demo.py lisinopril spironolactone metformin aspirin
    python scripts/demo.py --llm lisinopril spironolactone    # uses the configured LLM
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline import PharmGuardPipeline


def main():
    ap = argparse.ArgumentParser(description="PharmGuard CLI demo.")
    ap.add_argument("drugs", nargs="+", help="Drug names (generic or brand).")
    ap.add_argument("--llm", action="store_true",
                    help="Use the configured LLM for report generation (requires API key).")
    args = ap.parse_args()

    try:
        pipeline = PharmGuardPipeline.from_config()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Hint: run `python scripts/ingest_data.py --sample` first.", file=sys.stderr)
        sys.exit(1)

    result = pipeline.run(args.drugs, use_llm=args.llm)
    print(result.report)
    print()
    print("=" * 60)
    print(f"Latency: {result.latency_seconds:.3f}s  |  Pairs: {result.plan.num_pairs}  |  "
          f"Interactions: {result.retrieval.total_interactions}  |  "
          f"No-data pairs: {len(result.retrieval.no_data_pairs)}")


if __name__ == "__main__":
    main()
