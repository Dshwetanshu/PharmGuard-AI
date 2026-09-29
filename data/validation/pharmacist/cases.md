# PharmGuard pharmacist review: cases

Read docs/PHARMACIST_REVIEW_PROTOCOL.md first. Each report below is exactly what PharmGuard returns for the input shown (public build, deterministic mode). Score each one in rubric.csv.

## PR-01

Input, as typed: `warfarin, amiodarone, simvastatin, clarithromycin`

PharmGuard Interaction Report

### How your entries were read
- warfarin → warfarin
- amiodarone → amiodarone
- simvastatin → simvastatin
- clarithromycin → clarithromycin

### Summary
Analyzed 4 medications across 6 unique pairs. Found 6 graded interactions (Major 5, Moderate 0, Minor 1), 0 listings without a severity grade and 0 statistical reporting signals.

### Major Findings
- **amiodarone + clarithromycin** — curated severity: Major (DDInter) [DDInter:DDI-8b3b1d505b]
- **amiodarone + simvastatin** — curated severity: Major (DDInter) [DDInter:DDI-14dc833b9d]
- **amiodarone + warfarin** — curated severity: Major (DDInter) [DDInter:DDI-683b838b25]
- **clarithromycin + simvastatin** — curated severity: Major (DDInter) [DDInter:DDI-b50bbf17be]
- **clarithromycin + warfarin** — curated severity: Major (DDInter) [DDInter:DDI-9fba55f13a]

### Minor Findings
- **simvastatin + warfarin** — curated severity: Minor (DDInter) [DDInter:DDI-97223ae3cc]

### Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

---

## PR-02

Input, as typed: `lisinopril, spironolactone, potassium chloride`

PharmGuard Interaction Report

### How your entries were read
- lisinopril → lisinopril
- spironolactone → spironolactone
- potassium chloride → potassium chloride

### Summary
Analyzed 3 medications across 3 unique pairs. Found 3 graded interactions (Major 3, Moderate 0, Minor 0), 0 listings without a severity grade and 0 statistical reporting signals.

### Major Findings
- **lisinopril + potassium chloride** — curated severity: Major (DDInter) [DDInter:DDI-e37b182237]
- **lisinopril + spironolactone** — curated severity: Major (DDInter) [DDInter:DDI-267de0347b]
- **potassium chloride + spironolactone** — curated severity: Major (DDInter) [DDInter:DDI-654e4af47b]

### Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

---

## PR-03

Input, as typed: `sertraline, tramadol, linezolid`

PharmGuard Interaction Report

### How your entries were read
- sertraline → sertraline
- tramadol → tramadol
- linezolid → linezolid

### Summary
Analyzed 3 medications across 3 unique pairs. Found 3 graded interactions (Major 3, Moderate 0, Minor 0), 0 listings without a severity grade and 0 statistical reporting signals.

### Major Findings
- **linezolid + sertraline** — curated severity: Major (DDInter) [DDInter:DDI-be357c87b8]
- **linezolid + tramadol** — curated severity: Major (DDInter) [DDInter:DDI-20ea46513b]
- **sertraline + tramadol** — curated severity: Major (DDInter) [DDInter:DDI-840b05b96a]

### Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

---

## PR-04

Input, as typed: `lisinopril, spironolactone, metformin, atorvastatin, aspirin, omeprazole, sertraline`

PharmGuard Interaction Report

### How your entries were read
- lisinopril → lisinopril
- spironolactone → spironolactone
- metformin → metformin
- atorvastatin → atorvastatin
- aspirin → aspirin
- omeprazole → omeprazole
- sertraline → sertraline

### Summary
Analyzed 7 medications across 21 unique pairs. Found 9 graded interactions (Major 1, Moderate 6, Minor 2), 12 listings without a severity grade and 0 statistical reporting signals.

### Major Findings
- **lisinopril + spironolactone** — curated severity: Major (DDInter) [DDInter:DDI-267de0347b]

### Moderate Findings
- **aspirin + lisinopril** — curated severity: Moderate (DDInter) [DDInter:DDI-5c4747582b]
- **aspirin + sertraline** — curated severity: Moderate (DDInter) [DDInter:DDI-cdf8ccde8b]
- **atorvastatin + omeprazole** — curated severity: Moderate (DDInter) [DDInter:DDI-ead9feedd4]
- **lisinopril + metformin** — curated severity: Moderate (DDInter) [DDInter:DDI-cd8167557b]
- **metformin + spironolactone** — curated severity: Moderate (DDInter) [DDInter:DDI-d96d408d7e]
- **sertraline + spironolactone** — curated severity: Moderate (DDInter) [DDInter:DDI-897a419cf0]

### Minor Findings
- **aspirin + omeprazole** — curated severity: Minor (DDInter) [DDInter:DDI-2ea6b80981]
- **aspirin + spironolactone** — curated severity: Minor (DDInter) [DDInter:DDI-667245c02c]

### Listed by DDInter without a severity grade
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

### Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

---

## PR-05

Input, as typed: `acetaminophen, levothyroxine, atorvastatin, aspirin`

PharmGuard Interaction Report

### How your entries were read
- acetaminophen → acetaminophen
- levothyroxine → levothyroxine
- atorvastatin → atorvastatin
- aspirin → aspirin

### Summary
Analyzed 4 medications across 6 unique pairs. Found 0 graded interactions (Major 0, Moderate 0, Minor 0), 6 listings without a severity grade and 0 statistical reporting signals.

