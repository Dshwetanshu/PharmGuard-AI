# Example Outputs

This folder contains pre-recorded PharmGuard outputs across 8 different scenarios. Every file shows the exact input, the exact output, and the pipeline trace. All examples were generated against the sample dataset in `data/sample/` (85 interactions, 52 side effects, 22 reviews) with the deterministic generator (no LLM) for reproducibility.

## Regenerate any example

```bash
python scripts/demo.py <drug1> <drug2> ...
```

Or run all 8 examples at once:

```bash
python scripts/generate_examples.py
```

## Index

| File | Scenario | What it demonstrates |
|---|---|---|
| [01_geriatric_proposal_scenario.md](01_geriatric_proposal_scenario.md) | 7-drug geriatric polypharmacy (the proposal's opening vignette) | Cross-source citations (TWOSIDES + DDInter), combinatorial enumeration (21 pairs), Major severity classification |
| [02_warfarin_nsaid_classic.md](02_warfarin_nsaid_classic.md) | Warfarin + ibuprofen | Classic textbook interaction. Multiple Major findings from both sources. |
| [03_post_mi_regimen.md](03_post_mi_regimen.md) | Aspirin + clopidogrel + atorvastatin + metoprolol + lisinopril + omeprazole | Post-MI prescribing pattern. Flags the clopidogrel-omeprazole CYP2C19 interaction. |
| [04_afib_cocktail.md](04_afib_cocktail.md) | Warfarin + digoxin + amiodarone + atorvastatin + lisinopril | AFib regimen. Multiple Major findings from amiodarone interactions. |
| [05_brand_names_misspellings.md](05_brand_names_misspellings.md) | Lipitor + metfromin + XANAX + Prilosec | Normalization robustness: brand names, misspellings, mixed case — all resolved. |
| [06_no_interactions_baseline.md](06_no_interactions_baseline.md) | Acetaminophen + levothyroxine | No-interaction baseline. System explicitly declares "no data found" rather than silent omission. |
| [07_single_drug_edge_case.md](07_single_drug_edge_case.md) | Single drug | Edge case: 1 drug → 0 pairs → 0 interactions. Correctly handled. |
| [08_unresolved_drug.md](08_unresolved_drug.md) | Valid drug + fake drug + valid drug | Unresolved inputs are surfaced in a Coverage Note, not silently dropped. |

## Safety properties demonstrated

Across all 8 examples, every report:
- Includes a disclaimer (appended by pipeline code, not by the model)
- Cites every clinical claim with `[SOURCE:RECORD_ID]`
- Declares unresolved inputs explicitly
- Declares pairs with no data explicitly

These are contract invariants, not learned behaviors — they hold regardless of what the LLM does or doesn't do.
