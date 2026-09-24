# Trajectory evaluation (public build)

Regenerate with `python scripts/eval_trajectory.py --fault-suite --seeded-bugs --profile public`. Offline, no API keys, the real **public** build (Data: public build from RxNorm Current Prescribable 2026-09-08, DDInter bulk download (ddinter2.scbdd.com, 2024-05-21), SIDER 4.1; 169,534 interaction records; not synthetic; provenance sha256 `d459af5d62bc3110875ab7e30b8ef4a996bae79b2d5353eab0544ff521560d14`), 48 cases. LLM mode with a real model: **—** (no API key); LLM behaviour is exercised with scripted fake LLMs.

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

Suspected label errors, counted separately (not failures): none

Source gaps (labelled pair in no loaded table; not retrieval failures): END-02 [['insulin', 'metoprolol']]

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

Suspected label errors, counted separately (not failures): none

Source gaps (labelled pair in no loaded table; not retrieval failures): END-02 [['insulin', 'metoprolol']]

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

586 runs over 48 cases; scenarios skipped where the fault doesn't apply: {'absence_safe_once': 48, 'signal_severity_once': 48, 'omit_major_once': 17, 'mechanism_once': 3, 'mechanism_always': 3, 'phantom_citation_once': 3, 'severity_flip_once': 3, 'uncited_claim_once': 3, 'different_fault_on_retry': 3, 'retry_repeats_rejected_draft': 3}.

| Scenario | Runs | Expected report_source | Path match | Source match | All invariants | LLM calls/run |
|---|---:|---|---:|---:|---:|---:|
| clean+faers | 48 | llm | 100.0% | 100.0% | 100.0% | 0.938 |
| clean | 48 | llm | 100.0% | 100.0% | 100.0% | 0.938 |
| transient_error_once | 48 | llm_retry | 100.0% | 100.0% | 100.0% | 1.875 |
| transient_error_always | 48 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 1.875 |
| non_transient_error_once | 48 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 0.938 |
| mechanism_once | 45 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| mechanism_always | 45 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 2 |
| omit_major_once | 31 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| phantom_citation_once | 45 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| severity_flip_once | 45 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| uncited_claim_once | 45 | llm_retry | 100.0% | 100.0% | 100.0% | 2 |
| different_fault_on_retry | 45 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 2 |
| retry_repeats_rejected_draft | 45 | deterministic_fallback | 100.0% | 100.0% | 100.0% | 2 |

Path match 100.0% · report_source match 100.0% · recovery within the retry budget 100.0% · LLM calls per case 1.718

## Invariants (682 runs: step scoring + fault suite)

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

## Latency: orchestration overhead only (fake LLMs, public build, no network)

| Node | p50 ms | p95 ms |
|---|---:|---:|
| finalize | 0.27 | 2.82 |
| generate_llm | 0.04 | 0.12 |
| normalize | 0.03 | 0.1 |
| plan | 0.03 | 0.09 |
| retrieve | 10.56 | 45.71 |
| template | 0.03 | 1.53 |
| validate | 0.35 | 3.51 |
| **end to end** | 14.0 | 55.8 |

## Seeded orchestration bugs (validating the evaluation)

| Seeded bug | Caught | Invariants broken (pass rate under the bug) | Path match |
|---|---|---|---:|
| validate_always_passes | yes | `no_unvalidated_llm_text` (41.0%), `final_report_valid` (41.0%) | 41.0% |
| retry_limit_off_by_one | yes | `llm_attempts_within_budget` (69.3%) | 69.3% |
| fallback_returns_rejected_draft | yes | `no_unvalidated_llm_text` (77.0%), `exhausted_fallback_matches_deterministic` (77.0%), `final_report_valid` (77.0%) | 100.0% |
| faers_always_consulted | yes | `faers_only_when_needed` (2.6%) | 2.6% |
| plan_drops_a_pair | yes | `plan_complete` (2.6%), `exhausted_fallback_matches_deterministic` (6.8%) | 41.0% |
| non_transient_errors_retried | yes | `non_transient_never_retried` (92.3%) | 92.3% |

Gate: min invariant pass rate 100.0% (threshold 100.0%) → **PASS**
