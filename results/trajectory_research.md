# Trajectory evaluation (research build)

Regenerate with `python scripts/eval_trajectory.py --fault-suite --seeded-bugs --profile research`. Offline, no API keys, the real **research** build (Data: research build from RxNorm Current Prescribable 2026-09-08, DDInter 2.0, SIDER 4.1, TWOSIDES (research only; not for redistribution); 634,582 interaction records; not synthetic; provenance sha256 `070bf71c28c706bbf53cc4e260e4f62591dd3ed396565d817a743ef755b8a2b3`), 48 cases. LLM mode with a real model: **—** (no API key); LLM behaviour is exercised with scripted fake LLMs.

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

Failing cases: 0 (details kept local)

Suspected label errors, counted separately (not failures): 0 (details kept local)

Source gaps (labelled pair in no loaded table; not retrieval failures): 1 (details kept local)

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

Failing cases: 0 (details kept local)

Suspected label errors, counted separately (not failures): 0 (details kept local)

Source gaps (labelled pair in no loaded table; not retrieval failures): 1 (details kept local)

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
| MH-02 | `lithium` | resolves to `lithium` |
| MH-05 | `lithium` | resolves to `lithium` |
| MH-05 | `valproic acid` | resolves to `valproate` |
| END-02 | `insulin` | public profile: stays unresolved |
| END-02 | `insulin` | research profile: stays unresolved |

All other inputs are expected to resolve. Suspected label errors (unchanged, for review): EDG-03 [('atorvastatin', 'lisinopril')]

## Fault suite (scripted fake LLMs)

629 runs over 48 cases; scenarios skipped where the fault doesn't apply: {'absence_safe_once': 48, 'signal_severity_once': 5, 'omit_major_once': 17, 'mechanism_once': 3, 'mechanism_always': 3, 'phantom_citation_once': 3, 'severity_flip_once': 3, 'uncited_claim_once': 3, 'different_fault_on_retry': 3, 'retry_repeats_rejected_draft': 3}.

| Scenario | Runs | Expected report_source | Path match | Source match | All invariants | LLM calls/run |
|---|---:|---|---:|---:|---:|---:|
| clean | 48 | llm | 100.0% | 100.0% | 100.0% | 0.938 |
| clean+faers | 48 | llm | 100.0% | 100.0% | 100.0% | 0.938 |
| transient_error_once | 48 | llm_retry | 100.0% | 100.0% | 100.0% | 1.875 |
| transient_error_always | 48 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 1.875 |
| non_transient_error_once | 48 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 0.938 |
| mechanism_once | 45 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| mechanism_always | 45 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 2 |
| omit_major_once | 31 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| phantom_citation_once | 45 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| severity_flip_once | 45 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| uncited_claim_once | 45 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| signal_severity_once | 43 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| different_fault_on_retry | 45 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 2 |
| retry_repeats_rejected_draft | 45 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 2 |

Path match 100.0% · report_source match 100.0% · recovery within the retry budget 100.0% · LLM calls per case 1.738

## Invariants (725 runs: step scoring + fault suite)

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

## Latency: orchestration overhead only (fake LLMs, research build, no network)

| Node | p50 ms | p95 ms |
|---|---:|---:|
| finalize | 0.64 | 12.66 |
| generate_llm | 0.05 | 0.33 |
| normalize | 0.03 | 0.1 |
| plan | 0.03 | 0.1 |
| retrieve | 10.97 | 49.59 |
| template | 0.04 | 1.52 |
| validate | 0.78 | 14.68 |
| **end to end** | 15.7 | 94.3 |

## Seeded orchestration bugs (validating the evaluation)

| Seeded bug | Caught | Invariants broken (pass rate under the bug) | Path match |
|---|---|---|---:|
| validate_always_passes | yes | `no_unvalidated_llm_text` (38.2%), `final_report_valid` (38.2%) | 38.2% |
| retry_limit_off_by_one | yes | `llm_attempts_within_budget` (71.4%) | 71.4% |
| fallback_returns_rejected_draft | yes | `no_unvalidated_llm_text` (78.5%), `exhausted_fallback_matches_deterministic` (78.5%), `final_report_valid` (78.5%) | 100.0% |
| faers_always_consulted | yes | `faers_only_when_needed` (2.4%) | 2.4% |
| plan_drops_a_pair | yes | `plan_complete` (2.4%), `exhausted_fallback_matches_deterministic` (6.4%) | 38.2% |
| non_transient_errors_retried | yes | `non_transient_never_retried` (92.8%) | 92.8% |

Gate: min invariant pass rate 100.0% (threshold 100.0%) → **PASS**
