# A pair DDInter lists without a grade

Listed, but not graded: the report says so rather than calling it safe or dangerous.

## Input

```
acetaminophen
levothyroxine
```

## Output (deterministic report, public build)

# PharmGuard Interaction Report

## How your entries were read
- acetaminophen → acetaminophen
- levothyroxine → levothyroxine

## Summary
Analyzed 2 medications across 1 unique pair. Found 0 graded interactions (Major 0, Moderate 0, Minor 0), 1 listing without a severity grade and 0 statistical reporting signals.

## Listed by DDInter without a severity grade
DDInter lists these pairs without a severity grade; the loaded data can't say whether they matter clinically.
- **acetaminophen + levothyroxine** — curated severity: not graded (DDInter) [DDInter:DDI-8c1f6243a4]

## Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

## How it was produced

- Graph path: normalize → plan → retrieve → template → finalize
- report_source: `deterministic`
- Final checker: passed, 1 clinical claims, 1 citations

**Data license.** Contains data derived from DDInter and SIDER 4.1 (PharmGuard public build), licensed CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/), not MIT: non-commercial use only, share alike. Citations and attributions: docs/DATASETS.md.
