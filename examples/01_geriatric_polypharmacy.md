# 7-drug geriatric list

21 pairs checked; curated grades, ungraded DDInter listings.

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

## Output (deterministic report, public build)

# PharmGuard Interaction Report

## How your entries were read
- lisinopril → lisinopril
- spironolactone → spironolactone
- metformin → metformin
- atorvastatin → atorvastatin
- aspirin → aspirin
- omeprazole → omeprazole
- sertraline → sertraline

## Summary
Analyzed 7 medications across 21 unique pairs. Found 9 graded interactions (Major 1, Moderate 6, Minor 2), 12 listings without a severity grade and 0 statistical reporting signals.

## Major Findings
- **lisinopril + spironolactone** — curated severity: Major (DDInter) [DDInter:DDI-267de0347b]

## Moderate Findings
- **aspirin + lisinopril** — curated severity: Moderate (DDInter) [DDInter:DDI-5c4747582b]
- **aspirin + sertraline** — curated severity: Moderate (DDInter) [DDInter:DDI-cdf8ccde8b]
- **atorvastatin + omeprazole** — curated severity: Moderate (DDInter) [DDInter:DDI-ead9feedd4]
- **lisinopril + metformin** — curated severity: Moderate (DDInter) [DDInter:DDI-cd8167557b]
- **metformin + spironolactone** — curated severity: Moderate (DDInter) [DDInter:DDI-d96d408d7e]
- **sertraline + spironolactone** — curated severity: Moderate (DDInter) [DDInter:DDI-897a419cf0]

## Minor Findings
- **aspirin + omeprazole** — curated severity: Minor (DDInter) [DDInter:DDI-2ea6b80981]
- **aspirin + spironolactone** — curated severity: Minor (DDInter) [DDInter:DDI-667245c02c]

## Listed by DDInter without a severity grade
DDInter lists these pairs without a severity grade; the loaded data can't say whether they matter clinically.
- **aspirin + atorvastatin** — curated severity: not graded (DDInter) [DDInter:DDI-f7bef6fd81]
- **aspirin + metformin** — curated severity: not graded (DDInter) [DDInter:DDI-67454dcdb5]
- **atorvastatin + lisinopril** — curated severity: not graded (DDInter) [DDInter:DDI-623022f04a]
- **atorvastatin + metformin** — curated severity: not graded (DDInter) [DDInter:DDI-2e6e00a61f]
- **atorvastatin + sertraline** — curated severity: not graded (DDInter) [DDInter:DDI-f3d07d3637]
- **atorvastatin + spironolactone** — curated severity: not graded (DDInter) [DDInter:DDI-e46ec7e374]
- **lisinopril + omeprazole** — curated severity: not graded (DDInter) [DDInter:DDI-42244e84b6]
- **lisinopril + sertraline** — curated severity: not graded (DDInter) [DDInter:DDI-5b7b1dd03e]
- **metformin + omeprazole** — curated severity: not graded (DDInter) [DDInter:DDI-c4fa317e2d]
- **metformin + sertraline** — curated severity: not graded (DDInter) [DDInter:DDI-717ca3c9e1]
- **omeprazole + sertraline** — curated severity: not graded (DDInter) [DDInter:DDI-079b6f3912]
- **omeprazole + spironolactone** — curated severity: not graded (DDInter) [DDInter:DDI-08826bdf6e]

## Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

## How it was produced

- Graph path: normalize → plan → retrieve → template → finalize
- report_source: `deterministic`
- Final checker: passed, 21 clinical claims, 21 citations

**Data license.** Contains data derived from DDInter and SIDER 4.1 (PharmGuard public build), licensed CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/), not MIT: non-commercial use only, share alike. Citations and attributions: docs/DATASETS.md.
