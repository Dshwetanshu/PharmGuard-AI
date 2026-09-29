"""All real-model numbers in one command; writes results/llm_eval_<profile>.{json,md}.

For each generation provider with a key: first-draft pass rate, recovery on retry,
fallback rate, tokens per report, top finding codes, checker metrics, judge
faithfulness, and the deterministic-vs-LLM comparison. Also a blind CSV of 20% of
the judged claims for a human audit (results/judge_audit_<profile>.csv; the key
with the judge's verdicts goes to data/cache/, gitignored).

    python scripts/run_llm_eval.py --plan                       # no calls: what would run, and the call budget
    python scripts/run_llm_eval.py --providers gemini --judge-provider anthropic
    python scripts/run_llm_eval.py --providers gemini --judge-provider gemini --allow-same-provider-judge \\
        --min-interval 6                                        # one provider: disclosed as same-provider
    python scripts/score_judge_audit.py                         # after a human fills the audit CSV

Keys come from the environment or .env (ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY); this
script never prints them. Models: PHARMGUARD_LLM_MODEL applies to every generator unless
--model is given; --judge-model sets the judge's. The research build is refused: TWOSIDES-derived
evidence is not sent to a third-party model.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agents.generator import Generator  # noqa: E402
from src.config import Config, DEFAULT_MODELS  # noqa: E402
from src.data.ingestion import Ingester  # noqa: E402
from src.data.provenance import data_stamp  # noqa: E402
from src.evaluation.judge import ClaimJudge, check_providers, export_blind, extract_claims, prompt_info  # noqa: E402
from src.evaluation.llm_eval import CachedLLM, Throttled, call_budget, evaluate_provider  # noqa: E402
from src.evaluation.test_cases import TEST_CASES  # noqa: E402
from src.graph import PharmGuardGraph, Settings, build_components  # noqa: E402
from src.graph.settings import KEY_VARS  # noqa: E402
from src.llm import LLMClient  # noqa: E402
from src.verification import Evidence  # noqa: E402

METRICS = ("semantic_hallucination_rate", "uncited_claim_rate", "citation_validity", "pair_omission_rate",
           "major_omission_rate", "completeness")


def fmt(v, pct=False):
    if v is None:
        return "—"
    return f"{v:.1%}" if pct else (f"{v:.3f}" if isinstance(v, float) else str(v))


def data_dir_for(profile: str, tmp: Path) -> Path:
    if profile == "sample":
        cfg = Config()
        cfg.paths.data_dir = tmp / "data"
        shutil.copytree(ROOT / "data" / "sample", cfg.paths.data_dir / "sample")
        Ingester(cfg).ingest_sample()
        return cfg.paths.data_dir
    d = ROOT / "data" / "profiles" / profile
    if not (d / "processed" / "provenance.json").exists():
        sys.exit(f"no {profile} build at {d}")
    return d


def llm_client(provider: str, model: str, min_interval: float, cache: bool):
    cfg = Config()
    cfg.llm.provider, cfg.llm.model = provider, model
    client = Throttled(LLMClient(cfg), min_interval)
    return CachedLLM(client, f"{provider}:{model}", ROOT / "data" / "cache" / "llm") if cache else client


def to_markdown(r: dict) -> str:
    d = r["data"]
    L = ["# LLM-path evaluation" + (" (SIMULATED LLM)" if r.get("simulated") else ""), "",
         f"Regenerate with `{r['command']}` ({r['date']}). {d['data']} provenance sha256 `{d['provenance_sha256']}`.",
         f"Judge prompt `{r['judge_prompt']['file']}` sha256 `{r['judge_prompt']['sha256']}`.", ""]
    if r.get("simulated"):
        L += ["**Every LLM in this run is a scripted fake.** These numbers test the harness, not a model.", ""]
    for p in r["providers"]:
        runs, ch = p["llm_runs"], p["checks"]
        j = p.get("judge") or {}
        disc = p.get("judge_disclosure") or {}
        L += [f"## Generator {p['model']}", "",
              f"{p['cases']} cases; LLM reports shown: {p['llm_reports_shown']}. Judge: "
              + (f"{disc.get('judge_provider')}:{r.get('judge_model')}"
                 + (" — **same provider as the generator** (allowed by flag; agreement may be inflated)"
                    if disc.get("same_provider") else " (a different provider)") if j else "not run") + ".", "",
              "| Metric | Deterministic template | LLM first draft | LLM report shown |", "|---|---:|---:|---:|"]
        for m in METRICS:
            L.append(f"| {m} | {fmt((ch['template'] or {}).get(m))} | {fmt((ch['llm_first_draft'] or {}).get(m))} | "
                     f"{fmt((ch['llm_shown'] or {}).get(m))} |")
        j = {**j, "template": j.get("template") or {}}
        L.append(f"| faithfulness (judge: supported / judged) | {fmt((j.get('template') or {}).get('faithfulness'))} | — | "
                 f"{fmt((j.get('llm_shown') or {}).get('faithfulness'))} |")
        L.append(f"| contradicted rate (judge) | {fmt((j.get('template') or {}).get('contradicted_rate'))} | — | "
                 f"{fmt((j.get('llm_shown') or {}).get('contradicted_rate'))} |")
        lat = p["latency_ms_p50"]
        L.append(f"| graph latency p50, in-process (ms) | {fmt(lat['deterministic'])} | | {fmt(lat['llm_mode'])} |")
        L += ["", "| LLM runs | |", "|---|---|",
              f"| first-draft pass rate | {fmt(runs['first_draft_pass_rate'], True)} |",
              f"| recovery on retry | {fmt(runs['recovery_on_retry'], True)} |",
              f"| fallback rate | {fmt(runs['fallback_rate'], True)} |",
              f"| tokens per report | {fmt(runs['tokens_per_report'])} |",
              f"| top finding codes | {runs['top_finding_codes'] or '—'} |",
              f"| report sources | {runs['report_sources']} |",
              f"| LLM errors | {runs['llm_errors'] or '—'} |"]
        if j:
            L += [f"| judge calls / invalid judge outputs | {j['calls']} / "
                  f"{(j['llm_shown'] or {}).get('invalid_judge_output', 0) + (j['template'] or {}).get('invalid_judge_output', 0)} |",
                  f"| judge tokens | {j.get('usage') or '—'} |"]
        L.append("")
    a = r.get("audit")
    L += ["## Human audit of the judge", "",
          (f"{a['rows']} judged claims ({a['fraction']:.0%}, seed {a['seed']}) exported blind to `{a['csv']}`. "
           "Agreement and Cohen's κ: — until a human fills it in (`python scripts/score_judge_audit.py`).")
          if a else "Not exported.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["sample", "public"], default="public")
    ap.add_argument("--providers", default=None, help="comma list of generators (default: every provider with a key)")
    ap.add_argument("--model", default=None, help="generator model (default: PHARMGUARD_LLM_MODEL or the provider default)")
    ap.add_argument("--judge-provider", default=None)
    ap.add_argument("--judge-model", default=None)
    ap.add_argument("--allow-same-provider-judge", action="store_true")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--no-template-judge", action="store_true",
                    help="judge only the LLM reports (saves about half the judge calls)")
    ap.add_argument("--no-cache", action="store_true", help="don't reuse or store responses in data/cache/llm/")
    ap.add_argument("--min-interval", type=float, default=0.0, help="seconds between LLM calls, per client")
    ap.add_argument("--subset", default=None, help="case-id prefix")
    ap.add_argument("--max-cases", type=int, default=None)
    ap.add_argument("--audit-fraction", type=float, default=0.2)
    ap.add_argument("--plan", action="store_true", help="make no calls; print what would run and the call budget")
    ap.add_argument("--output-dir", default=str(ROOT / "results"))
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv()
    cases = [c for c in TEST_CASES if not args.subset or c.case_id.startswith(args.subset)][: args.max_cases]
    keyed = [p for p, k in KEY_VARS.items() if os.getenv(k)]
    providers = args.providers.split(",") if args.providers else keyed
    judge_provider = args.judge_provider
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = data_dir_for(args.profile, Path(tmp))
        base = Settings(data_dir=data_dir, mode="deterministic", rxnorm_enabled=False, faers_enabled=False)
        comps = build_components(base)
        det = PharmGuardGraph(base, comps)
        if args.plan:
            claims = 0
            for c in cases:
                try:
                    s = det.run(c.input_drugs)
                except ValueError:
                    continue
                claims += len(extract_claims(s["report"], Evidence.from_dict(s["evidence"]), c.case_id))
            b = call_budget(claims, len(cases), base.max_llm_attempts, judge_template=not args.no_template_judge)
            print(f"{len(cases)} cases on the {args.profile} build; template reports have {claims} cited claims.")
            print(f"Per generation provider: {b['generation_calls_min']}-{b['generation_calls_max']} generation calls; "
                  f"judge calls ≈ {0 if args.no_judge else b['judge_calls_est']} "
                  f"({'LLM reports only' if args.no_template_judge else 'LLM reports + template reports'}); "
                  f"at most ≈ {b['generation_calls_max'] + (0 if args.no_judge else b['judge_calls_est'])} calls.")
            print(f"Keys present for: {', '.join(keyed) or 'none'}. Generators requested: {', '.join(providers) or 'none'}. "
                  f"Judge: {judge_provider or 'none'}.")
            return 0
        missing = [p for p in providers + ([judge_provider] if judge_provider else []) if not os.getenv(KEY_VARS.get(p, "-"))]
        if not providers or missing:
            print(f"Not run: no API key for {', '.join(missing) or 'any provider'}. Every LLM-path number stays '—'.")
            return 2
        if not args.no_judge and not judge_provider:
            sys.exit("--judge-provider is required (or --no-judge)")
        judge_model = args.judge_model or DEFAULT_MODELS.get(judge_provider or "", "")
        out = {"command": "python " + " ".join(sys.argv), "date": datetime.date.today().isoformat(),
               "data": data_stamp(data_dir / "processed"), "judge_prompt": prompt_info(), "judge_model": judge_model,
               "providers": []}
        claims, judgements = [], []
        for p in providers:
            model = args.model or os.getenv("PHARMGUARD_LLM_MODEL") or DEFAULT_MODELS[p]
            disclosure = None if args.no_judge else check_providers(p, judge_provider, args.allow_same_provider_judge)
            gen_llm = llm_client(p, model, args.min_interval, not args.no_cache)
            s = replace(base, mode="llm", llm_provider=p, llm_model=model, llm_configured=True)
            c = replace(comps, generator=Generator(s.to_config(), llm=gen_llm, provenance=comps.generator.provenance),
                        llm_available=True, llm_label=f"{p}:{model}")
            judge = None if args.no_judge else ClaimJudge(llm_client(judge_provider, judge_model, args.min_interval,
                                                                     not args.no_cache))
            res = evaluate_provider(det, PharmGuardGraph(s, c), cases, judge, p, f"{p}:{model}",
                                    judge_template=not args.no_template_judge)
            res["judge_disclosure"] = disclosure
            res["generation_calls"] = getattr(gen_llm, "misses", None) or getattr(gen_llm, "calls", None)
            claims += res.pop("_claims", [])
            judgements += res.pop("_judgements", [])
            out["providers"].append(res)
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    if judgements:
        csv_path = outdir / f"judge_audit_{args.profile}.csv"
        key_path = ROOT / "data" / "cache" / f"judge_audit_key_{args.profile}.json"
        n = export_blind(claims, judgements, csv_path, key_path, fraction=args.audit_fraction)
        out["audit"] = {"rows": n, "fraction": args.audit_fraction, "seed": 20260928,
                        "csv": str(csv_path.relative_to(ROOT)) if csv_path.is_relative_to(ROOT) else str(csv_path),
                        "key": "data/cache (not committed)"}
    (outdir / f"llm_eval_{args.profile}.json").write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n")
    (outdir / f"llm_eval_{args.profile}.md").write_text(to_markdown(out))
    print(to_markdown(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
