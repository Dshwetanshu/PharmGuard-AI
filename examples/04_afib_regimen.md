# AFib regimen

Several Major findings involving amiodarone.

## Input

```
warfarin
digoxin
amiodarone
atorvastatin
lisinopril
```

## Output (deterministic report, public build)

# PharmGuard Interaction Report

## How your entries were read
- warfarin → warfarin
- digoxin → digoxin
- amiodarone → amiodarone
- atorvastatin → atorvastatin
- lisinopril → lisinopril

## Summary
Analyzed 5 medications across 10 unique pairs. Found 6 graded interactions (Major 2, Moderate 3, Minor 1), 4 listings without a severity grade and 0 statistical reporting signals.

## Major Findings
- **amiodarone + digoxin** — curated severity: Major (DDInter) [DDInter:DDI-5e89c41e33]
- **amiodarone + warfarin** — curated severity: Major (DDInter) [DDInter:DDI-683b838b25]

## Moderate Findings
- **amiodarone + atorvastatin** — curated severity: Moderate (DDInter) [DDInter:DDI-87ed95852d]
- **atorvastatin + digoxin** — curated severity: Moderate (DDInter) [DDInter:DDI-7fba1baca2]
- **digoxin + lisinopril** — curated severity: Moderate (DDInter) [DDInter:DDI-0fd192ca29]

## Minor Findings
- **atorvastatin + warfarin** — curated severity: Minor (DDInter) [DDInter:DDI-3cab39bdf9]

## Listed by DDInter without a severity grade
DDInter lists these pairs without a severity grade; the loaded data can't say whether they matter clinically.
- **amiodarone + lisinopril** — curated severity: not graded (DDInter) [DDInter:DDI-a96797a0cd]
- **atorvastatin + lisinopril** — curated severity: not graded (DDInter) [DDInter:DDI-623022f04a]
- **digoxin + warfarin** — curated severity: not graded (DDInter) [DDInter:DDI-303812e758]
- **lisinopril + warfarin** — curated severity: not graded (DDInter) [DDInter:DDI-843e75c917]

## Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

## How it was produced

- Graph path: normalize → plan → retrieve → template → finalize
- report_source: `deterministic`
- Final checker: passed, 10 clinical claims, 10 citations
