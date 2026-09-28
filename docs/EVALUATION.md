# Evaluation Methodology

> If you cannot describe the failure mode that keeps you up at night, you have not thought hard enough about your system.

This doc says how PharmGuard is evaluated, what is actually measured today, and what is not. All numbers below come from running the code in this repository. Each one names its data build: the **synthetic sample** (85 interaction records; what CI checks), the real **public** build (RxNorm Current Prescribable 2026-09-08 + the DDInter bulk download + SIDER 4.1) or the real **research** build (public + TWOSIDES; aggregate numbers only). See docs/DATASETS.md for the builds. Unmeasured values are shown as "—".

## The silent-failure scenario

The target failure mode is:

> A patient inputs six medications. The system returns a cleanly formatted report listing four interactions with professional-sounding mechanism descriptions. It looks authoritative. But the system has missed two critical interactions, one classified as *Major* severity in the source database, and has fabricated a CYP3A4 inhibition pathway where the actual mechanism is P-glycoprotein competition.

Counting citations can't catch this: the fabricated sentence can carry a real citation. So PharmGuard checks each claim against the record it cites (see *Report checks* below). The same checker runs as a runtime guardrail: an LLM report that fails it is never shown, and the deterministic template report is returned instead.

## Test cases

`src/evaluation/test_cases.py` defines 56 cases: 48 across 12 clinical groups, plus 8 brand-name and look-alike cases (LA-*, added after the step 8b blind trial) that check normalization only and have no interaction labels. The 48 cover (geriatric, textbook interactions, edge cases, mental health, cardiology, endocrine, infectious disease, oncology-adjacent, pain, respiratory, GI, a 10-drug profile). Each case has hand-written `known_interaction_pairs`. The labels are partial: 14 cases list none, and some labels are suspected to be wrong. Suspected errors are flagged for review, not edited.

## Retrieval metrics

### Internal consistency (recall / precision)

Ground truth = every input pair present in the loaded interaction table, derived with **the same normalizer and table the retriever uses**. Recall and precision are therefore 1.0 **by construction**. This only catches bugs in pair enumeration and lookup plumbing. It scored 1.0 while lithium + hydrochlorothiazide (Major) was reported as "no data" because of a lithium / lithium carbonate key mismatch (since fixed: both builds use the RxNorm ingredient "lithium").

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
- **False positives:** the template reports for all 56 cases, plus clean synthetic `FX-` fixture reports in template and LLM-style prose, give 0 findings.
- **Sensitivity:** 14 fault types are injected into the fixtures, including the canonical case above (a record saying P-glycoprotein, a report claiming CYP3A4). Each fault's expected code is raised on every injected instance. The two newest: a severity word attached to a statistical signal (or a signal listed under a severity heading), and hidden signals not stated as "+N more not shown". This shows each check works on the fault it targets. It is not an estimate of how often real LLM errors are caught: the injected terms come from the checker's own lexicons, and the fixtures are small.

## Report format the checks assume

- **Curated records** (DDInter) appear under their curated severity heading as "curated severity: X (source)", with every curated record kept.
- **Statistical signals** (TWOSIDES, and the TWOSIDES-shaped sample rows) appear only in "Statistical reporting signals (not graded for clinical severity)", with PRR and co-report count, never with a severity word. At most 3 are shown per pair (highest PRR); the rest are stated as "+N more not shown". `OMITTED_MAJOR` counts curated records only.
- The checker judges only the records the report selected.

## Results (synthetic sample data)

From `python scripts/run_eval.py` (56 cases). The LLM column requires an API key; none was configured when these numbers were produced.

| Metric | Deterministic template | LLM path |
|---|---:|---:|
| Internal-consistency recall / precision | 1.000 / 1.000 (by construction) | n/a (retrieval only) |
| Hand-label recall | 0.974 (37/38) | n/a |
| Hand-label precision (lower bound) | 0.578 (37/64) | n/a |
| uncited_claim_rate | 0.000 | — |
| semantic_hallucination_rate | 0.000 | — |
| citation_validity | 1.000 | — |
| pair_omission_rate / major_omission_rate | 0.000 / 0.000 | — |
| completeness | 1.000 | — |
| LLM fallback rate | n/a | — |
| Faithfulness (LLM judge) | — (not implemented) | — |

The template's zeros are expected: the template only restates record fields, and the checker was validated against it (the false-positive check above). Those zeros say nothing about LLM output.

## Results on the real builds (deterministic template; no API key)

The 8 look-alike cases (LA-*) have no interaction labels, so hand-label recall is still over the original 38 labelled pairs.

Same scripts, pointed at a real build. Every result file names the build and the sha256 of its `provenance.json`. Research-build files hold aggregate numbers only.

| | sample | public | research |
|---|---:|---:|---:|
| Hand-label recall | 0.974 (37/38) | 0.974 (37/38) | 0.974 (37/38) |
| Hand-label precision (lower bound) | 0.578 (37/64) | 0.155 (37/238) | 0.155 (37/238) |
| Misses: source gap / pipeline miss | 1 / 0 (EDG-03) | 1 / 0 (END-02) | 1 / 0 |
| Pairs with no curated record (56 cases) | 169 (completeness 1.000) | 0 of 238 | 0 of 238 |
| Checker false positives, 56 template reports | 0 (124 claims) | 0 (238 claims) | 0 (927 claims) |
| Checker false positives, 200 random 4-drug lists | n/a | 0 (239 claims) | 0 (376 claims) |
| Checker false positives, hard names (comma, parenthesis, > 30 chars) | n/a | 0 (27 reports, 153 claims) | 0 (44 reports, 730 claims) |
| Step completion (trajectory) | 100% | 100% | 100% |
| Fault-suite runs / invariant runs / min invariant pass rate | 629 / 741 / 100% | 680 / 792 / 100% | 729 / 841 / 100% |
| Seeded orchestration bugs caught | 6 / 6 | 6 / 6 | 6 / 6 |
| LLM path | — | — | — |

