# Brand names, a misspelling, mixed case

How each entry was read: brands, a spelling match flagged for checking.

## Input

```
Lipitor
metfromin
XANAX
Prilosec
```

## Output (deterministic report, public build)

# PharmGuard Interaction Report

## How your entries were read
- Lipitor → atorvastatin (brand name)
- metfromin → metformin (spelling match: check this)
- XANAX → alprazolam (brand name)
- Prilosec → omeprazole (brand name)

## Summary
Analyzed 4 medications across 6 unique pairs. Found 2 graded interactions (Major 0, Moderate 2, Minor 0), 4 listings without a severity grade and 0 statistical reporting signals.

## Moderate Findings
- **alprazolam + omeprazole** — curated severity: Moderate (DDInter) [DDInter:DDI-0911247b36]
- **atorvastatin + omeprazole** — curated severity: Moderate (DDInter) [DDInter:DDI-ead9feedd4]

## Listed by DDInter without a severity grade
DDInter lists these pairs without a severity grade; the loaded data can't say whether they matter clinically.
- **alprazolam + atorvastatin** — curated severity: not graded (DDInter) [DDInter:DDI-df349a2edd]
- **alprazolam + metformin** — curated severity: not graded (DDInter) [DDInter:DDI-9ce166bea2]
- **atorvastatin + metformin** — curated severity: not graded (DDInter) [DDInter:DDI-2e6e00a61f]
- **metformin + omeprazole** — curated severity: not graded (DDInter) [DDInter:DDI-c4fa317e2d]

## Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

## How it was produced

- Graph path: normalize → plan → retrieve → template → finalize
- report_source: `deterministic`
- Final checker: passed, 6 clinical claims, 6 citations

**Data license.** Contains data derived from DDInter and SIDER 4.1 (PharmGuard public build), licensed CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/), not MIT: non-commercial use only, share alike. Citations and attributions: docs/DATASETS.md.
