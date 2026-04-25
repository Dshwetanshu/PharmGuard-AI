# Geriatric polypharmacy — the proposal scenario

## Input

```
lisinopril
spironolactone
metformin
atorvastatin
aspirin
omeprazole
sertraline
```

## Output

# PharmGuard Interaction Report

## Summary
Analyzed 7 medication(s) across 21 unique pair(s). Retrieved 9 interaction record(s) from structured sources.

## Major Findings
- **lisinopril + spironolactone** — hyperkalemia (PRR=14.20) [TWOSIDES:TS-00000006]
- **lisinopril + spironolactone** — additive potassium retention [DDInter:DDI-00000003]

## Moderate Findings
- **aspirin + omeprazole** — reduced antiplatelet effect (PRR=4.80) [TWOSIDES:TS-00000003]
- **aspirin + omeprazole** — reduced antiplatelet response [DDInter:DDI-00000019]
- **aspirin + sertraline** — gastrointestinal bleeding (PRR=6.20) [TWOSIDES:TS-00000004]
- **aspirin + sertraline** — additive GI bleeding [DDInter:DDI-00000020]
- **lisinopril + spironolactone** — renal failure (PRR=7.80) [TWOSIDES:TS-00000008]

## Minor Findings
- **aspirin + spironolactone** — reduced diuretic efficacy (PRR=2.60) [TWOSIDES:TS-00000050]
- **metformin + lisinopril** — hypoglycemia risk (PRR=2.40) [TWOSIDES:TS-00000046]

## Coverage Notes
**No data found** for 16 pair(s): aspirin+atorvastatin, aspirin+lisinopril, aspirin+metformin, atorvastatin+lisinopril, atorvastatin+metformin...

---
**Disclaimer.** PharmGuard is a decision-support tool grounded in public pharmaceutical databases. It is not a substitute for professional medical judgment. Always consult a licensed clinician or pharmacist before making changes to a medication regimen.

## Pipeline trace

```json
{
  "normalize_ms": 0,
  "plan_ms": 0,
  "num_pairs": 21,
  "retrieve_ms": 23,
  "total_interactions": 9,
  "no_data_pairs": 16,
  "generator": "deterministic",
  "generate_ms": 0
}
```
