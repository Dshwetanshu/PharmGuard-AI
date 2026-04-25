# Evaluation Methodology

> If you cannot describe the failure mode that keeps you up at night, you have not thought hard enough about your system.

This doc specifies how PharmGuard is evaluated and, importantly, what counts as failure.

## The silent-failure scenario

The target failure mode — the one the evaluation is engineered to catch — is:

> A patient inputs six medications. The system returns a cleanly formatted report listing four interactions with professional-sounding mechanism descriptions. It looks authoritative. But the system has missed two critical interactions — one classified as *Major* severity in the source database — and has fabricated a CYP3A4 inhibition pathway where the actual mechanism is P-glycoprotein competition.

The output is polished, fluent, and dangerous. Traditional benchmarks miss this because they score confident-sounding language well. PharmGuard's eval deliberately does not.

## Ground truth construction

For each test case, ground truth is derived **programmatically**, not curated:

```
ground_truth(input_drugs) = {
    (a, b) for (a, b) in combinations(normalize(input_drugs), 2)
    if (a, b) exists in the loaded interactions table
}
```

This makes eval self-consistent with whatever dataset was ingested. If you load full TWOSIDES, ground truth is ~all TWOSIDES pairs in your input. If you load only the sample, ground truth is the sample's pairs. The same evaluator code produces meaningful numbers in both cases.

## The six metrics

### 1. Retrieval Recall — target ≥ 95%

`recall = true_positives / (true_positives + false_negatives)`

Fraction of ground-truth interaction pairs that the retriever surfaced. This is the **most important metric**. A missed major interaction is the worst-case outcome; recall measures how often that happens.

### 2. Retrieval Precision — target ≥ 90%

`precision = true_positives / (true_positives + false_positives)`

Since the retriever uses exact-pair lookups (not semantic search), precision should be extremely high by construction. Sub-90% precision would indicate a bug in pair normalization or the interactions index.

### 3. Faithfulness — target ≥ 85%

Does the generated mechanism match the retrieved source record?

**Automated path:** an LLM-judge (separate model instance) compares each generated paragraph against the retrieved record using semantic entailment. See `src/evaluation/metrics.py::count_uncited_claims` for a faster heuristic proxy.

**Human audit:** 20% of cases are manually reviewed. If auto-judge and human score diverge by more than 10 percentage points, the pipeline is recalibrated before reporting final numbers.

### 4. Hallucination Rate — target ≤ 5%

Fraction of clinical claims in the report that cannot be traced to any source record in the retrieval evidence.

Detected via regex: every sentence containing clinical markers (`interaction`, `bleeding`, `QT`, `mechanism`, etc.) must include a `[SOURCE:RECORD_ID]` citation. Uncited clinical claims are candidate hallucinations and flagged for audit.

### 5. Severity Accuracy — target ≥ 90%

Does the generated report's severity tier match the retrieved record's severity field?

### 6. Completeness Flagging — target 100%

For every input pair where the retriever returned no data, does the final report explicitly say "No interaction data available"?

This is a **contract check**, not a learned behavior. The pipeline surfaces `no_data_pairs` by construction — if this ever drops below 100%, it's a bug, not a model failure.

## Running the evaluation

```bash
# All 48 cases
python scripts/run_eval.py --output reports/eval_full.json

# Only geriatric cases
python scripts/run_eval.py --subset GER

# Only drug-textbook cases
python scripts/run_eval.py --subset TXT
```

The JSON output includes per-case breakdown so you can drill into any failure.

## What the evaluation deliberately does NOT measure

- **Clinical appropriateness.** PharmGuard flags an interaction if the source data does. Whether a clinician should act on a Moderate Minor interaction is a judgment call that belongs to the clinician, not the system.
- **Coverage of drugs outside the loaded database.** If TWOSIDES doesn't cover a drug, neither does PharmGuard. This is a data coverage limitation, not an accuracy failure — and it's reported honestly via the `unresolved_inputs` and `no_data_pairs` outputs.
- **Clinical outcomes.** Whether the system *improves patient outcomes* requires a prospective study, not a retrieval benchmark.

## Interpreting the numbers

A 95% recall sounds great until you realize: 5% of major interactions missed, across 1.3M ED visits/year attributed to ADEs, is a very large number of potential harms. That's why the system pairs its metrics with:

- Explicit `no_data_pairs` (not just "silence")
- Source-record citations on every claim (so the clinician can verify)
- Disclaimer on every output

The evaluation philosophy is: **be honest about what you know and what you don't.** A system that scores 92% recall but flags the 8% uncertain pairs as uncertain is clinically safer than one that scores 95% recall but is silent about its gaps.
