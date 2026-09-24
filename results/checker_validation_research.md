# Report checker false positives: research build

Regenerate with `python scripts/validate_checker.py --profile research`. Offline, no API key.
Data: research build from RxNorm Current Prescribable 2026-09-08, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1, TWOSIDES (research only; not for redistribution); 634,582 interaction records; not synthetic; provenance.json sha256 `45feffc9cecccafcddd405722bbd0ea69775355ed7a33fb4bd0a73e81aeed0a5`.

Template reports on real data; every finding on a clean template report is a false positive (target 0). Sensitivity is measured on the FX- fixtures (results/checker_validation.md).

| Report set | Reports | Clinical claims checked | Reports with findings | Findings |
|---|---:|---:|---:|---:|
| 48 evaluation cases | 48 | 902 | 0 | 0 |
| stress: random 4-drug lists (seed 7) | 200 | 376 | 0 | 0 |
| hard names (comma, parenthesis or > 30 chars) + 3 partners each | 44 | 730 | 0 | 0 |

Findings by code: none
