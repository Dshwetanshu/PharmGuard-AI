"""Trajectory evaluation of the PharmGuard graph; writes results/trajectory.{json,md}.

Usage:
    python scripts/eval_trajectory.py                                   # step scoring only
    python scripts/eval_trajectory.py --fault-suite                     # + scripted fake-LLM fault suite
    python scripts/eval_trajectory.py --fault-suite --seeded-bugs --min-invariant-pass 1.0   # CI gate

    python scripts/eval_trajectory.py --fault-suite --profile public    # on a real build -> results/trajectory_public.*

Offline, no API keys: the sample data is ingested into a temp dir (or a real
build is read from data/profiles/<profile>), RxNorm and FAERS are off (FAERS is
a counting stub in the FAERS pass), and every LLM is a scripted fake. Exit
status 1 if any invariant's pass rate is below --min-invariant-pass, or (with
--seeded-bugs) if a seeded bug breaks no invariant. Labelled pairs that no
loaded table contains are reported as source gaps, not retrieval failures.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import Config  # noqa: E402
from src.data.ingestion import Ingester  # noqa: E402
from src.data.provenance import data_stamp  # noqa: E402
from src.data.storage import read_table  # noqa: E402
from src.evaluation import trajectory as T  # noqa: E402
from src.evaluation.seeded_bugs import SEEDED_BUGS  # noqa: E402
from src.evaluation.test_cases import SUSPECTED_LABEL_ERRORS, TEST_CASES  # noqa: E402
from src.graph import Settings, build_components  # noqa: E402

COMMAND = "python scripts/eval_trajectory.py --fault-suite --seeded-bugs --min-invariant-pass 1.0"


def build_harness(data_dir: Path, profile: str = "sample") -> T.Harness:
    cfg = Config()
    cfg.paths.data_dir = data_dir
    if profile == "sample":
        shutil.copytree(ROOT / "data" / "sample", data_dir / "sample")
        Ingester(cfg).ingest_sample()
    settings = Settings(data_dir=data_dir, mode="deterministic", rxnorm_enabled=False, faers_enabled=False)
    components = build_components(settings)
    return T.Harness.build(settings, components, read_table(cfg.paths.processed_dir / "drug_vocabulary.parquet"),
                           profile=profile)


def _f(v, pct=True):
    return "—" if v is None else (f"{v:.1%}" if pct else f"{v}")


def to_markdown(res: dict) -> str:
    stamp = res["data"]
    what = ("synthetic sample data" if stamp["profile"] == "sample"
            else f"the real **{stamp['profile']}** build ({stamp['data']}; provenance sha256 "
                 f"`{stamp['provenance_sha256']}`)")
    L = ["# Trajectory evaluation" + ("" if stamp["profile"] == "sample" else f" ({stamp['profile']} build)"), "",
         f"Regenerate with `{res['command']}`. Offline, no API keys, {what}, 48 cases. "
         "LLM mode with a real model: **—** (no API key); LLM behaviour is exercised with scripted fake LLMs.", ""]
    for name, block in res["step_scoring"].items():
        if block is None:
            L += [f"## Step scoring: {name}", "", "— (no API key configured)", ""]
            continue
        sm = block["summary"]
        L += [f"## Step scoring: {name}", "",
              "| Subset | Cases | normalize | plan | retrieve | route | finalize | **completion** |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
        rows = [("**all**", sm["overall"])] + list(sm["per_subset"].items())
        for sub, a in rows:
            L.append(f"| {sub} | {a['cases']} | " + " | ".join(_f(a[s]) for s in T.STEPS)
                     + f" | **{_f(a['completion'])}** |")
        L += ["", "Failing cases: " + (", ".join(f"{f['case_id']} ({'/'.join(f['failed_steps'])}: {f['reasons']})"
                                                for f in sm["failing"]) or "none"),
              "", "Suspected label errors, counted separately (not failures): "
              + (", ".join(f"{k} {v}" for k, v in sm["suspected_label_misses"].items()) or "none"),
              "", "Source gaps (labelled pair in no loaded table; not retrieval failures): "
              + (", ".join(f"{k} {v}" for k, v in sm.get("source_gap_misses", {}).items()) or "none"), ""]
    L += ["## Normalizer expectations added (for review)", "", "| Case | Input | Expected |", "|---|---|---|"]
    for c in TEST_CASES:
        for q, g in c.expected_resolved.items():
            L.append(f"| {c.case_id} | `{q}` | resolves to `{g}` |")
        for q in c.expected_unresolved:
            L.append(f"| {c.case_id} | `{q}` | stays unresolved |")
        for prof, over in c.expected_by_profile.items():
            for q, g in over.items():
                L.append(f"| {c.case_id} | `{q}` | {prof} profile: "
                         + (f"resolves to `{g}` |" if g else "stays unresolved |"))
    L += ["", "All other inputs are expected to resolve. Suspected label errors (unchanged, for review): "
          + ", ".join(f"{k} {v}" for k, v in SUSPECTED_LABEL_ERRORS.items()), ""]

    fs = res.get("fault_suite")
    if fs:
        s = fs["summary"]
        L += ["## Fault suite (scripted fake LLMs)", "",
              f"{s['runs']} runs over 48 cases; scenarios skipped where the fault doesn't apply: {fs['skipped']}.", "",
              "| Scenario | Runs | Expected report_source | Path match | Source match | All invariants | LLM calls/run |",
              "|---|---:|---|---:|---:|---:|---:|"]
        for name, p in s["per_scenario"].items():
            L.append(f"| {name} | {p['runs']} | {p['expected_source']} | {_f(p['path_match'])} | "
                     f"{_f(p['source_match'])} | {_f(p['invariants_all_pass'])} | {p['llm_calls_mean']} |")
        L += ["", f"Path match {_f(s['path_match_rate'])} · report_source match {_f(s['source_match_rate'])} · "
                  f"recovery within the retry budget {_f(s['recovery_rate'])} · LLM calls per case "
                  f"{s['llm_calls_per_case']}", ""]
    inv = res["invariants"]
    L += [f"## Invariants ({inv['runs']} runs: step scoring{' + fault suite' if fs else ''})", "",
          "| Invariant | Pass rate |", "|---|---:|"]
    L += [f"| {k} | {_f(v)} |" for k, v in inv["pass_rate"].items()]
    if fs:
        s = fs["summary"]
        L += ["", f"## Latency: {s['latency_label']}", "", "| Node | p50 ms | p95 ms |", "|---|---:|---:|"]
        L += [f"| {n} | {v['p50']} | {v['p95']} |" for n, v in s["latency_ms_per_node"].items()]
        L.append(f"| **end to end** | {s['latency_ms_end_to_end']['p50']} | {s['latency_ms_end_to_end']['p95']} |")
    sb = res.get("seeded_bugs")
    if sb:
        L += ["", "## Seeded orchestration bugs (validating the evaluation)", "",
              "| Seeded bug | Caught | Invariants broken (pass rate under the bug) | Path match |", "|---|---|---|---:|"]
        for name, b in sb.items():
            broken = ", ".join(f"`{k}` ({_f(v)})" for k, v in b["broken"].items()) or "none"
            L.append(f"| {name} | {'yes' if b['caught'] else '**NO**'} | {broken} | {_f(b['path_match'])} |")
    L += ["", f"Gate: min invariant pass rate {_f(res['gate']['min_invariant_pass'])} (threshold "
              f"{_f(res['gate']['threshold'])}) → **{'PASS' if res['gate']['passed'] else 'FAIL'}**", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fault-suite", action="store_true", help="Run the scripted fake-LLM fault suite.")
    ap.add_argument("--seeded-bugs", action="store_true", help="Also check each seeded bug breaks an invariant.")
    ap.add_argument("--min-invariant-pass", type=float, default=1.0, help="Gate threshold (0-1).")
    ap.add_argument("--profile", choices=["sample", "public", "research"], default="sample",
                    help="sample (default, CI) or a real build in data/profiles/<profile>.")
    ap.add_argument("--output-dir", default=str(ROOT / "results"))
    args = ap.parse_args()
    command = COMMAND if args.profile == "sample" else (
        "python scripts/eval_trajectory.py" + (" --fault-suite" if args.fault_suite else "")
        + (" --seeded-bugs" if args.seeded_bugs else "") + f" --profile {args.profile}")
    suffix = "" if args.profile == "sample" else f"_{args.profile}"

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "data" if args.profile == "sample" else ROOT / "data" / "profiles" / args.profile
        h = build_harness(data_dir, args.profile)
        stamp = data_stamp(h.settings.to_config().paths.processed_dir)
        if args.profile != "sample":
            stamp["data_dir"] = f"data/profiles/{args.profile}"
        a = T.run_step_scoring(h)
        res = {"command": command, "data": stamp,
               "step_scoring": {k: (None if v is None else {"summary": v["summary"]})
                                for k, v in a["step_scoring"].items()}}
        invariant_rows = [{k: v[0] for k, v in x.items()} for x in a["invariant_runs"]]
        if args.fault_suite:
            b = T.run_fault_suite(h)
            summary = T.summarize_faults(b["runs"])
            # Per-run details stay out of the file (it would be ~1 MB); mismatches are in the summary.
            res["fault_suite"] = {"summary": summary, "skipped": b["skipped"]}
            invariant_rows += [r["invariants"] for r in b["runs"]]
        if args.seeded_bugs:
            res["seeded_bugs"] = {}
            for name, bug in SEEDED_BUGS.items():
                with bug():
                    s = T.summarize_faults(T.run_fault_suite(h)["runs"])
                broken = {k: v for k, v in s["invariant_pass_rate"].items() if v < 1.0}
                res["seeded_bugs"][name] = {"caught": bool(broken), "broken": broken, "path_match": s["path_match_rate"]}

    pass_rate = {k: round(sum(r[k] for r in invariant_rows) / len(invariant_rows), 4) for k in T.INVARIANTS}
    res["invariants"] = {"runs": len(invariant_rows), "pass_rate": pass_rate}
    min_pass = min(pass_rate.values())
    bugs_ok = all(b["caught"] for b in res.get("seeded_bugs", {}).values())
    res["gate"] = {"min_invariant_pass": min_pass, "threshold": args.min_invariant_pass,
                   "seeded_bugs_all_caught": bugs_ok if args.seeded_bugs else None,
                   "passed": min_pass >= args.min_invariant_pass and bugs_ok}

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"trajectory{suffix}.json").write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    (out / f"trajectory{suffix}.md").write_text(to_markdown(res))
    det = res["step_scoring"]["deterministic"]["summary"]["overall"]
    print(f"Step scoring (deterministic): completion {det['completion']:.1%} over {det['cases']} cases")
    if args.fault_suite:
        s = res["fault_suite"]["summary"]
        print(f"Fault suite: {s['runs']} runs, path match {s['path_match_rate']:.1%}, recovery {s['recovery_rate']:.1%}")
    print(f"Invariants: min pass rate {min_pass:.1%} over {len(invariant_rows)} runs")
    if args.seeded_bugs:
        print("Seeded bugs caught: " + ", ".join(f"{k}={'yes' if v['caught'] else 'NO'}"
                                                 for k, v in res["seeded_bugs"].items()))
    print(f"Wrote {out / f'trajectory{suffix}.json'} and {out / f'trajectory{suffix}.md'}")
    print("GATE PASS" if res["gate"]["passed"] else "GATE FAIL")
    return 0 if res["gate"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
