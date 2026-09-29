# Warfarin + ibuprofen

A textbook Major interaction.

## Input

```
warfarin
ibuprofen
```

## Output (deterministic report, public build)

# PharmGuard Interaction Report

## How your entries were read
- warfarin → warfarin
- ibuprofen → ibuprofen

## Summary
Analyzed 2 medications across 1 unique pair. Found 1 graded interaction (Major 1, Moderate 0, Minor 0), 0 listings without a severity grade and 0 statistical reporting signals.

## Major Findings
- **ibuprofen + warfarin** — curated severity: Major (DDInter) [DDInter:DDI-39db009bff]

## Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

## How it was produced

- Graph path: normalize → plan → retrieve → template → finalize
- report_source: `deterministic`
- Final checker: passed, 1 clinical claims, 1 citations
