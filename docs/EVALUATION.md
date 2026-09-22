# Evaluation Methodology

> If you cannot describe the failure mode that keeps you up at night, you have not thought hard enough about your system.

This doc says how PharmGuard is evaluated, what is actually measured today, and what is not. All numbers below come from running the code in this repository on the **synthetic sample data** (85 interaction records). None come from the real TWOSIDES, DDInter or SIDER releases, which have not been ingested. Unmeasured values are shown as "—".

## The silent-failure scenario

The target failure mode is:

> A patient inputs six medications. The system returns a cleanly formatted report listing four interactions with professional-sounding mechanism descriptions. It looks authoritative. But the system has missed two critical interactions, one classified as *Major* severity in the source database, and has fabricated a CYP3A4 inhibition pathway where the actual mechanism is P-glycoprotein competition.

Counting citations can't catch this: the fabricated sentence can carry a real citation. So PharmGuard checks each claim against the record it cites (see *Report checks* below). The same checker runs as a runtime guardrail: an LLM report that fails it is never shown, and the deterministic template report is returned instead.

## Test cases

`src/evaluation/test_cases.py` defines 48 cases across 12 groups (geriatric, textbook interactions, edge cases, mental health, cardiology, endocrine, infectious disease, oncology-adjacent, pain, respiratory, GI, a 10-drug profile). Each case has hand-written `known_interaction_pairs`. The labels are partial: 14 cases list none, and some labels are suspected to be wrong. Suspected errors are flagged for review, not edited.

## Retrieval metrics

### Internal consistency (recall / precision)

Ground truth = every input pair present in the loaded interaction table, derived with **the same normalizer and table the retriever uses**. Recall and precision are therefore 1.0 **by construction**. This only catches bugs in pair enumeration and lookup plumbing. It scored 1.0 while lithium + hydrochlorothiazide (Major) was reported as "no data" because of a lithium / lithium carbonate key mismatch.

### Hand labels

Retrieval is scored against `known_interaction_pairs`, with labels mapped to canonical names by exact vocabulary alias only (`src/evaluation/hand_labels.py`). Precision is a lower bound because the labels are partial.

## Report checks (`src/verification`)

`validate_report(report, evidence)` parses the report into claims (bullets and sentences), reads their `[SOURCE:RECORD_ID]` citations and drug mentions, and checks each claim against the records it cites:

| Code | What it catches |
|---|---|
| `PHANTOM_CITATION` | cited ID is not in the retrieved evidence |
| `MISATTRIBUTED_CITATION` | cited record belongs to a different drug pair |
| `SEVERITY_MISMATCH` | section or tier word differs from the record's severity |
| `NUMERIC_MISMATCH` | PRR (or FAERS report count) differs from the record |
| `EVENT_MISATTRIBUTION` | adverse event named is not the cited record's |
| `UNSUPPORTED_MECHANISM` | mechanism term (CYP isoform, P-gp, OATP, UGT, QT, serotonergic, ...) absent from the record; isoform-aware, so CYP3A matches CYP3A4 but CYP2D6 does not |
| `UNSUPPORTED_POPULATION` | elderly / pediatric / pregnancy / renal / hepatic claim absent from the record |
| `FAERS_AS_CURATED` | an unvalidated FAERS report cited outside the FAERS section |
| `UNCITED_CLAIM` | clinical claim with no citation (the old syntactic check) |
| `OMITTED_INTERACTION`, `OMITTED_MAJOR` | a pair with records (or a Major record) is never cited |
| `MISSING_NO_DATA_DECLARATION`, `CONFLATED_ABSENCE` | a no-data pair is not declared, or is described as safe / non-interacting |
| `MISSING_UNRESOLVED_DECLARATION`, `MISSING_DISCLAIMER` | an unresolved input is not declared; disclaimer not present exactly once |

Metrics (micro-averaged over reports):
- **semantic_hallucination_rate**: clinical claims with at least one fabrication finding ÷ clinical claims
- **uncited_claim_rate**: the old syntactic metric
- **citation_validity**
- **pair_omission_rate**, **major_omission_rate**
- **completeness**: no-data pairs declared ÷ total

**These checks are a lower bound.** Mechanisms, events and populations are matched with hand-written lexicons (`src/verification/lexicon.py`), so a fabrication worded outside them passes. Five such probes (for example "hepatic enzyme blockade", "patients over 80", "risk roughly triples") are all missed; see `results/checker_validation.md`. An LLM judge for semantic entailment is planned as a later layer. It is **not implemented**, and no faithfulness score is reported.

### Validating the checker

`python scripts/validate_checker.py` writes `results/checker_validation.{json,md}`:
- **False positives:** the template reports for all 48 cases, plus clean synthetic `FX-` fixture reports in template and LLM-style prose, give 0 findings.
- **Sensitivity:** 12 fault types are injected into the fixtures, including the canonical case above (a record saying P-glycoprotein, a report claiming CYP3A4). Each fault's expected code is raised on every injected instance. This shows each check works on the fault it targets. It is not an estimate of how often real LLM errors are caught: the injected terms come from the checker's own lexicons, and the fixtures are small.

## Results (synthetic sample data)

From `python scripts/run_eval.py` (48 cases). The LLM column requires an API key; none was configured when these numbers were produced.

| Metric | Deterministic template | LLM path |
|---|---:|---:|
| Internal-consistency recall / precision | 1.000 / 1.000 (by construction) | n/a (retrieval only) |
| Hand-label recall | 0.974 (37/38) | n/a |
| Hand-label precision (lower bound) | 0.587 (37/63) | n/a |
| uncited_claim_rate | 0.000 | — |
| semantic_hallucination_rate | 0.000 | — |
| citation_validity | 1.000 | — |
| pair_omission_rate / major_omission_rate | 0.000 / 0.000 | — |
| completeness | 1.000 | — |
| LLM fallback rate | n/a | — |
| Faithfulness (LLM judge) | — (not implemented) | — |

The template's zeros are expected: the template only restates record fields, and the checker was validated against it (the false-positive check above). Those zeros say nothing about LLM output.

## Running the evaluation

```bash
python scripts/ingest_data.py --sample
python scripts/run_eval.py --output /tmp/eval.json            # all 48 cases
python scripts/run_eval.py --subset GER --skip-llm            # geriatric cases, no LLM calls
python scripts/validate_checker.py                            # checker false positives / sensitivity
```

With an API key in `.env`, `run_eval.py` also runs every case through the LLM path (one paid call per case) and reports the same metrics on the raw LLM reports, plus the fallback rate.

## What the evaluation does not measure

- **Real-data performance.** Only synthetic sample data has been evaluated.
- **Clinical appropriateness.** PharmGuard reports what its sources record; whether to act on it is the clinician's call.
- **Coverage of drugs outside the loaded data.** Reported via unresolved inputs and no-data pairs, not scored.
- **Clinical outcomes.** That would need a prospective study, not a retrieval benchmark.

## Interpreting the numbers

A 95% recall still misses 1 in 20 interactions. That's why every report also lists no-data pairs explicitly, cites a source record for every claim so a clinician can verify it, and carries a disclaimer. A system that flags its gaps is safer than one that scores slightly higher but is silent about them.
