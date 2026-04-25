# PharmGuard AI

An agentic RAG system for prescription safety and drug-drug interaction detection, grounded in structured pharmaceutical databases.

> Given a list of 2–12 medications, PharmGuard enumerates all pairwise combinations, retrieves interaction evidence from TWOSIDES, DrugBank, and SIDER, and generates a severity-tiered, citation-backed clinical report. Every claim links to a source record ID.

## Submission deliverables

| Deliverable | Location |
|---|---|
| Source code + docs | This repository |
| Documentation PDF | [`docs/PharmGuard_AI_Documentation.pdf`](docs/PharmGuard_AI_Documentation.pdf) (14 pages) |
| Web showcase page | [`website/index.html`](website/index.html) — deployable to GitHub Pages |
| Video script | [`docs/VIDEO_SCRIPT.md`](docs/VIDEO_SCRIPT.md) — 10-minute demo walkthrough |
| Architecture doc | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Evaluation methodology | [`docs/EVALUATION.md`](docs/EVALUATION.md) |
| Dataset guide | [`docs/DATASETS.md`](docs/DATASETS.md) |

---

## Why this exists

A base LLM asked "does drug X interact with drug Y?" will answer fluently but cannot:

1. **Cite the source record** for each interaction
2. **Scale combinatorially** — 7 drugs produce 21 pairs, systematically
3. **Flag absence of evidence** instead of silently guessing

PharmGuard fills this gap with a plan → retrieve → generate loop over indexed pharmaceutical data.

---

## Dataset mapping

This build uses **all 7 datasets** from the proposal:

| Dataset | Role | Source |
|---|---|---|
| **TWOSIDES** (Tatonetti Lab) | Primary drug-drug interaction data | [tatonettilab.org](https://tatonettilab.org/resources/tatonetti-stm.html) |
| **DDInter 2.0** (Tian et al.) | Secondary interactions with severity labels | [ddinter2.scbdd.com](https://ddinter2.scbdd.com) |
| **OpenFDA FAERS** | Live-query fallback for no-data pairs (opt-in) | [open.fda.gov](https://open.fda.gov/apis/drug/event/) |
| **DrugBank 5.x** | Drug metadata, mechanisms, ATC codes, synonyms | [drugbank.com](https://go.drugbank.com/releases/latest) |
| **SIDER** | Side-effect (adverse reaction) knowledge base | [sideeffects.embl.de](http://sideeffects.embl.de/download/) |
| **ADE-Corpus-V2** | Per-drug adverse-event sentence evidence | [HuggingFace](https://huggingface.co/datasets/ade_corpus_v2) |
| **WebMD Drug Reviews** | Patient-reported experience retrieval | [Kaggle](https://www.kaggle.com/datasets/rohanharode07/webmd-drug-reviews-dataset) |
| **UCI Drug Review** | Patient-reported experience retrieval | [Kaggle](https://www.kaggle.com/datasets/jessicali9530/kuc-hackathon-winter-2018) |
| **RxNorm** (UMLS/NIH) | Drug name normalization (brand ↔ generic ↔ RXCUI) | [nlm.nih.gov](https://www.nlm.nih.gov/research/umls/rxnorm/index.html) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  User input: ["lisinopril", "metformin", "aspirin", ...]        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  Normalizer (RxNorm)             │
            │  brand → generic → RXCUI         │
            └──────────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  Planner Agent                   │
            │  Enumerate pairwise combinations │
            │  Construct retrieval plan        │
            └──────────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  Retriever Agent                 │
            │  ├─ TWOSIDES (interactions)      │
            │  ├─ DrugBank (mechanisms)        │
            │  ├─ SIDER (side effects)         │
            │  └─ WebMD (patient reports)      │
            └──────────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  Generator Agent                 │
            │  Grounded LLM report with        │
            │  inline source citations         │
            └──────────────────────────────────┘
                              │
                              ▼
            ┌──────────────────────────────────┐
            │  Severity-sorted report          │
            │  + coverage notes                │
            │  + uncertainty flags             │
            └──────────────────────────────────┘
```

---

## Quick start

### 1. Install dependencies

```bash
python -m venv prompt_final
source prompt_final/bin/activate      # Windows: prompt_final\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure API key

```bash
cp .env.example .env
# Edit .env and set ONE of:
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPENAI_API_KEY=sk-...
#   GOOGLE_API_KEY=...
```

### 3. Try it with sample data (no downloads required)

```bash
python scripts/ingest_data.py --sample
python -m app.streamlit_app
# or: streamlit run app/streamlit_app.py
```

The sample mode indexes a small curated subset so you can demo the full pipeline end-to-end without waiting on dataset downloads.

### 4. Run with real data

Download the datasets into `data/raw/` using these filenames (see `docs/DATASETS.md` for details):

```
data/raw/
├── twosides.csv              # Tatonetti TWOSIDES
├── drugbank_vocabulary.csv   # DrugBank open vocabulary
├── meddra_all_se.tsv         # SIDER side effects
├── meddra_all_indications.tsv # SIDER indications
├── rxnorm_RXNCONSO.RRF       # RxNorm concepts
├── webmd.csv                 # WebMD reviews
└── ... (see docs/DATASETS.md)
```

Then:

```bash
python scripts/ingest_data.py --full
python scripts/run_eval.py
streamlit run app/streamlit_app.py
```

---

## Project layout

```
pharmguard-ai/
├── README.md
├── requirements.txt
├── .env.example
├── data/
│   ├── raw/         # Place downloaded datasets here
│   ├── processed/   # Parquet + vector index output
│   └── sample/      # Small curated sample for demo/testing
├── src/
│   ├── config.py              # Central config
│   ├── data/
│   │   ├── normalizer.py      # RxNorm-based drug name normalization
│   │   ├── loaders.py         # Schema-aware loaders for each dataset
│   │   └── ingestion.py       # Build processed index
│   ├── retrieval/
│   │   ├── vector_store.py
│   │   ├── interaction_retriever.py
│   │   └── side_effect_retriever.py
│   ├── agents/
│   │   ├── planner.py
│   │   ├── retriever.py
│   │   └── generator.py
│   ├── llm.py                 # Unified LLM client (Anthropic/OpenAI/Gemini)
│   ├── pipeline.py            # Main orchestrator
│   └── evaluation/
│       ├── metrics.py
│       └── test_cases.py
├── app/
│   └── streamlit_app.py       # Web UI
├── scripts/
│   ├── ingest_data.py
│   └── run_eval.py
├── tests/
│   └── test_pipeline.py
└── docs/
    ├── DATASETS.md            # Where/how to download each dataset
    ├── ARCHITECTURE.md
    └── EVALUATION.md
```

---

## Evaluation

The evaluation framework (per the proposal) defines failure before success.

| Metric | Target |
|---|---|
| Retrieval Recall | ≥ 95% |
| Retrieval Precision | ≥ 90% |
| Faithfulness | ≥ 85% |
| Hallucination Rate | ≤ 5% |
| Severity Accuracy | ≥ 90% |
| Completeness Flagging | 100% |

Run with:

```bash
python scripts/run_eval.py --output reports/eval_report.json
```

---

## Safety disclaimer

PharmGuard is a **decision-support tool**, not a substitute for professional medical judgment. Every output includes this disclaimer. The system never claims comprehensiveness — it claims fidelity to its sources and honesty about what those sources do not cover.

---

## License

Academic use. See individual dataset licenses in `docs/DATASETS.md`.
