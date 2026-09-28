"""Show FAERS signal thresholds at work: which co-reported events are surfaced, which are suppressed and why.

Queries openFDA (live; free, no key), about 5 + 3 x --events calls per pair, at least 0.3 s apart and cached
in data/cache/openfda/ (gitignored), so a rerun makes no calls. Nothing here is curated evidence: FAERS
reports are unvalidated.

    python scripts/demo_faers_signals.py                          # default pairs
    python scripts/demo_faers_signals.py simvastatin+clarithromycin warfarin+fluconazole
    python scripts/demo_faers_signals.py --offline                # hand-computed tables, no network
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.retrieval.faers_retriever import FaersRetriever, OpenFdaCounts  # noqa: E402
from src.retrieval.faers_stats import PairEventCounts, assess  # noqa: E402

DEFAULT_PAIRS = ["simvastatin+clarithromycin", "metformin+lisinopril", "warfarin+fluconazole"]
OFFLINE = [  # the hand-computed tables in tests/test_faers_stats.py
    (("drug-a", "drug-b"), "rhabdomyolysis", PairEventCounts(10_000, 1_000, 500, 100, 200, 40, 30, 20)),
    (("drug-a", "drug-b"), "nausea", PairEventCounts(10_000, 1_000, 500, 100, 400, 200, 30, 20)),
    (("drug-a", "drug-b"), "headache", PairEventCounts(10_000, 1_000, 500, 5, 2_500, 300, 200, 3)),
]
HEADER = ["| Pair | Event | Reports (a) | PRR | ROR (95% CI) | χ² (Yates) | Pair rate | Rate A without B | "
          "Rate B without A | Result |", "|---|---|---:|---:|---|---:|---:|---:|---:|---|"]


def fmt(v, d=2):
    return "—" if v is None else f"{v:.{d}f}"


def row(pair, s) -> str:
    verdict = "**surfaced**" if s.surfaced else "suppressed: " + "; ".join(s.reasons)
    return (f"| {pair[0]} + {pair[1]} | {s.event} | {s.a:,} | {fmt(s.prr)} | {fmt(s.ror)} "
            f"({fmt(s.ror_ci_low)}–{fmt(s.ror_ci_high)}) | {fmt(s.chi2, 1)} | {fmt(s.pair_rate, 4)} | "
            f"{fmt(s.rate_a_without_b, 4)} | {fmt(s.rate_b_without_a, 4)} | {verdict} |")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs", nargs="*", default=DEFAULT_PAIRS, help="drug_a+drug_b")
    ap.add_argument("--events", type=int, default=3, help="top co-reported events per pair")
    ap.add_argument("--offline", action="store_true", help="hand-computed 2x2 tables only; no network")
    ap.add_argument("--cache-dir", default=str(ROOT / "data" / "cache" / "openfda"))
    ap.add_argument("--output", help="also write the table as markdown (e.g. results/faers_signal_demo.md)")
    ap.add_argument("--timeout", type=float, default=30.0, help="seconds per openFDA call (large pairs are slow)")
    args = ap.parse_args()
    lines = list(HEADER)
    say = lines.append
    if args.offline:
        for pair, event, counts in OFFLINE:
            say(row(pair, assess(event, counts, names=pair)))
        say("\nHand-computed tables (no network). Rate = reports with the event / reports listing the drug(s).")
        return finish(lines, args, "offline, hand-computed tables")
    counts = OpenFdaCounts(cache_dir=Path(args.cache_dir), timeout_s=args.timeout)
    retriever = FaersRetriever(enabled=True, max_events=args.events, counts=counts)
    for p in args.pairs:
        a, b = (x.strip().lower() for x in p.split("+", 1))
        out = retriever.assess_pair(a, b)
        if out.error:
            say(f"| {a} + {b} | lookup failed ({out.error}) | | | | | | | | |")
        for s in out.assessed:
            say(row(out.pair, s))
        if not out.error and not out.assessed:
            say(f"| {a} + {b} | no co-reported events | | | | | | | | |")
    say(f"\nopenFDA calls made: {counts.network_calls} (the rest from the cache in data/cache/openfda). "
        "Rate = reports with the event / reports listing the drug(s). Drugs matched on "
        "patient.drug.medicinalproduct (free text as reported). Top events by co-report count, administrative "
        "MedDRA terms skipped.")
    return finish(lines, args, "live openFDA")


def finish(lines, args, source) -> int:
    import datetime
    print("\n".join(lines))
    if args.output:
        cmd = "python scripts/demo_faers_signals.py " + ("--offline" if args.offline else " ".join(args.pairs))
        head = ["# FAERS signal thresholds: surfaced vs suppressed", "",
                f"Regenerate with `{cmd}` ({source}, {datetime.date.today().isoformat()}). FAERS reports are "
                "unvalidated; a surfaced signal is a reporting pattern, not evidence that the drugs interact.",
                "Surfaced only if PRR ≥ 2, χ² ≥ 4, at least 3 reports (Evans), the ROR's lower 95% bound is above 1, "
                "and the pair's event rate is at least 2 × each drug's rate without the other.", ""]
        Path(args.output).write_text("\n".join(head + lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
