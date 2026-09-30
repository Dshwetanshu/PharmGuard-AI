# LLM judge on the checker's injected faults (synthetic fixtures)

Regenerate with `python scripts/judge_checker_faults.py --provider gemini --model gemini-3.5-flash-lite --min-interval 5` (2026-09-30). Judge `gemini:gemini-3.5-flash-lite`, prompt `src/evaluation/prompts/judge_v1.txt` sha256 `ce2d0157ac2688a44174b1bc24135788e93303d53ecccbab9bf1f8ea23df41fa`. Data: the synthetic FX- fixture records of `src/evaluation/checker_fixtures.py`; no real data. No generator is involved: the reports are fixture templates with faults injected by code.

**Known-bad claims** are the cited claims an injected fault changed, located on the line where the checker raises that fault's code (the fault is known by construction; the checker only locates it). The judge sees one claim and its cited records, nothing else. These faults use the checker's own lexicon terms, so this is a sanity check on synthetic data, not an estimate of how many real LLM errors the judge catches.

- **Known-bad claims rated unsupported or contradicted: 165/181 (91.2%)** (unsupported 101, contradicted 64, supported 16, invalid output 0).
- Plus 37 phantom-citation claims rated unsupported without a call (they cite no record in the evidence).
- Blind-spot probes (missed by the lexicon checker) rated unsupported or contradicted: 10/10 (100.0%).
- Control, clean fixture claims rated supported: 43/43 (100.0%).
- Judge prompts: 234 (234 answered from the response cache of an earlier run of this script); tokens: {'input_tokens': 93035, 'output_tokens': 11107}.

| Fault | Known-bad claims judged | Unsupported | Contradicted | Supported (missed) | Invalid |
|---|---:|---:|---:|---:|---:|
| mechanism_injection | 32 | 29 | 3 | 0 | 0 |
| canonical_pgp_to_cyp3a4 | 2 | 0 | 2 | 0 | 0 |
| severity_flip | 5 | 1 | 4 | 0 | 0 |
| citation_swap | 34 | 20 | 14 | 0 | 0 |
| prr_distortion | 22 | 0 | 22 | 0 | 0 |
| event_swap | 32 | 7 | 19 | 6 | 0 |
| population_injection | 32 | 32 | 0 | 0 | 0 |
| severity_on_signal | 22 | 12 | 0 | 10 | 0 |
| blind spot: mechanism outside lexicon ('hepatic enzyme blockade') | 2 | 2 | 0 | 0 | 0 |
| blind spot: population outside lexicon ('patients over 80') | 2 | 2 | 0 | 0 | 0 |
| blind spot: unquantified magnitude ('risk roughly triples') | 2 | 2 | 0 | 0 | 0 |
| blind spot: event outside lexicon ('muscle breakdown') | 2 | 0 | 2 | 0 | 0 |
| blind spot: reversed direction ('lowering digoxin levels') | 2 | 0 | 2 | 0 | 0 |

Not judgeable per claim (no changed cited claim to show the judge), injections: severity_flip 5, omitted_major 6, absence_as_safety 18, uncited_claim 32, faers_as_curated 6, severity_on_signal 6, missing_hidden_count 4.

## Known-bad claims the judge called supported (16)

