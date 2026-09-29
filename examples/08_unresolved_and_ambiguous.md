# An unknown name, an ambiguous name and a combination product

Nothing is silently dropped or guessed.

## Input

```
lisinopril
warfarin
fictional_drug_xyz
insulin
Percocet
```

## Output (deterministic report, public build)

# PharmGuard Interaction Report

## How your entries were read
- lisinopril → lisinopril
- warfarin → warfarin
- fictional_drug_xyz → not found: check the spelling or enter the generic name; discontinued brands and non-US names may not be recognized
- insulin → not analysed: ambiguous name; matching drugs: insulin, regular, human / insulin aspart, human / insulin lispro / insulin detemir (and 3 more); enter the specific drug
- Percocet → not analysed: combination product: acetaminophen + oxycodone; enter them separately

## Summary
Analyzed 2 medications across 1 unique pair. Found 0 graded interactions (Major 0, Moderate 0, Minor 0), 1 listing without a severity grade and 0 statistical reporting signals.

## Listed by DDInter without a severity grade
DDInter lists these pairs without a severity grade; the loaded data can't say whether they matter clinically.
- **lisinopril + warfarin** — curated severity: not graded (DDInter) [DDInter:DDI-843e75c917]

## Coverage Notes
### Unresolved Inputs
These inputs could not be matched to a drug in the local vocabulary and were excluded:
- fictional_drug_xyz — not found: check the spelling or enter the generic name; discontinued brands and non-US names may not be recognized
- insulin — ambiguous name; matching drugs: insulin, regular, human / insulin aspart, human / insulin lispro / insulin detemir (and 3 more); enter the specific drug
- Percocet — combination product: acetaminophen + oxycodone; enter them separately

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

## How it was produced

- Graph path: normalize → plan → retrieve → template → finalize
- report_source: `deterministic`
- Final checker: passed, 1 clinical claims, 1 citations
