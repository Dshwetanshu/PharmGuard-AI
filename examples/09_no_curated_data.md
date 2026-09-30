# Pairs with no curated record

Declared as no data, which is not evidence of safety.

## Input

```
escitalopram
amoxicillin
melatonin
```

## Output (deterministic report, public build)

# PharmGuard Interaction Report

## How your entries were read
- escitalopram → escitalopram
- amoxicillin → amoxicillin
- melatonin → melatonin

## Summary
Analyzed 3 medications across 3 unique pairs. Found 0 graded interactions (Major 0, Moderate 0, Minor 0), 0 listings without a severity grade and 0 statistical reporting signals.

## Coverage Notes
### No Curated Interaction Data
No record in the queried curated sources for these 3 pairs. Absence of a record does not mean the combination is safe.
- amoxicillin + escitalopram
- amoxicillin + melatonin
- escitalopram + melatonin

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

## How it was produced

- Graph path: normalize → plan → retrieve → template → finalize
- report_source: `deterministic`
- Final checker: passed, 0 clinical claims, 0 citations

**Data license.** Contains data derived from DDInter and SIDER 4.1 (PharmGuard public build), licensed CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/), not MIT: non-commercial use only, share alike. Citations and attributions: docs/DATASETS.md.