- `severity_on_signal` (template, FX-0002 + 'Major severity'): clarithromycin + simvastatin — rhabdomyolysis: PRR 19.70, co-reports n/a; Major severity → **supported**: The cited record supports the drug pair (clarithromycin + simvastatin), the event (rhabdomyolysis), and the PRR (19.70). The mention of 'Major severity' and 'co-reports n/a' do not contradict the data and are standard formatting or missing field handling.
- `severity_on_signal` (template, FX-0005 + 'clinically significant'): metformin + verapamil — hypoglycemia: PRR 2.40, co-reports n/a, clinically significant → **supported**: The claimed drugs (metformin, verapamil), event (hypoglycemia), and PRR (2.40) are all explicitly stated in the cited record [TWOSIDES:FX-0005].
- `event_swap` (template, FX-0101 'prolonged prothrombin time'->'increased anticoagulant effect'): amiodarone + warfarin — increased anticoagulant effect: PRR 11.20, co-reports n/a → **supported**: The claim correctly reflects the drugs, the effect of increased anticoagulant effect via prolonged prothrombin time, and the PRR of 11.20 stated in the cited record.
- `event_swap` (template, FX-0102 'increased anticoagulant effect'->'prolonged prothrombin time'): amiodarone + warfarin — curated severity: Major (DDInter); prolonged prothrombin time; source mechanism: "Amiodarone inhibits CYP2C9 and CYP3A4 metabolism of warfarin" → **supported**: The claim accurately reflects the severity, mechanism, and drugs stated in the cited record [DDInter:FX-0102], and includes the clinical event of prolonged prothrombin time representing the increased anticoagulant effect.
- `event_swap` (template, FX-0106 'INR increased'->'prolonged prothrombin time'): amiodarone + warfarin — prolonged prothrombin time: PRR 9.40, co-reports n/a → **supported**: The claim of amiodarone + warfarin leading to prolonged prothrombin time (INR increased) with a PRR of 9.40 is directly supported by the cited TWOSIDES record.
- `severity_on_signal` (template, FX-0106 + 'a serious risk'): amiodarone + warfarin — INR increased: PRR 9.40, co-reports n/a, a serious risk → **supported**: The claim that amiodarone and warfarin lead to INR increased with a PRR of 9.40 and are a serious risk is supported by the cited TWOSIDES record indicating a signal for INR increased with a PRR of 9.4.
- `severity_on_signal` (template, FX-0203 + 'a serious risk'): lisinopril + lithium — lithium toxicity: PRR 4.40, co-reports n/a, a serious risk → **supported**: The claim matches the cited TWOSIDES record for lisinopril and lithium, including the event and PRR of 4.40.
- `severity_on_signal` (template, FX-0204 + 'clinically significant'): hydrochlorothiazide + lithium — lithium toxicity: PRR 16.80, co-reports n/a, clinically significant → **supported**: The claim correctly states the drugs (hydrochlorothiazide + lithium), the event (lithium toxicity), and the PRR (16.80, which matches 16.8 in the source record).
- `severity_on_signal` (prose, FX-0003 + 'a serious risk'): Co-reports of Clarithromycin and digoxin show a disproportionality signal for digoxin toxicity (PRR 6.1), a serious risk . → **supported**: The cited record confirms the co-reports of clarithromycin and digoxin show a signal for digoxin toxicity with a PRR of 6.1.
- `event_swap` (prose, FX-0102 'increased anticoagulant effect'->'prolonged prothrombin time'): Amiodarone with warfarin: prolonged prothrombin time . → **supported**: The claim states 'prolonged prothrombin time', which directly follows from the cited record's event of 'increased anticoagulant effect' for the drug pair amiodarone and warfarin.
- `event_swap` (prose, FX-0105 'interaction'->'prolonged prothrombin time'): Cipro (ciprofloxacin) with warfarin: prolonged prothrombin time . → **supported**: The cited record states that ciprofloxacin and warfarin interact with the mechanism that ciprofloxacin may increase INR, which directly supports the claim of prolonged prothrombin time.
- `event_swap` (prose, FX-0106 'INR increased'->'prolonged prothrombin time'): Co-reports of Amiodarone and warfarin show a disproportionality signal for prolonged prothrombin time (PRR 9.4) . → **supported**: The cited record confirms the drug pair amiodarone and warfarin, the event of prolonged prothrombin time (INR increased), and a PRR of 9.4.
- `severity_on_signal` (prose, FX-0106 + 'a serious risk'): Co-reports of Amiodarone and warfarin show a disproportionality signal for INR increased (PRR 9.4), a serious risk . → **supported**: The cited record confirms the co-report of amiodarone and warfarin for the event 'INR increased' with a PRR of 9.4.
- `severity_on_signal` (prose, FX-0103 + 'moderate interaction'): Co-reports of Amiodarone and ciprofloxacin show a disproportionality signal for QT prolongation (PRR 11.8) (moderate interaction) . → **supported**: The cited record confirms the drugs amiodarone and ciprofloxacin, the event QT prolongation, and the PRR of 11.8. The descriptor 'moderate interaction' is considered formatting/classification and does not contradict the record.
- `severity_on_signal` (prose, FX-0203 + 'a serious risk'): Lisinopril with lithium: reporting signal for lithium toxicity, PRR 4.4, a serious risk . → **supported**: The cited record confirms the drug pair lisinopril and lithium, the event lithium toxicity, the signal designation, and the PRR of 4.4.
- `severity_on_signal` (prose, FX-0204 + 'clinically significant'): Co-reports of Hctz (hydrochlorothiazide) and lithium show a disproportionality signal for lithium toxicity (PRR 16.8), clinically significant . → **supported**: The cited record confirms the co-reports of hydrochlorothiazide and lithium show a signal for lithium toxicity with a PRR of 16.8.

## Clean claims the judge did not call supported (0)

