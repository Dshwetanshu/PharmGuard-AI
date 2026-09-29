# Alert burden over the evaluation cases (research build)

Regenerate with `python scripts/eval_alert_burden.py --profile research`. Offline, no API key, deterministic reports.
Data: research build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1, TWOSIDES (research only; not for redistribution); 634,721 interaction records; not synthetic. provenance sha256 `73a84f12af814416c14bfccf5c8f02b0cda98081fcbfd81aa2b9f3f64e2c0ddd`.

57 reports (0 case(s) rejected before a report: fewer than 2 drugs). 239 pairs checked. An *item* is one line a reader sees under a finding heading.

| What the reader sees | Total | Share of items | Median per report | Max per report |
|---|---:|---:|---:|---:|
| graded interactions (DDInter) | 141 | 15.2% | 1 | 34 |
| of which Major | 40 | 4.3% | 1 | |
| of which Moderate / Minor | 87 / 14 | | | |
| listings without a severity grade | 98 | 10.5% | 0 | 32 |
| statistical signals shown (TWOSIDES) | 692 | 74.3% | 3 | 195 |
| statistical signals hidden ("+N more not shown") | 460 | | | |
| no-data pairs (declared) | 0 | | 0 | |
| unresolved inputs (declared) | 3 | | | |

Reports with at least one Major: 36 of 57. Reports with nothing graded: 6.
