# Warfarin + NSAID — classic dangerous combination

## Input

```
warfarin
ibuprofen
```

## Output

# PharmGuard Interaction Report

## Summary
Analyzed 2 medication(s) across 1 unique pair(s). Retrieved 2 interaction record(s) from structured sources.

## Major Findings
- **warfarin + ibuprofen** — hemorrhage (PRR=15.60) [TWOSIDES:TS-00000009]
- **warfarin + ibuprofen** — NSAID potentiation of anticoagulation [DDInter:DDI-00000002]

## Coverage Notes
All inputs resolved; all pairs had coverage in queried sources.

---
**Disclaimer.** PharmGuard is a decision-support tool grounded in public pharmaceutical databases. It is not a substitute for professional medical judgment. Always consult a licensed clinician or pharmacist before making changes to a medication regimen.

## Pipeline trace

```json
{
  "normalize_ms": 0,
  "plan_ms": 0,
  "num_pairs": 1,
  "retrieve_ms": 3,
  "total_interactions": 2,
  "no_data_pairs": 0,
  "generator": "deterministic",
  "generate_ms": 0
}
```
