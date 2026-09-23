"""Simple CLI demo for PharmGuard.

Usage:
    python scripts/demo.py lisinopril spironolactone metformin aspirin
    python scripts/demo.py --llm lisinopril spironolactone    # LLM mode (needs an API key)
    python scripts/demo.py --legacy lisinopril spironolactone # pre-LangGraph pipeline, for comparison
    python scripts/demo.py --simulate-retry lisinopril spironolactone aspirin
        # SIMULATED LLM (no API key): draft 1 has a fabricated CYP3A4 mechanism and is
        # rejected; draft 2 is clean and passes. Shows the retry path in a trace.

Tracing: set PHARMGUARD_TRACING=phoenix|langsmith (see docs/OBSERVABILITY.md).
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
    from src.graph.simulated import SIMULATED_LABEL, simulated_retry_graph

    graph = PharmGuardGraph(Settings.from_env(mode="llm" if args.llm else "deterministic"))
    tags = ["entrypoint:demo"]
    if args.simulate_retry:
        graph = simulated_retry_graph(graph, args.drugs)
        tags.append("simulated")
        print(f"[{SIMULATED_LABEL}] scripted drafts, not a model: draft 1 contains a fabricated "
              "CYP3A4 mechanism, draft 2 is clean.\n")
    state = graph.run(args.drugs, tags=tags, metadata={"entrypoint": "demo.py"})
    graph.tracing.flush()
    print(state["report"])
    print()
    print("=" * 60)
    sim = f" [{SIMULATED_LABEL}]" if args.simulate_retry else ""
    print(f"report_source={state['report_source']}{sim}: {REPORT_SOURCES[state['report_source']]}")
    print(f"Latency: {state['latency_seconds']:.3f}s  |  Pairs: {len(state['plan']['pairs'])}  |  "
          f"No-data pairs: {len((state.get('retrieval') or {}).get('no_data_pairs', []))}")
    print("Trajectory: " + " -> ".join(f"{t['node']}[{t['status']}]" for t in state["trajectory"]))
    redacted = ("" if graph.tracing.backend == "none"
                else " (inputs/outputs redacted)" if graph.tracing.redact else " (redaction OFF)")
    print(f"Tracing: {graph.tracing.backend}{redacted}  |  request_id={state['request_id']}")


def main():
    ap = argparse.ArgumentParser(description="PharmGuard CLI demo.")
    ap.add_argument("drugs", nargs="+", help="Drug names (generic or brand).")
    ap.add_argument("--llm", action="store_true",
                    help="Use the configured LLM for report generation (requires API key).")
    ap.add_argument("--legacy", action="store_true",
                    help="Run the pre-LangGraph pipeline (src/pipeline.py) for comparison.")
    ap.add_argument("--simulate-retry", action="store_true",
                    help="Use a scripted SIMULATED LLM (no API key) whose first draft fails validation.")
    args = ap.parse_args()

    if args.simulate_retry and (args.legacy or args.llm):
        ap.error("--simulate-retry can't be combined with --legacy or --llm")
    try:
        (run_legacy if args.legacy else run_graph)(args)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Hint: run `python scripts/ingest_data.py --sample` first.", file=sys.stderr)
        sys.exit(1)
    except InvalidDrugNameError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
