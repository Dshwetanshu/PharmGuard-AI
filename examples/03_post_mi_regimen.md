# Post-myocardial-infarction regimen

## Input

```
aspirin
clopidogrel
atorvastatin
metoprolol
lisinopril
omeprazole
```

## Output

# PharmGuard Interaction Report

## Summary
Analyzed 6 medication(s) across 15 unique pair(s). Retrieved 6 interaction record(s) from structured sources.

## Moderate Findings
- **aspirin + clopidogrel** — bleeding (PRR=5.10) [TWOSIDES:TS-00000005]
- **aspirin + omeprazole** — reduced antiplatelet effect (PRR=4.80) [TWOSIDES:TS-00000003]
- **aspirin + omeprazole** — reduced antiplatelet response [DDInter:DDI-00000019]
- **clopidogrel + omeprazole** — reduced antiplatelet effect (PRR=7.20) [TWOSIDES:TS-00000017]
- **omeprazole + clopidogrel** — reduced antiplatelet response (PRR=6.90) [TWOSIDES:TS-00000041]
- **clopidogrel + omeprazole** — CYP2C19 inhibition [DDInter:DDI-00000018]

## Coverage Notes
**No data found** for 12 pair(s): aspirin+atorvastatin, aspirin+lisinopril, aspirin+metoprolol, atorvastatin+clopidogrel, atorvastatin+lisinopril...

---
**Disclaimer.** PharmGuard is a decision-support tool grounded in public pharmaceutical databases. It is not a substitute for professional medical judgment. Always consult a licensed clinician or pharmacist before making changes to a medication regimen.

## Pipeline trace

```json
{
  "normalize_ms": 0,
  "plan_ms": 0,
  "num_pairs": 15,
  "retrieve_ms": 15,
  "total_interactions": 6,
  "no_data_pairs": 12,
  "generator": "deterministic",
  "generate_ms": 0
}
```
