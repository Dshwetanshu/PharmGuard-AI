# Report checker validation

Regenerate with `python scripts/validate_checker.py`. Offline, no API key; all data is synthetic (sample CSVs for the 56 cases, `FX-` fixture records for fault injection).

The mechanism, event and population checks use hand-written lexicons, so detection is a **lower bound**: the blind-spot probes below are fabrications the checker is known to miss. An LLM judge is planned as a later layer.

## False positives (clean reports; target 0)

| Report set | Reports | Clinical claims checked | Reports with findings | Findings |
|---|---:|---:|---:|---:|
| Template, 56 evaluation cases (sample data) | 56 | 124 | 0 | 0 |
| Fixtures, template style | 3 | 19 | 0 | 0 |
| Fixtures, prose style | 3 | 24 | 0 | 0 |

## Sensitivity (injected faults on FX- fixtures)

Detection = the expected finding code is raised. These rates show each check works on the fault it targets. They are **not** an estimate of how many real LLM errors are caught: the injected faults use terms from the checker's own lexicons by construction, and the fixtures are small (3 scenarios, 17 records).

| Fault | Expected code | template: detected / injected | prose: detected / injected |
|---|---|---:|---:|
| mechanism_injection | `UNSUPPORTED_MECHANISM` | 16/16 (100%) | 16/16 (100%) |
| canonical_pgp_to_cyp3a4 | `UNSUPPORTED_MECHANISM` | 1/1 (100%) | 1/1 (100%) |
| severity_flip | `SEVERITY_MISMATCH` | 5/5 (100%) | 5/5 (100%) |
| citation_swap | `MISATTRIBUTED_CITATION` | 15/15 (100%) | 15/15 (100%) |
| phantom_citation | `PHANTOM_CITATION` | 16/16 (100%) | 16/16 (100%) |
| prr_distortion | `NUMERIC_MISMATCH` | 11/11 (100%) | 11/11 (100%) |
| omitted_major | `OMITTED_MAJOR` | 3/3 (100%) | 3/3 (100%) |
| absence_as_safety | `CONFLATED_ABSENCE` | 9/9 (100%) | 9/9 (100%) |
| event_swap | `EVENT_MISATTRIBUTION` | 16/16 (100%) | 16/16 (100%) |
| population_injection | `UNSUPPORTED_POPULATION` | 16/16 (100%) | 16/16 (100%) |
| uncited_claim | `UNCITED_CLAIM` | 16/16 (100%) | 16/16 (100%) |
| faers_as_curated | `FAERS_AS_CURATED` | 3/3 (100%) | 3/3 (100%) |
| severity_on_signal | `SEVERITY_ON_STATISTICAL_SIGNAL` | 14/14 (100%) | 14/14 (100%) |
| missing_hidden_count | `MISSING_HIDDEN_COUNT` | 2/2 (100%) | 2/2 (100%) |

## Blind-spot probes (expected to be missed)

| Probe | template: caught? | prose: caught? |
|---|---|---|
| mechanism outside lexicon ('hepatic enzyme blockade') | no | no |
| population outside lexicon ('patients over 80') | no | no |
| unquantified magnitude ('risk roughly triples') | no | no |
| event outside lexicon ('muscle breakdown') | no | no |
| reversed direction ('lowering digoxin levels') | no | no |

The canonical case (`canonical_pgp_to_cyp3a4`): fixture record `FX-0001` says "Verapamil inhibits P-glycoprotein, raising digoxin levels"; the mutated report claims CYP3A4 with the same, real citation.
