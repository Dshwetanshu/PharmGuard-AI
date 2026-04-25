# PharmGuard Architecture

## Design principles

1. **Structured retrieval over semantic search for exact-pair queries.** For the question "what is the interaction between drug A and drug B?", a database lookup strictly dominates vector similarity. Vector search is reserved for unstructured context (reviews, mechanism prose).

2. **Deterministic where possible, LLM where necessary.** Pair enumeration is deterministic (`itertools.combinations`). Severity classification is deterministic (PRR thresholds). The LLM is only used for the final synthesis step — where fluent, clinically-structured prose is the actual product.

3. **Uncertainty surfaced, not suppressed.** Unresolved drug names, no-data pairs, and database coverage gaps are first-class outputs. A `no_data_pairs` field exists on every result.

4. **Every claim is a citation.** The generator prompt enforces inline `[SOURCE:RECORD_ID]` tags. The deterministic fallback does the same. If the pipeline ever produces a clinical claim without a citation, that's a bug.

## Pipeline stages

### Stage 1: Normalization (`src/data/normalizer.py`)

Input: free-form drug names.
Output: `ResolvedDrug` objects with `(generic_name, rxcui, drugbank_id, confidence, method)`.

Strategy:
1. Exact match against the RxNorm + DrugBank name index
2. Fuzzy match via `rapidfuzz.WRatio` with threshold 85
3. Explicit `unresolved` flag if neither succeeds

Failed resolutions are returned, not raised — the Planner surfaces them.

### Stage 2: Planning (`src/agents/planner.py`)

Input: list of resolved drugs.
Output: `RetrievalPlan` containing unique pairs, side-effect lookups, and unresolved-input list.

Deduplicates by canonical generic name so that "Lipitor + atorvastatin" doesn't create a phantom pair.

No LLM. Determinism is critical here: combinatorial enumeration is a closed-form operation.

### Stage 3: Retrieval (`src/agents/retriever.py`)

Input: plan.
Output: `RetrievalResult` with per-pair interactions, per-drug side effects, and no-data pairs.

Interactions come from a sorted-pair hash lookup over the processed TWOSIDES table (O(1) per pair). Side effects come from SIDER. Optional vector search over WebMD reviews if enabled.

### Stage 4: Generation (`src/agents/generator.py`)

Input: plan + retrieval result.
Output: markdown report.

The system prompt enforces three constraints:
- Every claim must cite a source record
- No-data pairs must be declared explicitly
- No fabrication of mechanisms not in the evidence

A deterministic fallback (`generate_deterministic`) produces a valid report without any LLM call — used as a safety net if the LLM fails, and in tests.

## Data flow

```
user input
   │
   ▼
[drug_vocabulary.parquet]  ←── built by Ingester from RxNorm + DrugBank
   │
   ▼ DrugNormalizer.resolve
   │
   ▼
[ResolvedDrug × N]
   │
   ▼ Planner.plan
   │
   ▼
[RetrievalPlan] ── pairs, side_effect_lookups, unresolved
   │
   ├──► InteractionRetriever ◄── [interactions.parquet] (from TWOSIDES)
   ├──► SideEffectRetriever ◄── [side_effects.parquet] (from SIDER)
   └──► VectorStore ◄── [reviews.parquet] (from WebMD)
   │
   ▼
[RetrievalResult]
   │
   ▼ Generator.generate
   │
   ▼
[final markdown report + disclaimer]
```

## What a base LLM cannot do (and why this architecture does)

| Capability | Base LLM | PharmGuard |
|---|---|---|
| Cite a specific DDInter/TWOSIDES record ID | ✗ | ✓ |
| Guarantee all pairs of an N-drug list were checked | ✗ | ✓ (deterministic enumeration) |
| Distinguish "no known interaction" from "no data" | ✗ | ✓ (`no_data_pairs`) |
| Produce a severity tier tied to reporting statistics | Fabricates | Derived from PRR thresholds |
| Refuse to invent a mechanism when none is recorded | Rarely | Enforced by prompt + fallback |

## Why TWOSIDES instead of DDInter

The original proposal used DDInter 2.0 as the primary interaction source. This build uses TWOSIDES at user request. Differences:

- **DDInter**: curated, severity-labeled, ~302K records, text mechanism descriptions.
- **TWOSIDES**: signal-mined from FAERS, ~4.6M raw records, statistical significance (PRR) instead of labeled severity.

Severity is synthesized from PRR (`src/data/loaders.py::_prr_to_severity`): PRR ≥ 10 → Major, ≥ 4 → Moderate, else Minor. This is a reasonable proxy but should be recalibrated if you have access to DDInter for cross-validation.

## Extension points

- **DDInter as secondary source:** add `load_ddinter` in `loaders.py` and merge into the interactions table; the retriever is source-agnostic.
- **Real-time FDA OpenFDA queries:** add an `openfda_retriever.py` that queries the FAERS API for pairs not in the local index.
- **Multi-turn chat UI:** the LLMClient is stateless by design. To add conversation, pass prior messages into `LLMClient.complete(messages=...)`.
- **Alternative vector stores:** `VectorStore` is a thin wrapper. Swap Chroma for Weaviate/Pinecone by changing `_ensure_client`.
