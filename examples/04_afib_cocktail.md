# Atrial fibrillation regimen — multiple Major interactions

## Input

```
warfarin
digoxin
amiodarone
atorvastatin
lisinopril
```

## Output

# PharmGuard Interaction Report

## Summary
Analyzed 5 medication(s) across 10 unique pair(s). Retrieved 5 interaction record(s) from structured sources.

## Major Findings
- **amiodarone + digoxin** — digoxin toxicity (PRR=22.10) [TWOSIDES:TS-00000014]
- **amiodarone + digoxin** — digoxin clearance reduction [DDInter:DDI-00000009]
- **warfarin + amiodarone** — bleeding (PRR=13.80) [TWOSIDES:TS-00000011]
- **warfarin + amiodarone** — prolonged prothrombin time (PRR=11.20) [TWOSIDES:TS-00000010]
- **amiodarone + warfarin** — CYP2C9 inhibition [DDInter:DDI-00000010]

## Coverage Notes
**No data found** for 8 pair(s): amiodarone+atorvastatin, amiodarone+lisinopril, atorvastatin+digoxin, atorvastatin+lisinopril, atorvastatin+warfarin...

---
**Disclaimer.** PharmGuard is a decision-support tool grounded in public pharmaceutical databases. It is not a substitute for professional medical judgment. Always consult a licensed clinician or pharmacist before making changes to a medication regimen.

## Pipeline trace

```json
{
  "normalize_ms": 0,
  "plan_ms": 0,
  "num_pairs": 10,
  "retrieve_ms": 10,
  "total_interactions": 5,
  "no_data_pairs": 8,
  "generator": "deterministic",
  "generate_ms": 0
}
```
