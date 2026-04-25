# Robustness: brand names + misspellings + mixed case

## Input

```
Lipitor
metfromin
XANAX
Prilosec
```

## Output

# PharmGuard Interaction Report

## Summary
Analyzed 4 medication(s) across 6 unique pair(s). Retrieved 0 interaction record(s) from structured sources.

## Coverage Notes
**No data found** for 6 pair(s): alprazolam+atorvastatin, alprazolam+metformin, alprazolam+omeprazole, atorvastatin+metformin, atorvastatin+omeprazole...

---
**Disclaimer.** PharmGuard is a decision-support tool grounded in public pharmaceutical databases. It is not a substitute for professional medical judgment. Always consult a licensed clinician or pharmacist before making changes to a medication regimen.

## Pipeline trace

```json
{
  "normalize_ms": 1,
  "plan_ms": 0,
  "num_pairs": 6,
  "retrieve_ms": 5,
  "total_interactions": 0,
  "no_data_pairs": 6,
  "generator": "deterministic",
  "generate_ms": 0
}
```
