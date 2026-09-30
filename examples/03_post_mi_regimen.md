# Post-MI regimen

Includes clopidogrel + omeprazole.

## Input

```
aspirin
clopidogrel
atorvastatin
metoprolol
lisinopril
omeprazole
```

## Output (deterministic report, public build)

# PharmGuard Interaction Report

## How your entries were read
- aspirin → aspirin
- clopidogrel → clopidogrel
- atorvastatin → atorvastatin
- metoprolol → metoprolol
- lisinopril → lisinopril
- omeprazole → omeprazole

## Summary
Analyzed 6 medications across 15 unique pairs. Found 7 graded interactions (Major 1, Moderate 4, Minor 2), 8 listings without a severity grade and 0 statistical reporting signals.

## Major Findings
- **clopidogrel + omeprazole** — curated severity: Major (DDInter) [DDInter:DDI-6e019091ab]

## Moderate Findings
- **aspirin + clopidogrel** — curated severity: Moderate (DDInter) [DDInter:DDI-6c5d22c04f]
- **aspirin + lisinopril** — curated severity: Moderate (DDInter) [DDInter:DDI-5c4747582b]
- **atorvastatin + clopidogrel** — curated severity: Moderate (DDInter) [DDInter:DDI-8c8d7424c3]
- **atorvastatin + omeprazole** — curated severity: Moderate (DDInter) [DDInter:DDI-ead9feedd4]

## Minor Findings
- **aspirin + metoprolol** — curated severity: Minor (DDInter) [DDInter:DDI-4aa997a1db]
- **aspirin + omeprazole** — curated severity: Minor (DDInter) [DDInter:DDI-2ea6b80981]

## Listed by DDInter without a severity grade
DDInter lists these pairs without a severity grade; the loaded data can't say whether they matter clinically.
- **aspirin + atorvastatin** — curated severity: not graded (DDInter) [DDInter:DDI-f7bef6fd81]
- **atorvastatin + lisinopril** — curated severity: not graded (DDInter) [DDInter:DDI-623022f04a]
- **atorvastatin + metoprolol** — curated severity: not graded (DDInter) [DDInter:DDI-0870b513b4]
- **clopidogrel + lisinopril** — curated severity: not graded (DDInter) [DDInter:DDI-dd5eb3c9f6]
- **clopidogrel + metoprolol** — curated severity: not graded (DDInter) [DDInter:DDI-b4646beca7]
- **lisinopril + metoprolol** — curated severity: not graded (DDInter) [DDInter:DDI-4adfa1c336]
- **lisinopril + omeprazole** — curated severity: not graded (DDInter) [DDInter:DDI-42244e84b6]
- **metoprolol + omeprazole** — curated severity: not graded (DDInter) [DDInter:DDI-790561ff57]

## Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

## How it was produced

- Graph path: normalize → plan → retrieve → template → finalize
- report_source: `deterministic`
- Final checker: passed, 15 clinical claims, 15 citations

**Data license.** Contains data derived from DDInter and SIDER 4.1 (PharmGuard public build), licensed CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/), not MIT: non-commercial use only, share alike. Citations and attributions: docs/DATASETS.md.
