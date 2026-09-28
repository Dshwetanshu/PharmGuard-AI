# Holdout: graceful degradation (research build)

Regenerate with `python scripts/eval_holdout.py --profile research --fraction 0.1 --seed 20260928`. Offline, no API key, deterministic; RxNorm API and FAERS off.
Data: research build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1, TWOSIDES (research only; not for redistribution); 634,721 interaction records; not synthetic. provenance sha256 `73a84f12af814416c14bfccf5c8f02b0cda98081fcbfd81aa2b9f3f64e2c0ddd`.

**This is a graceful-degradation test, not a retrieval-quality test.** 10% of the build's 169,657 DDInter pairs (seed 20260928, sampled by pair) were removed from a copy of the build, and each removed pair was then checked on its own. It shows what a user sees when the curated source has a gap; it says nothing about how many real interactions DDInter lacks.

| Outcome | Pairs | Share |
|---|---:|---:|
| declared as no data | 11,534 | 68.0% |
| recovered from another source | 5,432 | 32.0% |
| a drug unresolved (declared) | 0 | 0.0% |
| input rejected by the validator | 0 | 0.0% |
| **silent (must be 0)** | 0 | 0.0% |
| total held out | 16,966 | |

By the held-out pair's DDInter grade:

| DDInter grade | declared as no data | recovered from another source | a drug unresolved (declared) | input rejected by the validator | silent (must be 0) |
|---|---:|---:|---:|---:|---:|
| Major | 2,327 | 388 | 0 | 0 | 0 |
| Moderate | 7,706 | 1,801 | 0 | 0 | 0 |
| Minor | 460 | 195 | 0 | 0 | 0 |
| not graded | 1,041 | 3,048 | 0 | 0 | 0 |

Recovered pairs by source: TWOSIDES 5,432. A recovered TWOSIDES pair shows statistical reporting signals, not a curated severity, so a held-out Major pair recovered this way is no longer reported as Major.

Held-out DDInter records that still reached a report (must be 0): 0.
