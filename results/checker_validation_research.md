# Report checker false positives: research build

Regenerate with `python scripts/validate_checker.py --profile research`. Offline, no API key.
Data: research build from RxNorm Current Prescribable 2026-09-08, DDInter 2.0, SIDER 4.1, TWOSIDES (research only; not for redistribution); 634,582 interaction records; not synthetic; provenance.json sha256 `070bf71c28c706bbf53cc4e260e4f62591dd3ed396565d817a743ef755b8a2b3`.

Template reports on real data; every finding on a clean template report is a false positive (target 0). Sensitivity is measured on the FX- fixtures (results/checker_validation.md).

| Report set | Reports | Clinical claims checked | Reports with findings | Findings |
|---|---:|---:|---:|---:|
| 48 evaluation cases | 48 | 902 | 0 | 0 |
| stress: random 4-drug lists (seed 7) | 200 | 376 | 0 | 0 |
| hard names (comma, parenthesis or > 30 chars) + 3 partners each | 44 | 730 | 0 | 0 |

Findings by code: none
