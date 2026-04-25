# Dataset Download Guide

PharmGuard uses **all seven datasets** from the original proposal (plus RxNorm for name normalization). Sample CSVs in `data/sample/` let you run the full pipeline without any downloads. For production-quality evaluation, populate `data/raw/` with the real datasets below.

Summary of how each dataset is used:

| # | Dataset | Role in pipeline |
|---|---|---|
| [1] | DDInter 2.0 | Curated interactions with native severity labels (secondary source, cross-validates TWOSIDES) |
| [2] | OpenFDA FAERS | Live-query fallback for pairs not in local indexes (opt-in) |
| [3] | DrugBank | Drug metadata + synonyms for normalization |
| [4] | UCI Drug Review | Patient-experience vector context (merged with WebMD) |
| [5] | ADE-Corpus-V2 | Per-drug adverse-event sentences (merged with SIDER) |
| [6] | SIDER | Side-effect knowledge base |
| [7] | TWOSIDES | Primary drug-drug interaction source |
| —   | RxNorm | Drug name ↔ RXCUI normalization |

---

## Core datasets (required for full mode)

### 1. TWOSIDES — drug-drug interactions (Tatonetti Lab)

**Download:** https://tatonettilab.org/resources/tatonetti-stm.html

Download the TWOSIDES CSV. Save as:

```
data/raw/twosides.csv
```

Expected columns: `drug_1_rxnorm_id, drug_1_concept_name, drug_2_rxnorm_id, drug_2_concept_name, condition_meddra_id, condition_concept_name, PRR, mean_reporting_frequency` (and others).

**Size:** ~3.6M records. Filter by PRR ≥ 2.0 (default) to get the clinically relevant subset.

**License:** Open for research use. Cite: Tatonetti et al., *Science Translational Medicine*, 2012.

---

### 2. DrugBank — drug metadata

**Download:** https://go.drugbank.com/releases/latest

The **open-access vocabulary CSV** is free and sufficient for PharmGuard's normalizer:
`drugbank vocabulary.csv` (available without academic license).

Save as:

```
data/raw/drugbank_vocabulary.csv
```

For mechanism descriptions and full drug profiles, a free academic license is needed (approved within ~48h at the link above).

**License:** Creative Commons BY-NC 4.0 for academic use.

---

### 3. SIDER — side effects

**Download:** http://sideeffects.embl.de/download/

Download `meddra_all_se.tsv.gz` (decompress). Save as:

```
data/raw/meddra_all_se.tsv
```

Optionally also download `meddra_all_indications.tsv`.

**License:** Free for academic/non-commercial use.

---

### 4. RxNorm — drug name normalization (UMLS/NIH)

**Download:** https://www.nlm.nih.gov/research/umls/rxnorm/index.html

Requires a free UMLS license (approved within ~3 business days).

Download the monthly **RxNorm full release** zip, extract `RXNCONSO.RRF`, and save as:

```
data/raw/rxnorm_RXNCONSO.RRF
```

**Alternative:** If UMLS license delay is an issue, the DrugBank vocabulary provides partial coverage. The RxNorm API (public, no license) can be used for live lookups — see `scripts/rxnorm_api_fetch.py` (not included; straightforward to add).

**License:** Free, with UMLS Metathesaurus License.

---

## Supplementary datasets

### 5. WebMD Drug Reviews

**Download:** https://www.kaggle.com/datasets/rohanharode07/webmd-drug-reviews-dataset

Save as:

```
data/raw/webmd.csv
```

Used for patient-experience retrieval (semantic search context).

**License:** CC0 per Kaggle.

---

### 6. Medical Recommendation Dataset (Kaggle)

**Download:** https://www.kaggle.com/datasets/joymarhew/medical-reccomadation-dataset

Save as:

```
data/raw/medical_recommendation.csv
```

Schema varies. Load via `load_generic_csv` in `src/data/loaders.py` and adapt.

---

