# Alert burden over the evaluation cases (public build)

Regenerate with `python scripts/eval_alert_burden.py --profile public`. Offline, no API key, deterministic reports.
Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic. provenance sha256 `fc037dc5f67b9c0dd05c4664e48a4888a155d285dc0e1a11369fc971dab31073`.

57 reports (0 case(s) rejected before a report: fewer than 2 drugs). 239 pairs checked. An *item* is one line a reader sees under a finding heading.

| What the reader sees | Total | Share of items | Median per report | Max per report |
|---|---:|---:|---:|---:|
| graded interactions (DDInter) | 141 | 59.0% | 1 | 34 |
| of which Major | 40 | 16.7% | 1 | |
| of which Moderate / Minor | 87 / 14 | | | |
| listings without a severity grade | 98 | 41.0% | 0 | 32 |
| statistical signals shown (TWOSIDES) | 0 | 0.0% | 0 | 0 |
| statistical signals hidden ("+N more not shown") | 0 | | | |
| no-data pairs (declared) | 0 | | 0 | |
| unresolved inputs (declared) | 3 | | | |

Reports with at least one Major: 36 of 57. Reports with nothing graded: 6.

## Per case

| Case | Pairs | Major | Moderate | Minor | Ungraded | Signals | No data | Unresolved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GER-01 | 21 | 1 | 6 | 2 | 12 | 0 | 0 | 0 |
| GER-02 | 15 | 1 | 5 | 0 | 9 | 0 | 0 | 0 |
| GER-03 | 15 | 1 | 4 | 2 | 8 | 0 | 0 | 0 |
| GER-04 | 10 | 2 | 3 | 1 | 4 | 0 | 0 | 0 |
| TXT-01 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| TXT-02 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| TXT-03 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| TXT-04 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| TXT-05 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| TXT-06 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| TXT-07 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| TXT-08 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| TXT-09 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| TXT-10 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| EDG-01 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| EDG-02 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| EDG-03 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| EDG-04 | 3 | 0 | 2 | 0 | 1 | 0 | 0 | 0 |
| EDG-05 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| EDG-06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| EDG-07 | 66 | 4 | 25 | 5 | 32 | 0 | 0 | 0 |
| MH-01 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| MH-02 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| MH-03 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| MH-04 | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 0 |
| MH-05 | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 0 |
| CV-01 | 6 | 1 | 3 | 0 | 2 | 0 | 0 | 0 |
| CV-02 | 3 | 0 | 2 | 0 | 1 | 0 | 0 | 0 |
| CV-03 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| CV-04 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| CV-05 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| END-01 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| END-02 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| END-03 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| ID-01 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| ID-02 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| ID-03 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| ID-04 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| ONC-01 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| ONC-02 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| PAIN-01 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| PAIN-02 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| PAIN-03 | 6 | 1 | 2 | 0 | 3 | 0 | 0 | 0 |
| RSP-01 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| RSP-02 | 3 | 1 | 2 | 0 | 0 | 0 | 0 | 0 |
| GI-01 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| GI-02 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| REAL-01 | 45 | 1 | 16 | 4 | 24 | 0 | 0 | 0 |
| LA-01 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| LA-02 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| LA-03 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| LA-04 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| LA-05 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| LA-06 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| LA-07 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| LA-08 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| LA-09 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
