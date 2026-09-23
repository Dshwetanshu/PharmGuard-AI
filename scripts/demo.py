"""Simple CLI demo for PharmGuard.

Usage:
    python scripts/demo.py lisinopril spironolactone metformin aspirin
    python scripts/demo.py --llm lisinopril spironolactone    # LLM mode (needs an API key)
    python scripts/demo.py --legacy lisinopril spironolactone # pre-LangGraph pipeline, for comparison
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.input_validation import InvalidDrugNameError


def run_legacy(args):
    from src.pipeline import PharmGuardPipeline

    pipeline = PharmGuardPipeline.from_config()
    result = pipeline.run(args.drugs, use_llm=args.llm)
    print(result.report)
    print()
    print("=" * 60)
    print(f"[legacy pipeline] report_source={result.trace['report_source']}  |  "
          f"Latency: {result.latency_seconds:.3f}s  |  Pairs: {result.plan.num_pairs}  |  "
          f"Interactions: {result.retrieval.total_interactions}  |  "
          f"No-data pairs: {len(result.retrieval.no_data_pairs)}")


def run_graph(args):
    from src.graph import REPORT_SOURCES, PharmGuardGraph, Settings

    graph = PharmGuardGraph(Settings.from_env(mode="llm" if args.llm else "deterministic"))
    state = graph.run(args.drugs)
    print(state["report"])
    print()
    print("=" * 60)
    print(f"report_source={state['report_source']}: {REPORT_SOURCES[state['report_source']]}")
    print(f"Latency: {state['latency_seconds']:.3f}s  |  Pairs: {len(state['plan']['pairs'])}  |  "
          f"No-data pairs: {len((state.get('retrieval') or {}).get('no_data_pairs', []))}")
    print("Trajectory: " + " -> ".join(f"{t['node']}[{t['status']}]" for t in state["trajectory"]))


def main():
    ap = argparse.ArgumentParser(description="PharmGuard CLI demo.")
    ap.add_argument("drugs", nargs="+", help="Drug names (generic or brand).")
    ap.add_argument("--llm", action="store_true",
                    help="Use the configured LLM for report generation (requires API key).")
    ap.add_argument("--legacy", action="store_true",
                    help="Run the pre-LangGraph pipeline (src/pipeline.py) for comparison.")
    args = ap.parse_args()

    try:
        (run_legacy if args.legacy else run_graph)(args)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Hint: run `python scripts/ingest_data.py --sample` first.", file=sys.stderr)
        sys.exit(1)
    except InvalidDrugNameError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
