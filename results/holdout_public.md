# Holdout: graceful degradation (public build)

Regenerate with `python scripts/eval_holdout.py --profile public --fraction 0.1 --seed 20260928`. Offline, no API key, deterministic; RxNorm API and FAERS off.
Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic. provenance sha256 `fc037dc5f67b9c0dd05c4664e48a4888a155d285dc0e1a11369fc971dab31073`.

**This is a graceful-degradation test, not a retrieval-quality test.** 10% of the build's 169,657 DDInter pairs (seed 20260928, sampled by pair) were removed from a copy of the build, and each removed pair was then checked on its own. It shows what a user sees when the curated source has a gap; it says nothing about how many real interactions DDInter lacks.

| Outcome | Pairs | Share |
|---|---:|---:|
| declared as no data | 16,966 | 100.0% |
| recovered from another source | 0 | 0.0% |
| a drug unresolved (declared) | 0 | 0.0% |
| input rejected by the validator | 0 | 0.0% |
| **silent (must be 0)** | 0 | 0.0% |
| total held out | 16,966 | |

By the held-out pair's DDInter grade:

| DDInter grade | declared as no data | recovered from another source | a drug unresolved (declared) | input rejected by the validator | silent (must be 0) |
|---|---:|---:|---:|---:|---:|
| Major | 2,715 | 0 | 0 | 0 | 0 |
| Moderate | 9,507 | 0 | 0 | 0 | 0 |
| Minor | 655 | 0 | 0 | 0 | 0 |
| not graded | 4,089 | 0 | 0 | 0 | 0 |

Held-out DDInter records that still reached a report (must be 0): 0.