Notes:
- **Precision** falls on real data because DDInter has a record for every pair in the 56 cases, many of them without a grade, while the hand labels list only the headline interactions. It is a lower bound.
- **EDG-03** (atorvastatin + lisinopril), a suspected label error on the sample, is a DDInter record on the real builds (not graded). **END-02**'s labelled pair can't match on real data: plain "insulin" is ambiguous in RxNorm and stays unresolved by design.
- The real-build stress sets found three checker/input bugs, now fixed with regression tests: comma names rejected by input validation, a non-idempotent British-spelling fold (a TWOSIDES "gastrooesophageal" event flagged against its own record), and a population word matched inside a drug name ("calcium lactate").
- Before all 14 DDInter ATC files were ingested, the public build's hand-label recall was 0.553 (21/38), with 17 "source gaps" that were really our incomplete download.

## Trajectory evaluation (orchestration)

`python scripts/eval_trajectory.py --fault-suite --seeded-bugs --min-invariant-pass 1.0` writes `results/trajectory.{json,md}` and exits non-zero below the threshold, so CI can use it as a gate. It runs offline with no API keys; every LLM in it is a scripted fake.

- **Step scoring:** each case is scored per step (normalize, plan, retrieve, route, finalize); task completion means every step is correct. Edge-case inputs have explicit `expected_resolved` / `expected_unresolved` in `test_cases.py`. The already-flagged EDG-03 label is counted separately.
- **Fault suite:** scripted drafts derived from each case's deterministic report. Scenarios: clean; transient error once or always; non-transient error once; hallucinated mechanism once or always; omitted Major; absence stated as safety; phantom citation; severity flip; uncited claim; a different fault on the retry; the retry repeating the rejected draft. Each scenario has an expected node path and report_source.
- **Invariants:** 11, checked on every run and computed independently of the graph's own claims.
- **Seeded bugs:** six orchestration bugs (`src/evaluation/seeded_bugs.py`) are checked to break at least one invariant each.
- **Latency:** with fake LLMs it measures orchestration overhead only.

## Latency

All deterministic (no LLM call). **End to end** means timed by the client, from sending the HTTP request to
receiving the whole response, so it includes the network, TLS and the server. **Server-side** is the
`timings_ms.total` the API reports. **In-process** is the graph alone, with no HTTP.

| Where | What is timed | p50 | p95 | n | Source |
|---|---|---:|---:|---:|---|
| Live, https://pharmguard.web.app (Firebase Hosting → Cloud Run) | six-drug check, **end to end** | 174 ms | 236 ms | 38 | docs/DEPLOYMENT.md, 28 Sep 2026 |
| Live, same requests | server-side | 56 ms | 77 ms | 38 | docs/DEPLOYMENT.md |
| Live, run.app (Cloud Run directly) | six-drug check, **end to end** | 138 ms | 161 ms | 40 | docs/DEPLOYMENT.md |
| Live, same requests | server-side | 54 ms | 70 ms | 40 | docs/DEPLOYMENT.md |
| Local Docker (OrbStack, Apple Silicon) | 47 cases × 5 rounds, **end to end** | 22.7 ms | 125.5 ms | 235 | docs/API.md, 24 Sep 2026 |
| Local Docker, same requests | server-side | 18.1 ms | 121.0 ms | 235 | docs/API.md |
| Local, in-process (public build, fake LLMs) | graph orchestration only, not end to end | 8.4 ms | 32.6 ms | — | results/trajectory_public.md |

The live end-to-end numbers were measured from the machine used for the deployment, so they include that
machine's network path to Google. Cold starts, all end to end (`/health`):

| Where | Cold start | Next request |
|---|---:|---:|
| Live run.app, after 25 min idle (new instance in the log) | 14.9 s | 82 ms |
| Live web.app, after 25 min idle (new instance in the log) | 15.7 s | 117 ms |
| Live, a deployment's first instance, start to ready | 12.9 s (about 7 s image and Python start, about 6 s to download, verify and load the build) | — |
| Local Docker, first run after the build / later runs | 16.9 s / 2.8 s | — |

An LLM-mode check would add at least one model call per report (two with a retry). Its latency is
unmeasured: "—".

## Running the evaluation

```bash
python scripts/ingest_data.py --sample
python scripts/run_eval.py --output /tmp/eval.json            # all 56 cases
python scripts/run_eval.py --subset GER --skip-llm            # geriatric cases, no LLM calls
python scripts/validate_checker.py                            # checker false positives / sensitivity
```

With an API key in `.env`, `run_eval.py` also runs every case through the LLM path (one paid call per case) and reports the same metrics on the raw LLM reports, plus the fallback rate.

## What the evaluation does not measure

- **LLM output on any build.** No API key has been configured, so every LLM-path number is "—".
- **Clinical appropriateness.** PharmGuard reports what its sources record; whether to act on it is the clinician's call.
- **Coverage of drugs outside the loaded data.** Reported via unresolved inputs and no-data pairs, not scored.
- **Clinical outcomes.** That would need a prospective study, not a retrieval benchmark.

## Interpreting the numbers

A 95% recall still misses 1 in 20 interactions. That's why every report also lists no-data pairs explicitly, cites a source record for every claim so a clinician can verify it, and carries a disclaimer. A system that flags its gaps is safer than one that scores slightly higher but is silent about them.
