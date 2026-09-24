"""Run PharmGuard evaluation against the curated test suite.

Retrieval checks:
  1. Internal consistency: ground truth is derived from the same normalizer and
     interaction table the retriever uses, so recall/precision are 1.0 by
     construction. It only catches bugs in pair enumeration/lookup plumbing.
  2. Hand labels: retrieval scored against known_interaction_pairs in
     src/evaluation/test_cases.py (partial labels; precision is a lower bound).
Report checks (src/verification, the same checker as the runtime guardrail),
run through the LangGraph orchestration (src/graph); --legacy uses the old
pipeline instead:
  3. Template path: every case's deterministic report.
  4. LLM path: only if an API key for the configured provider is set (costs up
     to max_llm_attempts LLM calls per case). Reports first-draft semantic
     metrics, first-draft pass rate, recovery on retry, fallback rate, tokens
     per report and the most common finding codes. Without a key: "—".
The semantic checks are lexicon-based and therefore a lower bound.
Data: whatever PHARMGUARD_DATA_DIR points at (default: the synthetic sample).
The output names the build (profile, data line, sha256 of provenance.json).
Hand-label misses are split into source gaps (pair in no loaded table) and
pipeline misses (pair in a table but not retrieved).

Usage:
    python scripts/run_eval.py
    python scripts/run_eval.py --output reports/eval.json
    python scripts/run_eval.py --subset GER   # only cases whose id starts with GER
    PHARMGUARD_DATA_DIR=data/profiles/public python scripts/run_eval.py --skip-llm --output results/eval_public.json
    # research build: numbers only, no per-case pairs (TWOSIDES-derived content stays local)
    PHARMGUARD_DATA_DIR=data/profiles/research python scripts/run_eval.py --skip-llm --aggregate-only --output ...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from src.config import config
from src.data.normalizer import DrugNormalizer
from src.data.storage import read_table
from src.retrieval.interaction_retriever import InteractionRetriever
from src.retrieval.side_effect_retriever import SideEffectRetriever
from src.agents.retriever import Retriever
from src.agents.planner import Planner
from src.data.canonical import build_alias_map
from src.data.provenance import data_stamp
from src.evaluation.hand_labels import pair_sources, score_hand_labels
from src.evaluation.metrics import Evaluator
from src.evaluation.test_cases import TEST_CASES
from src.evaluation.llm_runs import summarize_llm_states
from src.graph import PharmGuardGraph, Settings
from src.pipeline import PharmGuardPipeline
from src.verification import aggregate_stats, validate_report

KEY_VARS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GOOGLE_API_KEY"}
# uncited_claim_rate is the old syntactic metric; the others are semantic.
REPORT_METRICS = ("uncited_claim_rate", "semantic_hallucination_rate", "citation_validity",
                  "pair_omission_rate", "major_omission_rate", "completeness")


def _fmt(v) -> str:
    return "—" if v is None else f"{v:.3f}"


def _llm_skip_reason(provider: str, skip: bool) -> Optional[str]:
    key_var = KEY_VARS.get(provider)
    if skip:
        return "--skip-llm"
    if not (key_var and os.getenv(key_var)):
        return f"no {key_var or 'API key'} configured"
    return None


def graph_report_checks(cases, skip_llm: bool) -> dict:
    settings = Settings.from_env(mode="deterministic")
    graph = PharmGuardGraph(settings)
    template = [graph.run(c.input_drugs)["final_validation"]["stats"] for c in cases]
    checks = {"orchestration": "langgraph", "template": aggregate_stats(template), "llm": None,
              "llm_fallback_rate": None, "llm_runs": None, "llm_model": None,
              "llm_skipped_reason": _llm_skip_reason(settings.llm_provider, skip_llm)}
    if checks["llm_skipped_reason"] is None:
        llm_graph = graph.with_mode("llm")
        runs = summarize_llm_states([llm_graph.run(c.input_drugs) for c in cases])
        checks.update(llm=runs["first_draft_checks"], llm_fallback_rate=runs["fallback_rate"], llm_runs=runs,
                      llm_model=f"{settings.llm_provider}:{settings.model_id}")
    return checks


def legacy_report_checks(cases, skip_llm: bool) -> dict:
    pipeline = PharmGuardPipeline.from_config()
    template_stats = []
    for case in cases:
        r = pipeline.run(case.input_drugs, use_llm=False)
        template_stats.append(validate_report(r.report, pipeline.evidence(r.plan, r.retrieval)).stats)
    checks = {"orchestration": "legacy", "template": aggregate_stats(template_stats), "llm": None,
              "llm_fallback_rate": None, "llm_runs": None, "llm_model": None,
              "llm_skipped_reason": _llm_skip_reason(config.llm.provider, skip_llm)}
    if checks["llm_skipped_reason"] is None:
        llm_stats, fallbacks = [], 0
        for case in cases:
            r = pipeline.run(case.input_drugs, use_llm=True)
            fallbacks += r.trace["report_source"] != "llm"
            if "llm_validation" in r.trace:
                llm_stats.append(r.trace["llm_validation"]["stats"])
        checks.update(llm=aggregate_stats(llm_stats) if llm_stats else None,
                      llm_fallback_rate=round(fallbacks / len(cases), 4),
                      llm_model=f"{config.llm.provider}:{config.llm.resolved_model()}")
    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=str, default=None, help="Path to save JSON report.")
    ap.add_argument("--subset", type=str, default=None, help="Filter case IDs by prefix.")
    ap.add_argument("--skip-llm", action="store_true", help="Don't run the LLM path even if a key is set.")
    ap.add_argument("--legacy", action="store_true", help="Use the pre-LangGraph pipeline for report checks.")
    ap.add_argument("--aggregate-only", action="store_true",
                    help="Write aggregate numbers only (no per-case pairs or findings); use for the research build.")
    args = ap.parse_args()

    normalizer = DrugNormalizer().load()
    interaction_retriever = InteractionRetriever().load()
    side_effect_retriever = SideEffectRetriever().load()
    retriever = Retriever(interaction_retriever, side_effect_retriever)

    interactions_df = read_table(config.paths.processed_dir / "interactions.parquet")

    cases = TEST_CASES
    if args.subset:
        cases = [c for c in cases if c.case_id.startswith(args.subset)]

    stamp = data_stamp(config.paths.processed_dir)
    evaluator = Evaluator(normalizer, retriever, interactions_df)
    print(f"Evaluating {len(cases)} case(s) on {stamp['data']}")
    internal = evaluator.evaluate_all(cases).as_dict()

    planner = Planner()

    def retrieve_pairs(drugs):
        plan = planner.plan(normalizer.resolve_many(drugs))
        return set(retriever.execute(plan).interactions)

    vocab = read_table(config.paths.processed_dir / "drug_vocabulary.parquet")
    hand = score_hand_labels(cases, retrieve_pairs, build_alias_map(vocab), pair_sources(interactions_df))

    checks = (legacy_report_checks if args.legacy else graph_report_checks)(cases, args.skip_llm)
    report = {"data": stamp, "internal_consistency": internal, "hand_labels": hand, "report_checks": checks}
    from src.observability import active
    active().flush()   # send any buffered trace spans before exit

    print("\n=== Internal consistency (1.0 by construction: same normalizer + table) ===")
    print(f"Mean recall:    {internal['mean_recall']}")
    print(f"Mean precision: {internal['mean_precision']}")
    print("\n=== Hand-labelled pairs (partial labels) ===")
    print(f"Recall:                  {hand['recall']}  ({hand['hits']}/{hand['labelled_pairs']} labelled pairs retrieved)")
    print(f"Precision (lower bound): {hand['precision_lower_bound']}  "
          f"({hand['hits']}/{hand['retrieved_pairs']} retrieved pairs are labelled)")
    print(f"Misses: {hand['source_gaps']} source gap(s) (pair in no loaded table), "
          f"{hand['pipeline_misses']} pipeline miss(es) (in a table, not retrieved); "
          f"pipeline recall {hand['pipeline_recall']}")
    for case_id, pair in hand["missed_source_gap"]:
        print(f"  source gap:    {case_id} {pair[0]} + {pair[1]}")
    for case_id, pair, sources in hand["missed_pipeline"]:
        print(f"  pipeline miss: {case_id} {pair[0]} + {pair[1]} (in {', '.join(sources)})")
    print("\n=== Report checks (lexicon-based: a lower bound) ===")
    tmpl, llm = checks["template"], checks["llm"] or {}
    print(f"{'metric':32s} {'template':>10s} {'llm':>10s}")
    for key in REPORT_METRICS:
        print(f"{key:32s} {_fmt(tmpl.get(key)):>10s} {_fmt(llm.get(key)):>10s}")
    print(f"{'llm_fallback_rate':32s} {'':>10s} {_fmt(checks['llm_fallback_rate']):>10s}")
    runs = checks.get("llm_runs") or {}
    for key in ("first_draft_pass_rate", "recovery_on_retry", "tokens_per_report"):
        print(f"{key:32s} {'':>10s} {_fmt(runs.get(key)):>10s}")
    print(f"{'top_finding_codes':32s} {'':>10s} {runs.get('top_finding_codes') or '—'}")
    print(f"orchestration: {checks['orchestration']}")
    if checks["llm_skipped_reason"]:
        print(f"LLM path not run: {checks['llm_skipped_reason']}")
    print(f"Cases evaluated: {internal['num_cases']}")

    if args.aggregate_only:
        report["hand_labels"] = {k: v for k, v in hand.items() if not isinstance(v, list)}
        report["internal_consistency"] = {k: v for k, v in internal.items() if not isinstance(v, (list, dict))}
        report["aggregate_only"] = True
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2))
        print(f"\nFull report saved to {out}")


if __name__ == "__main__":
    main()