### Listed by DDInter without a severity grade
DDInter lists these pairs without a severity grade; the loaded data can't say whether they matter clinically.
- **acetaminophen + aspirin** — curated severity: not graded (DDInter) [DDInter:DDI-caac095b8d]
- **acetaminophen + atorvastatin** — curated severity: not graded (DDInter) [DDInter:DDI-0023e15a32]
- **acetaminophen + levothyroxine** — curated severity: not graded (DDInter) [DDInter:DDI-8c1f6243a4]
- **aspirin + atorvastatin** — curated severity: not graded (DDInter) [DDInter:DDI-f7bef6fd81]
- **aspirin + levothyroxine** — curated severity: not graded (DDInter) [DDInter:DDI-149789eafd]
- **atorvastatin + levothyroxine** — curated severity: not graded (DDInter) [DDInter:DDI-ebbaf03855]

### Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

---

## PR-06

Input, as typed: `Coumadin, Diflucan, warfarin`

PharmGuard Interaction Report

### How your entries were read
> **Same drug entered more than once:** Coumadin and warfarin both mean warfarin (possible duplicate therapy). It is analysed once.
- Coumadin → warfarin (brand name, Drugs@FDA)
- Diflucan → fluconazole (brand name)
- warfarin → warfarin

### Summary
Analyzed 2 medications across 1 unique pair. Found 1 graded interaction (Major 1, Moderate 0, Minor 0), 0 listings without a severity grade and 0 statistical reporting signals.

### Major Findings
- **fluconazole + warfarin** — curated severity: Major (DDInter) [DDInter:DDI-d7d2b17f74]

### Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

---

## PR-07

Input, as typed: `Celebyx, warfarin, aspirin`

PharmGuard Interaction Report

### How your entries were read
- Celebyx → not analysed: ambiguous name; closest matches: fosphenytoin (matched cerebyx) / celecoxib (matched celebrex) / citalopram (matched celexa) / doxorubicin (matched caelyx); enter the specific drug
- warfarin → warfarin
- aspirin → aspirin

### Summary
Analyzed 2 medications across 1 unique pair. Found 1 graded interaction (Major 1, Moderate 0, Minor 0), 0 listings without a severity grade and 0 statistical reporting signals.

### Major Findings
- **aspirin + warfarin** — curated severity: Major (DDInter) [DDInter:DDI-3c13283cb3]

### Coverage Notes
### Unresolved Inputs
These inputs could not be matched to a drug in the local vocabulary and were excluded:
- Celebyx — ambiguous name; closest matches: fosphenytoin (matched cerebyx) / celecoxib (matched celebrex) / citalopram (matched celexa) / doxorubicin (matched caelyx); enter the specific drug

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

---

## PR-08

Input, as typed: `insulin, metoprolol, Percocet`

PharmGuard Interaction Report

### How your entries were read
- insulin → not analysed: ambiguous name; matching drugs: insulin, regular, human / insulin aspart, human / insulin lispro / insulin detemir (and 3 more); enter the specific drug
- metoprolol → metoprolol
- Percocet → not analysed: combination product: acetaminophen + oxycodone; enter them separately

### Summary
Analyzed 1 medication across 0 unique pairs. Found 0 graded interactions (Major 0, Moderate 0, Minor 0), 0 listings without a severity grade and 0 statistical reporting signals.

### Coverage Notes
### Unresolved Inputs
These inputs could not be matched to a drug in the local vocabulary and were excluded:
- insulin — ambiguous name; matching drugs: insulin, regular, human / insulin aspart, human / insulin lispro / insulin detemir (and 3 more); enter the specific drug
- Percocet — combination product: acetaminophen + oxycodone; enter them separately

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

---

## PR-09

Input, as typed: `escitalopram, amoxicillin, melatonin`

PharmGuard Interaction Report

### How your entries were read
- escitalopram → escitalopram
- amoxicillin → amoxicillin
- melatonin → melatonin

### Summary
Analyzed 3 medications across 3 unique pairs. Found 0 graded interactions (Major 0, Moderate 0, Minor 0), 0 listings without a severity grade and 0 statistical reporting signals.

### Coverage Notes
### No Curated Interaction Data
No record in the queried curated sources for these 3 pairs. Absence of a record does not mean the combination is safe.
- amoxicillin + escitalopram
- amoxicillin + melatonin
- escitalopram + melatonin

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

---

## PR-10

Input, as typed: `metfromin, lisonopril, ibuprofen, Lasix`

PharmGuard Interaction Report

### How your entries were read
- metfromin → metformin (spelling match: check this)
- lisonopril → lisinopril (spelling match: check this)
- ibuprofen → ibuprofen
- Lasix → furosemide (brand name)

### Summary
Analyzed 4 medications across 6 unique pairs. Found 6 graded interactions (Major 0, Moderate 6, Minor 0), 0 listings without a severity grade and 0 statistical reporting signals.

### Moderate Findings
- **furosemide + ibuprofen** — curated severity: Moderate (DDInter) [DDInter:DDI-7be13db145]
- **furosemide + lisinopril** — curated severity: Moderate (DDInter) [DDInter:DDI-5e36955e28]
- **furosemide + metformin** — curated severity: Moderate (DDInter) [DDInter:DDI-3ff608f109]
- **ibuprofen + lisinopril** — curated severity: Moderate (DDInter) [DDInter:DDI-d277686aa8]
- **ibuprofen + metformin** — curated severity: Moderate (DDInter) [DDInter:DDI-b0aad68886]
- **lisinopril + metformin** — curated severity: Moderate (DDInter) [DDInter:DDI-cd8167557b]

### Coverage Notes
All entries were recognized, and each pair has a record in the loaded data.

---
**Disclaimer.** PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. It reports only what its loaded data contains; absence of data is not evidence of safety.

Data: public build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,673 interaction records; not synthetic.

---
