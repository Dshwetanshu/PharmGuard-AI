# Unresolved drug (surfaced, not silently dropped)

## Input

```
lisinopril
definitely_not_a_drug_xyz
aspirin
```

## Output

# PharmGuard Interaction Report

## Summary
Analyzed 2 medication(s) across 1 unique pair(s). Retrieved 0 interaction record(s) from structured sources.

## Coverage Notes
**Unresolved inputs:** definitely_not_a_drug_xyz — these were not matched to any drug in the RxNorm/DrugBank vocabulary and were excluded.
**No data found** for 1 pair(s): aspirin+lisinopril

---
**Disclaimer.** PharmGuard is a decision-support tool grounded in public pharmaceutical databases. It is not a substitute for professional medical judgment. Always consult a licensed clinician or pharmacist before making changes to a medication regimen.

## Pipeline trace

```json
{
  "normalize_ms": 49,
  "plan_ms": 0,
  "num_pairs": 1,
  "retrieve_ms": 2,
  "total_interactions": 0,
  "no_data_pairs": 1,
  "generator": "deterministic",
  "generate_ms": 0
}
```
