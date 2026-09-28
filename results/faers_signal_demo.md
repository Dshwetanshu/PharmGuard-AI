# FAERS signal thresholds: surfaced vs suppressed

Regenerate with `python scripts/demo_faers_signals.py simvastatin+clarithromycin metformin+lisinopril warfarin+fluconazole` (live openFDA, 2026-09-28). FAERS reports are unvalidated; a surfaced signal is a reporting pattern, not evidence that the drugs interact.
Surfaced only if PRR ≥ 2, χ² ≥ 4, at least 3 reports (Evans), the ROR's lower 95% bound is above 1, and the pair's event rate is at least 2 × each drug's rate without the other.

| Pair | Event | Reports (a) | PRR | ROR (95% CI) | χ² (Yates) | Pair rate | Rate A without B | Rate B without A | Result |
|---|---|---:|---:|---|---:|---:|---:|---:|---|
| clarithromycin + simvastatin | rhabdomyolysis | 242 | 65.28 | 74.79 (65.32–85.63) | 15193.9 | 0.1289 | 0.0086 | 0.0188 | **surfaced** |
| clarithromycin + simvastatin | malaise | 203 | 5.16 | 5.66 (4.89–6.55) | 690.5 | 0.1081 | 0.0465 | 0.0318 | **surfaced** |
| clarithromycin + simvastatin | macular degeneration | 202 | 192.50 | 215.58 (186.09–249.75) | 37655.3 | 0.1076 | 0.0174 | 0.0010 | **surfaced** |
| lisinopril + metformin | nausea | 3,769 | 1.92 | 1.99 (1.92–2.06) | 1707.3 | 0.0719 | 0.0588 | 0.0694 | suppressed: PRR below 2; explained by lisinopril alone (pair rate < 2 x its rate without the other drug); explained by metformin alone (pair rate < 2 x its rate without the other drug) |
| lisinopril + metformin | diarrhoea | 3,388 | 2.11 | 2.19 (2.12–2.27) | 2040.1 | 0.0647 | 0.0553 | 0.0647 | suppressed: explained by lisinopril alone (pair rate < 2 x its rate without the other drug); explained by metformin alone (pair rate < 2 x its rate without the other drug) |
| lisinopril + metformin | fatigue | 3,223 | 1.66 | 1.71 (1.65–1.77) | 881.1 | 0.0615 | 0.0659 | 0.0476 | suppressed: PRR below 2; explained by lisinopril alone (pair rate < 2 x its rate without the other drug); explained by metformin alone (pair rate < 2 x its rate without the other drug) |
| fluconazole + warfarin | international normalised ratio increased | 185 | 127.79 | 154.57 (131.85–181.21) | 23027.6 | 0.1744 | 0.0027 | 0.0823 | **surfaced** |
| fluconazole + warfarin | chronic kidney disease | 103 | 26.59 | 29.34 (23.94–35.96) | 2517.0 | 0.0971 | 0.0214 | 0.0095 | **surfaced** |
| fluconazole + warfarin | renal failure | 100 | 14.78 | 16.22 (13.20–19.93) | 1278.6 | 0.0943 | 0.0250 | 0.0163 | **surfaced** |

openFDA calls made: 0 (the rest from the cache in data/cache/openfda). Rate = reports with the event / reports listing the drug(s). Drugs matched on patient.drug.medicinalproduct (free text as reported). Top events by co-report count, administrative MedDRA terms skipped.