### 7. Medical Prescription Dataset (Kaggle)

**Download:** https://www.kaggle.com/datasets/bokhnhl/medical-prescription-dataset

Save as:

```
data/raw/medical_prescription.csv
```

---

### 8. Medicare Part D Prescribers (stretch)

**Download:** https://catalog.data.gov/dataset/medicare-part-d-prescribers-by-provider-and-drug-ad73e

This dataset contains prescribing *patterns*, not interactions. Useful for population-level analytics (most-prescribed drugs, co-prescription frequency) but not for the core PharmGuard pipeline.

---

## File checklist for full mode

After downloading, your `data/raw/` should contain:

```
data/raw/
├── twosides.csv              ← Primary interaction source
├── ddinter.csv               ← Secondary interactions (severity labels)
├── drugbank_vocabulary.csv   ← Drug metadata
├── meddra_all_se.tsv         ← SIDER side effects
├── rxnorm_RXNCONSO.RRF       ← RxNorm concepts
├── ade_corpus.csv            ← ADE-Corpus-V2 drug-adverse-effect pairs
├── webmd.csv                 ← WebMD reviews (optional)
└── uci_drug_reviews.csv      ← UCI Drug Reviews (optional)
```

Then:

```bash
python scripts/ingest_data.py --full
```

To enable the OpenFDA FAERS live fallback, add to your `.env`:

```
PHARMGUARD_FAERS_ENABLED=true
```

---

## Additional datasets (added to match proposal)

### DDInter 2.0

**Download:** https://ddinter2.scbdd.com

Download the bulk CSV (merged across ATC classes) and save as:

```
data/raw/ddinter.csv
```

Expected columns: `DDInterID_A, Drug_A, DDInterID_B, Drug_B, Level, Mechanism` where `Level` is one of `Major / Moderate / Minor`.

**Why both TWOSIDES and DDInter?** TWOSIDES provides statistical signals (PRR from FAERS), DDInter provides curated severity labels and mechanism prose. PharmGuard merges both and cites each separately, so a clinician can cross-validate a finding against both sources.

**Cite:** Tian, Y. et al. "DDInter 2.0: an enhanced drug interaction resource." *Nucleic Acids Research*, 53(D1), 2025.

---

### OpenFDA FAERS

**No download required** — queried live via the public API.

To enable:
```
# in .env
PHARMGUARD_FAERS_ENABLED=true
```

Per-pair queries hit `https://api.fda.gov/drug/event.json` and surface reactions co-reported for drug pairs. Rate-limit-aware (1.5 s between calls, well under the 40/min unauthenticated ceiling). If a pair has **no** record in the local TWOSIDES/DDInter index, FAERS is consulted before the pair is flagged as no-data.

**Cite:** U.S. FDA. FAERS Adverse Event Reporting System. https://open.fda.gov/apis/drug/event/

---

### UCI Drug Review Dataset

**Download:** https://kaggle.com/datasets/jessicali9530/kuc-hackathon-winter-2018

Save the CSV (or TSV) as:

```
data/raw/uci_drug_reviews.csv
```

Merged with WebMD reviews into the reviews vector index for patient-experience context.

**Cite:** Gräßer, F. et al. UCI Drug Review Dataset. Kaggle.

---

### ADE-Corpus-V2

**Download:** https://huggingface.co/datasets/ade_corpus_v2 (config: `Ade_corpus_v2_drug_ade_relation`)

Export the drug-ADE relation split to CSV with columns `text, drug, effect` (or JSONL). Save as:

```
data/raw/ade_corpus.csv
```

Merged with SIDER to provide per-drug adverse-event context with source sentences.

**Cite:** Gurulingappa, H. et al. ADE-Corpus-V2. HuggingFace.

---

## A note on privacy

None of these datasets contain PHI. TWOSIDES and FAERS-derived data are de-identified before public release under HIPAA Safe Harbor. PharmGuard itself stores no user medication lists — input is processed in memory only.
