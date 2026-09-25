# Report checker false positives: public build

Regenerate with `python scripts/validate_checker.py --profile public`. Offline, no API key.
Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic; provenance.json sha256 `688a8cee8a9c61abf456991240f7451859c723db6600122c203815ebd16ef578`.

Template reports on real data; every finding on a clean template report is a false positive (target 0). Sensitivity is measured on the FX- fixtures (results/checker_validation.md).

| Report set | Reports | Clinical claims checked | Reports with findings | Findings |
|---|---:|---:|---:|---:|
| 56 evaluation cases | 56 | 238 | 0 | 0 |
| stress: random 4-drug lists (seed 7) | 200 | 239 | 0 | 0 |
| hard names (comma, parenthesis or > 30 chars) + 3 partners each | 27 | 153 | 0 | 0 |

Findings by code: none
