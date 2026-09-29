# Reference set (public build)

Regenerate with `python scripts/score_reference_set.py --profile public`. Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic. provenance sha256 `fc037dc5f67b9c0dd05c4664e48a4888a155d285dc0e1a11369fc971dab31073`.

Rows: 41; scored 33; **skipped 8 unverified** (no verified_source / verified_on).

**Reference: FDA labeling, checked automatically** (`python scripts/verify_reference_labels.py`, openFDA drug labels fetched 2026-09-29). Each drug's label was searched for the other drug by generic, salt or brand name, and the wording around the match was classified by keyword rules (src/evaluation/label_evidence.py). **The classification is heuristic**, and its rules were refined by reading these same labels, so it is not independently validated. An expected interaction counts as verified only if a label gives guidance (contraindicated, avoid, or monitor/adjust); 8 rows the labels don't settle are excluded and counted as skipped. A negative control counts as verified when neither label names the other drug, which is **only weak evidence** of no interaction.

Label evidence for the verified rows: monitor / adjust 11, contraindicated 11, avoid / not recommended 1, not mentioned 10.

| Outcome | Expected interaction | Negative control |
|---|---:|---:|
| DETECTED | 23 | 0 |
| LISTED_UNGRADED | 0 | 10 |
| NO_DATA | 0 | 0 |
| UNRESOLVED | 0 | 0 |
| SILENT | 0 | 0 |

- Recall (graded): 1.000; including ungraded listings: 1.000.
- Under-triage (PharmGuard's DDInter grade below the reference's minimum): 0 of 23 detected (0.000).
- Silent misses: 0 (must be 0).
- DDInter vs Drugs.com, 0 rows with a Drugs.com grade: exact agreement —, linear-weighted κ — (levels none < Minor < Moderate < Major). Pairs picked for a manual Drugs.com lookup: simvastatin + clarithromycin; warfarin + amiodarone; atorvastatin + lisinopril.

- FDA label vs DDInter grade, 23 verified interactions (label wording mapped contraindicated or avoid -> Major; monitor/adjust -> Moderate (heuristic)): same grade 0.565 of 23; DDInter lower than the label: 0.

| Label wording / DDInter grade | Pairs |
|---|---:|
| avoid / not recommended / Major | 1 |
| contraindicated / Major | 11 |
| monitor / adjust / Major | 10 |
| monitor / adjust / Moderate | 1 |

| Pair | Expected | Min severity | Outcome | PharmGuard grade | Drugs.com |
|---|---|---|---|---|---|
| warfarin + amiodarone | interaction | Moderate | DETECTED | Major | — |
| simvastatin + clarithromycin | interaction | Major | DETECTED | Major | — |
| clopidogrel + omeprazole | interaction | Major | DETECTED | Major | — |
| sildenafil + nitroglycerin | interaction | Major | DETECTED | Major | — |
| linezolid + sertraline | interaction | Major | DETECTED | Major | — |
| lithium + hydrochlorothiazide | interaction | Moderate | DETECTED | Major | — |
| digoxin + amiodarone | interaction | Moderate | DETECTED | Major | — |
| azathioprine + allopurinol | interaction | Moderate | DETECTED | Major | — |
| colchicine + clarithromycin | interaction | Major | DETECTED | Major | — |
| tizanidine + ciprofloxacin | interaction | Major | DETECTED | Major | — |
| warfarin + fluconazole | interaction | Moderate | DETECTED | Major | — |
| simvastatin + itraconazole | interaction | Major | DETECTED | Major | — |
| tramadol + fluoxetine | interaction | Moderate | DETECTED | Major | — |
| phenelzine + fluoxetine | interaction | Major | DETECTED | Major | — |
| carbamazepine + clarithromycin | interaction | Moderate | DETECTED | Major | — |
| tacrolimus + clarithromycin | interaction | Moderate | DETECTED | Major | — |
| mercaptopurine + allopurinol | interaction | Moderate | DETECTED | Major | — |
| pimozide + clarithromycin | interaction | Major | DETECTED | Major | — |
| simvastatin + gemfibrozil | interaction | Major | DETECTED | Major | — |
| ramelteon + fluvoxamine | interaction | Major | DETECTED | Major | — |
| clozapine + fluvoxamine | interaction | Moderate | DETECTED | Moderate | — |
| alprazolam + ketoconazole | interaction | Major | DETECTED | Major | — |
| apixaban + ketoconazole | interaction | Moderate | DETECTED | Major | — |
| acetaminophen + amoxicillin | none | — | LISTED_UNGRADED | — | — |
| atorvastatin + lisinopril | none | — | LISTED_UNGRADED | — | — |
| montelukast + cetirizine | none | — | LISTED_UNGRADED | — | — |
| famotidine + acetaminophen | none | — | LISTED_UNGRADED | — | — |
| loratadine + omeprazole | none | — | LISTED_UNGRADED | — | — |
| levothyroxine + acetaminophen | none | — | LISTED_UNGRADED | — | — |
| pantoprazole + amlodipine | none | — | LISTED_UNGRADED | — | — |
| losartan + acetaminophen | none | — | LISTED_UNGRADED | — | — |
| metformin + amlodipine | none | — | LISTED_UNGRADED | — | — |
| sertraline + acetaminophen | none | — | LISTED_UNGRADED | — | — |
