# Report checker false positives: public build

Regenerate with `python scripts/validate_checker.py --profile public`. Offline, no API key.
Data: public build from RxNorm Current Prescribable 2026-09-08, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,534 interaction records; not synthetic; provenance.json sha256 `d459af5d62bc3110875ab7e30b8ef4a996bae79b2d5353eab0544ff521560d14`.

Template reports on real data; every finding on a clean template report is a false positive (target 0). Sensitivity is measured on the FX- fixtures (results/checker_validation.md).

| Report set | Reports | Clinical claims checked | Reports with findings | Findings |
|---|---:|---:|---:|---:|
| 48 evaluation cases | 48 | 231 | 0 | 0 |
| stress: random 4-drug lists (seed 7) | 200 | 227 | 0 | 0 |
| hard names (comma, parenthesis or > 30 chars) + 3 partners each | 26 | 147 | 0 | 0 |

Findings by code: none
