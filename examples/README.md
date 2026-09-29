# Example outputs

PharmGuard's deterministic reports for 9 scenarios on the **public build** (the data the live app uses: https://pharmguard.web.app). Regenerate with `python scripts/generate_examples.py`; a realdata test checks they are current.

| File | Scenario |
|---|---|
| [01_geriatric_polypharmacy.md](01_geriatric_polypharmacy.md) | 7-drug geriatric list: 21 pairs checked; curated grades, ungraded DDInter listings. |
| [02_warfarin_nsaid.md](02_warfarin_nsaid.md) | Warfarin + ibuprofen: A textbook Major interaction. |
| [03_post_mi_regimen.md](03_post_mi_regimen.md) | Post-MI regimen: Includes clopidogrel + omeprazole. |
| [04_afib_regimen.md](04_afib_regimen.md) | AFib regimen: Several Major findings involving amiodarone. |
| [05_brand_names_misspellings.md](05_brand_names_misspellings.md) | Brand names, a misspelling, mixed case: How each entry was read: brands, a spelling match flagged for checking. |
| [06_ungraded_listing.md](06_ungraded_listing.md) | A pair DDInter lists without a grade: Listed, but not graded: the report says so rather than calling it safe or dangerous. |
| [07_single_drug.md](07_single_drug.md) | Single drug: Fewer than 2 drugs: no pairs to check. |
| [08_unresolved_and_ambiguous.md](08_unresolved_and_ambiguous.md) | An unknown name, an ambiguous name and a combination product: Nothing is silently dropped or guessed. |
| [09_no_curated_data.md](09_no_curated_data.md) | Pairs with no curated record: Declared as no data, which is not evidence of safety. |

## Data sources and attribution

- **DDInter.** Interaction severities from the DDInter bulk download (ddinter2.scbdd.com, files dated 2024-05-21). Cite: Tian Y, Yi J, Wang N, Wu C, Peng J, Liu S, Yang G, Cao D. DDInter 2.0: an enhanced drug interaction resource with expanded data coverage, new interaction types, and improved user interface. Nucleic Acids Research. 2025;53(D1):D1356-D1362. doi:10.1093/nar/gkae726; and Xiong G, Yang Z, Yi J, Wang N, Wang L, Zhu H, Wu C, Lu A, Chen X, Liu S, Hou T, Cao D. DDInter: an online drug-drug interaction database towards improving clinical decision-making and patient safety. Nucleic Acids Research. 2022;50(D1):D1200-D1207. doi:10.1093/nar/gkab880. Licensed CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/). PharmGuard mapped drug names to RxNorm and removed duplicates.
- **SIDER 4.1.** Kuhn M, Letunic I, Jensen LJ, Bork P. The SIDER database of drugs and side effects. Nucleic Acids Research. 2016;44(D1):D1075-D1079. doi:10.1093/nar/gkv1075. Licensed CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/).
- **RxNorm.** This product uses publicly available data courtesy of the U.S. National Library of Medicine (NLM), National Institutes of Health, Department of Health and Human Services; NLM is not responsible for the product and does not endorse or recommend this or any other product. Vocabulary: RxNorm Current Prescribable Content, release 2026-09-08; drug names may have changed since that release. NLM urges you to consult with a qualified physician for medical advice.
- **Drugs@FDA.** Brand names, including discontinued products, from the Drugs@FDA data files (datdaf_20260924, files dated 2026-09-23), U.S. Food and Drug Administration; public domain. The FDA does not endorse this product.
- **openFDA.** Data provided by the U.S. Food and Drug Administration (https://open.fda.gov). Used only when the optional FAERS lookup is enabled; FAERS reports are unvalidated, and the FDA does not endorse this product.
- **Non-commercial use.** This build contains data licensed CC BY-NC-SA 4.0 (DDInter, SIDER 4.1). Non-commercial use only; anything derived from that data must be shared under the same license, with the attributions above.
