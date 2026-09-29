# Hand-label changes

The hand labels are `known_interaction_pairs` in `src/evaluation/test_cases.py`. They change only with the
project owner's approval, and every change is listed here.

## 2026-09-29

Reviewed against the public build (DDInter bulk download). Approved by the project owner.

| Case | Before | After | Why |
|---|---|---|---|
| EDG-03 "Brand name input" (Lipitor + Prinivil) | label (atorvastatin, lisinopril) | no label; brand-name resolution checks kept | No record in the synthetic sample; DDInter lists the pair without a grade; neither FDA label names the other drug (`data/validation/reference_interactions.csv`, a negative control). It was the only entry in `SUSPECTED_LABEL_ERRORS`, which is now empty. |
| END-02 "Insulin + beta-blocker masking" | input `insulin`; label (insulin, metoprolol) | input `insulin glargine`; label (insulin glargine, metoprolol) | Plain "insulin" is ambiguous in RxNorm and stays unresolved on the real builds by design, so the label could never match there. insulin glargine + metoprolol is a DDInter Moderate record. On the synthetic sample, which has only a generic "insulin", the new label is a source gap. |
| LA-09 (new) "Ambiguous generic name (plain insulin)" | — | input `insulin`, `metoprolol`; no label | Keeps the check that plain "insulin" stays ambiguous on the real builds (it moved here from END-02). |
| EDG-02 | description "Two drugs with no known interaction" | "Two drugs with no graded interaction in DDInter" | DDInter lists acetaminophen + levothyroxine without a grade, so "no known interaction" claimed more than the data shows. No label change. |

Not changed: the 12 unlabelled pairs that DDInter grades Major (owner's decision: add none, so the labels
stay independent of DDInter).

Effect: 38 → 37 labelled pairs, 56 → 57 cases. Results regenerated in the same step.
