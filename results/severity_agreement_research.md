# Severity agreement: TWOSIDES PRR tiers vs DDInter grades (research build)

Regenerate with `python scripts/eval_severity_agreement.py`. Offline, no API key. Aggregate numbers only.
Data: research build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1, TWOSIDES (research only; not for redistribution); 634,721 interaction records; not synthetic. provenance sha256 `73a84f12af814416c14bfccf5c8f02b0cda98081fcbfd81aa2b9f3f64e2c0ddd`.

**What is compared.** For each pair that has both a DDInter record and a TWOSIDES signal, the DDInter grade (Minor < Moderate < Major) against a tier from the pair's PRR, the highest PRR among its kept TWOSIDES events (TWOSIDES filters: PRR ≥ 2, ≥ 5 co-reports, top 5 events per pair). Pairs DDInter lists without a grade are left out. PharmGuard never shows these tiers: reports give TWOSIDES signals without severity words. This asks whether a PRR could stand in for a curated grade.

Pairs: DDInter 169,657; TWOSIDES 115,995; in both 54,097 (23,549 graded by DDInter, 30,548 not graded).
Split: seeded 50/50 by pair (seed 20260928): calibration 11,774, test 11,775. Tuned thresholds were chosen on the calibration half only (linear-weighted kappa on the calibration half, over 31 calibration-half PRR quantiles).

## Test half

| Thresholds | Pairs | Accuracy | Macro-F1 | Linear-weighted κ | Spearman (tier) | Spearman (PRR) |
|---|---:|---:|---:|---:|---:|---:|
| current: Moderate ≥ 4, Major ≥ 10 | 11,775 | 0.198 | 0.130 | 0.002 | 0.005 | 0.032 |
| tuned on calibration: Moderate ≥ 8.57, Major ≥ 100 | 11,775 | 0.611 | 0.340 | 0.019 | 0.014 | 0.032 |
| baseline: always Moderate (calibration majority) | 11,775 | 0.757 | 0.287 | 0.000 | — | 0.032 |

DDInter grades in the test half: Minor 850, Moderate 8,913, Major 2,012.

Current thresholds, test half (rows: DDInter grade; columns: PRR tier)

| DDInter \ PRR tier | Minor | Moderate | Major |
|---|---:|---:|---:|
| Minor | 7 | 33 | 810 |
| Moderate | 56 | 400 | 8,457 |
| Major | 10 | 82 | 1,920 |

Tuned thresholds, test half (rows: DDInter grade; columns: PRR tier)

| DDInter \ PRR tier | Minor | Moderate | Major |
|---|---:|---:|---:|
| Minor | 36 | 613 | 201 |
| Moderate | 419 | 6,687 | 1,807 |
| Major | 84 | 1,454 | 474 |

Spearman (tier) correlates the tier with the DDInter grade; Spearman (PRR) uses the raw PRR, so it doesn't depend on any threshold. Both use average ranks for ties.

## Calibration half (for reference; the tuned row is fitted here)

| Thresholds | Pairs | Accuracy | Macro-F1 | Linear-weighted κ | Spearman (tier) | Spearman (PRR) |
|---|---:|---:|---:|---:|---:|---:|
| current | 11,774 | 0.198 | 0.130 | 0.004 | 0.018 | 0.034 |
| tuned | 11,774 | 0.615 | 0.352 | 0.039 | 0.036 | 0.034 |
