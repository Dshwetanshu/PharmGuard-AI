# Trajectory evaluation

Regenerate with `python scripts/eval_trajectory.py --fault-suite --seeded-bugs --min-invariant-pass 1.0`. Offline, no API keys, synthetic sample data (48 cases). LLM mode with a real model: **—** (no API key); LLM behaviour is exercised with scripted fake LLMs.

## Step scoring: deterministic

| Subset | Cases | normalize | plan | retrieve | route | finalize | **completion** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **all** | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| CV | 5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| EDG | 7 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| END | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| GER | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| GI | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| ID | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| MH | 5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| ONC | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| PAIN | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| REAL | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| RSP | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| TXT | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |

Failing cases: none

Suspected label errors, counted separately (not failures): EDG-03 [['atorvastatin', 'lisinopril']]

## Step scoring: llm_mode_without_key

| Subset | Cases | normalize | plan | retrieve | route | finalize | **completion** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **all** | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| CV | 5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| EDG | 7 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| END | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| GER | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| GI | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| ID | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| MH | 5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| ONC | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| PAIN | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| REAL | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| RSP | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| TXT | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |

Failing cases: none

Suspected label errors, counted separately (not failures): EDG-03 [['atorvastatin', 'lisinopril']]

## Step scoring: llm_mode_with_key

— (no API key configured)

## Normalizer expectations added (for review)

| Case | Input | Expected |
|---|---|---|
| EDG-03 | `Lipitor` | resolves to `atorvastatin` |
| EDG-03 | `Prinivil` | resolves to `lisinopril` |
| EDG-04 | `  METFORMIN  ` | resolves to `metformin` |
| EDG-04 | `Lisinopril` | resolves to `lisinopril` |
| EDG-05 | `metfromin` | resolves to `metformin` |
| EDG-05 | `lisonopril` | resolves to `lisinopril` |
| EDG-06 | `lisinopril` | resolves to `lisinopril` |
| EDG-06 | `fictional_drug_xyz` | stays unresolved |
| MH-02 | `lithium` | resolves to `lithium carbonate` |
| MH-05 | `lithium` | resolves to `lithium carbonate` |
| MH-05 | `valproic acid` | resolves to `valproic acid` |

All other inputs are expected to resolve. Suspected label errors (unchanged, for review): EDG-03 [('atorvastatin', 'lisinopril')]

## Fault suite (scripted fake LLMs)

549 runs over 48 cases; scenarios skipped where the fault doesn't apply: {'omit_major_once': 24, 'absence_safe_once': 29, 'mechanism_once': 10, 'mechanism_always': 10, 'phantom_citation_once': 10, 'severity_flip_once': 10, 'uncited_claim_once': 10, 'different_fault_on_retry': 10, 'retry_repeats_rejected_draft': 10}.

| Scenario | Runs | Expected report_source | Path match | Source match | All invariants | LLM calls/run |
|---|---:|---|---:|---:|---:|---:|
| clean+faers | 48 | llm | 100.0% | 100.0% | 100.0% | 0.958 |
| clean | 48 | llm | 100.0% | 100.0% | 100.0% | 0.958 |
| transient_error_once | 48 | llm_retry | 100.0% | 100.0% | 100.0% | 1.917 |
| transient_error_always | 48 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 1.917 |
| non_transient_error_once | 48 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 0.958 |
| mechanism_once | 38 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| mechanism_always | 38 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 2 |
| omit_major_once | 24 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| absence_safe_once | 19 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| phantom_citation_once | 38 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| severity_flip_once | 38 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| uncited_claim_once | 38 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| different_fault_on_retry | 38 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 2 |
| retry_repeats_rejected_draft | 38 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 2 |

Path match 100.0% · report_source match 100.0% · recovery within the retry budget 100.0% · LLM calls per case 1.712

## Invariants (645 runs: step scoring + fault suite)

| Invariant | Pass rate |
|---|---:|
| ends_at_finalize | 100.0% |
| plan_complete | 100.0% |
| partition_holds | 100.0% |
| faers_only_when_needed | 100.0% |
| llm_attempts_within_budget | 100.0% |
| non_transient_never_retried | 100.0% |
| no_unvalidated_llm_text | 100.0% |
| exhausted_fallback_matches_deterministic | 100.0% |
| final_report_valid | 100.0% |
| every_node_timed | 100.0% |
| state_json_serializable | 100.0% |

## Latency: orchestration overhead only (fake LLMs, synthetic sample data, no network)

| Node | p50 ms | p95 ms |
|---|---:|---:|
| faers | 0.19 | 0.93 |
| finalize | 1.53 | 25.52 |
| generate_llm | 0.03 | 0.09 |
| normalize | 0.02 | 0.09 |
| plan | 0.03 | 0.13 |
| retrieve | 2.88 | 26.38 |
| template | 0.02 | 0.07 |
| validate | 1.58 | 25.65 |
| **end to end** | 9.7 | 60.0 |

## Seeded orchestration bugs (validating the evaluation)

| Seeded bug | Caught | Invariants broken (pass rate under the bug) | Path match |
|---|---|---|---:|
| validate_always_passes | yes | `no_unvalidated_llm_text` (43.7%), `final_report_valid` (43.7%) | 43.7% |
| retry_limit_off_by_one | yes | `llm_attempts_within_budget` (70.9%) | 70.9% |
| fallback_returns_rejected_draft | yes | `no_unvalidated_llm_text` (79.2%), `exhausted_fallback_matches_deterministic` (79.2%), `final_report_valid` (79.2%) | 100.0% |
| faers_always_consulted | yes | `faers_only_when_needed` (5.3%) | 5.3% |
| plan_drops_a_pair | yes | `plan_complete` (1.8%), `exhausted_fallback_matches_deterministic` (18.9%) | 50.8% |
| non_transient_errors_retried | yes | `non_transient_never_retried` (91.6%) | 91.6% |

Gate: min invariant pass rate 100.0% (threshold 100.0%) → **PASS**
