"""Run the LLM judge on the checker's injected faults; writes results/judge_faults_sample.{json,md}.

    python scripts/judge_checker_faults.py --plan                     # no calls: the claims and the call count
    python scripts/judge_checker_faults.py --provider gemini --model gemini-3.5-flash-lite --min-interval 5

Synthetic only: the FX- fixture records of src/evaluation/checker_fixtures.py (no real data is sent).
- Known-bad claims: for each injected fault, the cited claims that differ from the clean report AND sit on
  a line where the checker raises the fault's expected code (for a severity flip, the flipped grade must
  appear in the claim's text). The fault is known by construction; the
  checker only locates its line, so claims merely reworded by a re-render (prose style) aren't counted.
  Faults with no such claim (omissions, a line moved under another heading, dropped counts) can't be
  shown to a per-claim judge and are listed as not judgeable.
- Blind-spot probes: the fabrications the lexicon checker is known to miss.
- Control: every claim of the clean fixture reports; the judge should call these supported.
A claim citing only records that aren't in the evidence is rated unsupported without a call (ClaimJudge).
Responses are cached in data/cache/llm/ (gitignored), so a run stopped by a quota resumes.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.checker_fixtures import BLIND_SPOTS, FAULTS, SCENARIOS, STYLES, evidence_for, render  # noqa: E402
from src.evaluation.judge import ClaimJudge, extract_claims, prompt_info  # noqa: E402
from src.verification import validate_report  # noqa: E402

BAD = ("unsupported", "contradicted")


def _key(c):
    return c.text, tuple(c.citations)


def _line(c) -> int:
    return int(c.claim_id.rsplit(":L", 1)[1])


def visible(name: str, site: str, c) -> bool:
    """Whether the fault shows in the claim's own text. A severity flip in prose moves the line under another
    heading but leaves the sentence true; the judge sees one claim, not its heading."""
    if name == "severity_flip":
        return site.rsplit("->", 1)[1] in c.text
    return True


def fault_claims():
    """(group, name, style, site, claim) for every known-bad, blind-spot and control claim; plus not-judgeable faults."""
    items, not_judgeable = [], Counter()
    for style in STYLES:
        for s in SCENARIOS:
            ev = evidence_for(s)
            clean = extract_claims(render(s, style=style), ev, f"{style}/{s.name}/clean")
            items += [("control", "clean fixture claim", style, s.name, c) for c in clean]
            seen = {_key(c) for c in clean}
            for name, (inject, code) in FAULTS.items():
                for n, (site, report) in enumerate(inject(s, style)):
                    lines = {f.line for f in validate_report(report, ev).findings if f.code == code}
                    bad = [c for c in extract_claims(report, ev, f"{style}/{s.name}/{name}/{n}")
                           if _key(c) not in seen and _line(c) in lines and visible(name, site, c)]
                    items += [("fault", name, style, site, c) for c in bad]
                    not_judgeable[name] += not bad
        s = SCENARIOS[0]
        ev = evidence_for(s)
        seen = {_key(c) for c in extract_claims(render(s, style=style), ev, "clean")}
        for name, (make, _) in BLIND_SPOTS.items():
            items += [("blind_spot", name, style, s.name, c)
                      for c in extract_claims(make(style), ev, f"{style}/blind/{name}") if _key(c) not in seen]
    return items, {k: v for k, v in not_judgeable.items() if v}


def needs_call(c) -> bool:
    return not (c.missing_citations and not c.records)


def run(judge, items):
    rows = []
    for group, name, style, site, c in items:
        j = judge.judge(c)
        rows.append({"group": group, "name": name, "style": style, "site": site, "claim": c.text,
                     "citations": c.citations, "verdict": j.verdict, "called_judge": j.called_judge,
                     "rationale": j.rationale})
    return rows


def summarize(rows):
    def tally(rs):
        v = Counter(r["verdict"] for r in rs)
        return {"claims": len(rs), "supported": v["supported"], "unsupported": v["unsupported"],
                "contradicted": v["contradicted"], "invalid": v["invalid"]}
    out = {}
    for group in ("fault", "blind_spot", "control"):
        rs = [r for r in rows if r["group"] == group]
        called = [r for r in rs if r["called_judge"]]
        out[group] = {"all": tally(rs), "llm_judged": tally(called),
                      "by_name": {n: tally([r for r in called if r["name"] == n])
                                  for n in dict.fromkeys(r["name"] for r in rs)},
                      "rated_without_call": len(rs) - len(called)}
    return out


def to_markdown(r: dict) -> str:
    s = r["summary"]
    pct = lambda a, b: f"{a}/{b} ({a / b:.1%})" if b else "—"
    caught = lambda t: t["unsupported"] + t["contradicted"]
    f, b, c = s["fault"]["llm_judged"], s["blind_spot"]["llm_judged"], s["control"]["llm_judged"]
    L = ["# LLM judge on the checker's injected faults (synthetic fixtures)", "",
         f"Regenerate with `{r['command']}` ({r['run_on']}). Judge `{r['judge']}`, prompt `{r['judge_prompt']['file']}` "
         f"sha256 `{r['judge_prompt']['sha256']}`. Data: the synthetic FX- fixture records of "
         "`src/evaluation/checker_fixtures.py`; no real data. No generator is involved: the reports are fixture "
         "templates with faults injected by code.", "",
         "**Known-bad claims** are the cited claims an injected fault changed, located on the line where the checker "
         "raises that fault's code (the fault is known by construction; the checker only locates it). The judge sees "
         "one claim and its cited records, nothing else. These faults use the checker's own lexicon terms, so this "
         "is a sanity check on synthetic data, not an estimate of how many real LLM errors the judge catches.", "",
         f"- **Known-bad claims rated unsupported or contradicted: {pct(caught(f), f['claims'])}** "
         f"(unsupported {f['unsupported']}, contradicted {f['contradicted']}, supported {f['supported']}, "
         f"invalid output {f['invalid']}).",
         f"- Plus {s['fault']['rated_without_call']} phantom-citation claims rated unsupported without a call "
         "(they cite no record in the evidence).",
         f"- Blind-spot probes (missed by the lexicon checker) rated unsupported or contradicted: "
         f"{pct(caught(b), b['claims'])}.",
         f"- Control, clean fixture claims rated supported: {pct(c['supported'], c['claims'])}.",
         f"- Judge prompts: {r['calls']} ({r.get('cache_hits', 0)} answered from the response cache of an earlier "
         f"run of this script); tokens: {r['usage'] or '—'}.", "",
         "| Fault | Known-bad claims judged | Unsupported | Contradicted | Supported (missed) | Invalid |",
         "|---|---:|---:|---:|---:|---:|"]
    for group in ("fault", "blind_spot"):
        for n, t in s[group]["by_name"].items():
            if t["claims"]:
                label = n if group == "fault" else f"blind spot: {n}"
                L.append(f"| {label} | {t['claims']} | {t['unsupported']} | {t['contradicted']} | {t['supported']} | {t['invalid']} |")
    L += ["", "Not judgeable per claim (no changed cited claim to show the judge), injections: "
          + (", ".join(f"{k} {v}" for k, v in r["not_judgeable"].items()) or "none") + ".", ""]
    missed = [x for x in r["rows"] if x["group"] != "control" and x["verdict"] == "supported"]
    wrong = [x for x in r["rows"] if x["group"] == "control" and x["verdict"] != "supported"]
    for title, xs in (("Known-bad claims the judge called supported", missed),
                      ("Clean claims the judge did not call supported", wrong)):
        L += [f"## {title} ({len(xs)})", ""]
        L += [f"- `{x['name']}` ({x['style']}, {x['site']}): {x['claim']} → **{x['verdict']}**: {x['rationale']}" for x in xs]
        L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="gemini")
    ap.add_argument("--model", default=None)
    ap.add_argument("--min-interval", type=float, default=0.0, help="seconds between LLM calls")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--plan", action="store_true", help="make no calls; print the claims and the call count")
    ap.add_argument("--output-dir", default=str(ROOT / "results"))
    args = ap.parse_args()
    items, not_judgeable = fault_claims()
    counts = Counter((g, needs_call(c)) for g, _, _, _, c in items)
    distinct = len({(c.text, json.dumps(c.records, sort_keys=True, default=str)) for *_, c in items if needs_call(c)})
    print(f"known-bad claims {counts['fault', True] + counts['fault', False]} ({counts['fault', False]} rated without a "
          f"call), blind-spot probes {counts['blind_spot', True]}, control claims {counts['control', True]}; "
          f"judge calls ≤ {sum(v for (g, call), v in counts.items() if call)} ({distinct} distinct prompts). "
          f"Not judgeable: {not_judgeable}")
    if args.plan:
        return 0

    from dotenv import load_dotenv
    load_dotenv()
    from run_llm_eval import llm_client
    from src.config import DEFAULT_MODELS
    model = args.model or DEFAULT_MODELS[args.provider]
    judge = ClaimJudge(llm_client(args.provider, model, args.min_interval, not args.no_cache))
    rows = run(judge, items)
    cache_hits = getattr(judge.llm, "hits", 0)
    cmd = f"python scripts/judge_checker_faults.py --provider {args.provider} --model {model}"
    r = {"command": cmd + (f" --min-interval {args.min_interval:g}" if args.min_interval else ""),
         "run_on": datetime.date.today().isoformat(), "judge": f"{args.provider}:{model}",
         "judge_prompt": prompt_info(), "calls": judge.calls, "cache_hits": cache_hits, "usage": dict(judge.usage),
         "not_judgeable": not_judgeable, "summary": summarize(rows), "rows": rows}
    out = Path(args.output_dir)
    (out / "judge_faults_sample.json").write_text(json.dumps(r, indent=2) + "\n")
    (out / "judge_faults_sample.md").write_text(to_markdown(r))
    print(to_markdown(r).split("| Fault |")[0])
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.exit(main())
