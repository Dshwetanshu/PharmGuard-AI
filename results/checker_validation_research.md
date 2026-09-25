# Report checker false positives: research build

Regenerate with `python scripts/validate_checker.py --profile research`. Offline, no API key.
Data: research build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1, TWOSIDES (research only; not for redistribution); 634,721 interaction records; not synthetic; provenance.json sha256 `73a84f12af814416c14bfccf5c8f02b0cda98081fcbfd81aa2b9f3f64e2c0ddd`.

Template reports on real data; every finding on a clean template report is a false positive (target 0). Sensitivity is measured on the FX- fixtures (results/checker_validation.md).

| Report set | Reports | Clinical claims checked | Reports with findings | Findings |
|---|---:|---:|---:|---:|
| 56 evaluation cases | 56 | 927 | 0 | 0 |
| stress: random 4-drug lists (seed 7) | 200 | 376 | 0 | 0 |
| hard names (comma, parenthesis or > 30 chars) + 3 partners each | 44 | 730 | 0 | 0 |

Findings by code: none
