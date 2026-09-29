# LLM-path evaluation — sample-only (synthetic data)

Regenerate with `python scripts/run_llm_eval.py --profile sample --providers gemini --model gemini-3.5-flash-lite --judge-provider gemini --judge-model gemini-3.5-flash-lite --allow-same-provider-judge --min-interval 5` (2026-09-29). Data: synthetic sample dataset (85 interaction records), not real clinical data. provenance sha256 `28d02174d104970c84783c43b9264e0424e6ce364c3223695f41749ca49a7506`.
Judge prompt `src/evaluation/prompts/judge_v1.txt` sha256 `ce2d0157ac2688a44174b1bc24135788e93303d53ecccbab9bf1f8ea23df41fa`.

**Sample-only.** Every number here comes from the 85-record synthetic sample, not real clinical data; it describes the model's behaviour on this harness, not PharmGuard's accuracy on real drugs.

## Generator gemini:gemini-3.5-flash-lite

57 cases; LLM reports shown: 46. Judge: gemini:gemini-3.5-flash-lite — **same provider as the generator** (allowed by flag; agreement may be inflated).

| Metric | Deterministic template | LLM first draft | LLM report shown |
|---|---:|---:|---:|
| semantic_hallucination_rate | 0.000 | 0.016 | 0.000 |
| uncited_claim_rate | 0.000 | 0.016 | 0.000 |
| citation_validity | 1.000 | 1.000 | 1.000 |
| pair_omission_rate | 0.000 | 0.000 | 0.000 |
| major_omission_rate | 0.000 | 0.000 | 0.000 |
| completeness | 1.000 | 1.000 | 1.000 |
| faithfulness (judge: supported / judged) | 1.000 | — | 1.000 |
| contradicted rate (judge) | 0.000 | — | 0.000 |
| graph latency p50, in-process (ms) | 14.000 | | 4875.700 |

| LLM runs | |
|---|---|
| first-draft pass rate | 91.5% |
| recovery on retry | 75.0% |
| fallback rate | 2.1% |
| tokens per report | 1620.900 |
| top finding codes | [('SEVERITY_ON_STATISTICAL_SIGNAL', 3), ('UNCITED_CLAIM', 2)] |
| report sources | {'llm': 43, 'llm_retry': 3, 'deterministic_insufficient_input': 10, 'deterministic_fallback': 1} |
| LLM errors | — |
| judge calls / invalid judge outputs | 247 / 0 |
| judge tokens | {'input_tokens': 100271, 'output_tokens': 12728} |

## Human audit of the judge

49 judged claims (20%, seed 20260928) exported blind to `results/judge_audit_sample.csv`. Agreement and Cohen's κ: — until a human fills it in (`python scripts/score_judge_audit.py`).
