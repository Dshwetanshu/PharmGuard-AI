# Trajectory evaluation (research build)

Regenerate with `python scripts/eval_trajectory.py --fault-suite --seeded-bugs --profile research`. Offline, no API keys, the real **research** build (Data: research build from RxNorm Current Prescribable 2026-09-08, Drugs@FDA brand names, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1, TWOSIDES (research only; not for redistribution); 634,721 interaction records; not synthetic; provenance sha256 `73a84f12af814416c14bfccf5c8f02b0cda98081fcbfd81aa2b9f3f64e2c0ddd`), 57 cases. LLM mode with a real model: **—** (no API key); LLM behaviour is exercised with scripted fake LLMs.

## Step scoring: deterministic

| Subset | Cases | normalize | plan | retrieve | route | finalize | **completion** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **all** | 57 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| CV | 5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| EDG | 7 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| END | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| GER | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| GI | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| ID | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| LA | 9 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| MH | 5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| ONC | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| PAIN | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| REAL | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| RSP | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| TXT | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |

Failing cases: 0 (details kept local)

Suspected label errors, counted separately (not failures): 0 (details kept local)

Source gaps (labelled pair in no loaded table; not retrieval failures): 0 (details kept local)

## Step scoring: llm_mode_without_key

| Subset | Cases | normalize | plan | retrieve | route | finalize | **completion** |
|---|---:|---:|---:|---:|---:|---:|---:|
| **all** | 57 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| CV | 5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| EDG | 7 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| END | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| GER | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| GI | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| ID | 4 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| LA | 9 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| MH | 5 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| ONC | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| PAIN | 3 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| REAL | 1 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| RSP | 2 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |
| TXT | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0%** |

Failing cases: 0 (details kept local)

Suspected label errors, counted separately (not failures): 0 (details kept local)

Source gaps (labelled pair in no loaded table; not retrieval failures): 0 (details kept local)

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
| END-02 | `insulin glargine` | sample profile: stays unresolved |
| LA-01 | `Coumadin` | resolves to `warfarin` |
| LA-01 | `Diflucan` | resolves to `fluconazole` |
| LA-01 | `Diflucan` | sample profile: stays unresolved |
| LA-02 | `Lanoxin` | resolves to `digoxin` |
| LA-02 | `Lanoxin` | sample profile: stays unresolved |
| LA-03 | `Celebrex` | resolves to `celecoxib` |
| LA-03 | `Celebrex` | sample profile: stays unresolved |
| LA-04 | `Cerebyx` | resolves to `fosphenytoin` |
| LA-04 | `Cerebyx` | sample profile: stays unresolved |
| LA-05 | `Klonopin` | resolves to `clonazepam` |
| LA-05 | `Klonopin` | sample profile: stays unresolved |
| LA-06 | `Coumadin` | resolves to `warfarin` |
| LA-06 | `Diflucan` | resolves to `fluconazole` |
| LA-06 | `Diflucan` | sample profile: stays unresolved |
| LA-07 | `Celebyx` | stays unresolved |
| LA-08 | `Biaxin` | resolves to `clarithromycin` |
| LA-09 | `insulin` | public profile: stays unresolved |
| LA-09 | `insulin` | research profile: stays unresolved |

All other inputs are expected to resolve. Suspected label errors (unchanged, for review): 

## Fault suite (scripted fake LLMs)

742 runs over 57 cases; scenarios skipped where the fault doesn't apply: {'absence_safe_once': 57, 'signal_severity_once': 7, 'omit_major_once': 21, 'mechanism_once': 4, 'mechanism_always': 4, 'phantom_citation_once': 4, 'severity_flip_once': 4, 'uncited_claim_once': 4, 'different_fault_on_retry': 4, 'retry_repeats_rejected_draft': 4}.

| Scenario | Runs | Expected report_source | Path match | Source match | All invariants | LLM calls/run |
|---|---:|---|---:|---:|---:|---:|
| clean+faers | 57 | llm | 100.0% | 100.0% | 100.0% | 0.93 |
| clean | 57 | llm | 100.0% | 100.0% | 100.0% | 0.93 |
| transient_error_once | 57 | llm_retry | 100.0% | 100.0% | 100.0% | 1.86 |
| transient_error_always | 57 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 1.86 |
| non_transient_error_once | 57 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 0.93 |
| mechanism_once | 53 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| mechanism_always | 53 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 2 |
| omit_major_once | 36 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| phantom_citation_once | 53 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| severity_flip_once | 53 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| uncited_claim_once | 53 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| signal_severity_once | 50 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| different_fault_on_retry | 53 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 2 |
| retry_repeats_rejected_draft | 53 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 2 |

Path match 100.0% · report_source match 100.0% · recovery within the retry budget 100.0% · LLM calls per case 1.732

## Invariants (856 runs: step scoring + fault suite)

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
| finalize | 0.78 | 13.57 |
| generate_llm | 0.08 | 0.35 |
| normalize | 0.03 | 0.13 |
| plan | 0.05 | 0.15 |
| retrieve | 11.49 | 48.41 |
| template | 0.13 | 2.2 |
| validate | 1.03 | 13.91 |
| **end to end** | 16.8 | 93.9 |

## Seeded orchestration bugs (validating the evaluation)

| Seeded bug | Caught | Invariants broken (pass rate under the bug) | Path match |
|---|---|---|---:|
| validate_always_passes | yes | `no_unvalidated_llm_text` (38.4%), `final_report_valid` (38.4%) | 38.4% |
| retry_limit_off_by_one | yes | `llm_attempts_within_budget` (71.4%) | 71.4% |
| fallback_returns_rejected_draft | yes | `no_unvalidated_llm_text` (78.6%), `exhausted_fallback_matches_deterministic` (78.6%), `final_report_valid` (78.6%) | 100.0% |
| faers_always_consulted | yes | `faers_only_when_needed` (2.7%) | 2.7% |
| plan_drops_a_pair | yes | `plan_complete` (2.7%), `exhausted_fallback_matches_deterministic` (6.5%) | 38.4% |
| non_transient_errors_retried | yes | `non_transient_never_retried` (92.9%) | 92.9% |

Gate: min invariant pass rate 100.0% (threshold 100.0%) → **PASS**
