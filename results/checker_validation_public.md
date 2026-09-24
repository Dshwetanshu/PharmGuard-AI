# Report checker false positives: public build

Regenerate with `python scripts/validate_checker.py --profile public`. Offline, no API key.
Data: public build from RxNorm Current Prescribable 2026-09-08, DDInter 2.0, SIDER 4.1; 169,534 interaction records; not synthetic; provenance.json sha256 `9312529882f37a86552bcf909278f285411a2b7ccdbbec8d0876107c69b5a055`.

Template reports on real data; every finding on a clean template report is a false positive (target 0). Sensitivity is measured on the FX- fixtures (results/checker_validation.md).

| Report set | Reports | Clinical claims checked | Reports with findings | Findings |
|---|---:|---:|---:|---:|
| 48 evaluation cases | 48 | 231 | 0 | 0 |
| stress: random 4-drug lists (seed 7) | 200 | 227 | 0 | 0 |
| hard names (comma, parenthesis or > 30 chars) + 3 partners each | 26 | 147 | 0 | 0 |

Findings by code: none
