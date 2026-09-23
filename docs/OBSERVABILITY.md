# Observability: tracing the PharmGuard graph

Tracing is **optional and off by default**. There is one switch:

```bash
PHARMGUARD_TRACING=none        # default: nothing is recorded or sent
PHARMGUARD_TRACING=phoenix     # OpenTelemetry to a Phoenix collector (can run on your machine)
PHARMGUARD_TRACING=langsmith   # LangSmith (hosted by LangChain)
PHARMGUARD_TRACE_REDACT=true   # default: hide inputs and outputs (see "Redaction")
```

The switch is read only in `Settings.from_env()` (`src/graph/settings.py`). If the value is unknown, the packages aren't installed, the credentials are missing, or the Phoenix collector isn't reachable, PharmGuard logs **one warning** and runs untraced. Tracing never changes a report: every tracing call is wrapped so its errors are logged, not raised, and a test checks that reports are byte-identical with tracing on and off.

The tracing packages are optional:

```bash
pip install -r requirements.txt -r requirements-tracing.txt
```

## Phoenix (local)

1. Start a collector and UI on port 6006. Either:
   - `docker compose up -d phoenix` (see `docker-compose.yml`), or
   - without Docker, in a separate environment: `pip install arize-phoenix && phoenix serve`.

   The Docker route is untested here (no Docker on the development machine); the pip route (arize-phoenix 20.15.0) was used for the verification below.
2. Run with tracing:

   ```bash
   export PHARMGUARD_TRACING=phoenix
   export PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006   # default
   export PHOENIX_PROJECT_NAME=pharmguard                    # default
   python scripts/demo.py lisinopril spironolactone aspirin fictional_drug_xyz
   python scripts/demo.py --simulate-retry lisinopril spironolactone aspirin
   ```
3. Open http://localhost:6006.

Setup details (`src/observability/tracing.py`):
- `phoenix.otel.register(project_name=..., endpoint=.../v1/traces)` builds the tracer provider.
- The OpenInference LangChain, Anthropic and OpenAI instrumentors are attached explicitly with a `TraceConfig`. `register(auto_instrument=True)` can only take redaction settings from `OPENINFERENCE_*` environment variables, so it isn't used.
- `openinference-instrumentation-anthropic` 2.1.5 (the latest release) fails to load against `anthropic` 1.8, because it imports `anthropic._utils._transform`, which no longer exists. So Anthropic calls are recorded by PharmGuard's own OpenInference-style LLM span (`llm.anthropic`): model, token counts, latency, and prompts only when redaction is off. The OpenAI instrumentor loads normally.

## LangSmith (hosted)

```bash
export PHARMGUARD_TRACING=langsmith
export LANGSMITH_API_KEY=...          # required; without it: one warning, untraced
export LANGSMITH_PROJECT=pharmguard   # optional
```

- PharmGuard attaches a `LangChainTracer` built on a `langsmith.Client(hide_inputs=..., hide_outputs=...)`, so the redaction setting applies to every LangGraph run.
- The Anthropic/OpenAI SDK client is wrapped with `langsmith.wrappers.wrap_anthropic` / `wrap_openai`, so prompts (when not redacted), token counts and latency appear on the LLM call.
- `LANGSMITH_TRACING=true` is not needed. On its own, without `PHARMGUARD_TRACING=langsmith`, it sends nothing: PharmGuard disables LangChain's env-driven tracing for its runs (tested).
- **Not verified against the live service**: no LangSmith key was available. A test captures the HTTP bodies the LangSmith client would send and checks they contain no drug names.

## What is recorded

| Where | What |
|---|---|
| Root run `pharmguard.request` (one per request) | Tags: `mode:<llm/deterministic>`, `pipeline:langgraph`, `llm:<label>`, plus the entry point. Metadata: `request_id` (also the Phoenix `session.id`), `n_drugs`, `mode`, `llm`, `data_provenance` (e.g. "Data: synthetic sample dataset (85 interaction records), not real clinical data."), `trace_redacted`. Outcome, set at the end: `report_source`, `llm_attempts`, `fallback_reason` (`validation_failed`, `llm_error:<class>`, `no_llm_configured`, `insufficient_input` or empty), `finding_codes`, `final_validation_passed`. |
| One span per graph node (`normalize`, `plan`, `retrieve`, `faers`, `generate_llm`, `validate`, `template`, `finalize`) | `pharmguard.status`, `pharmguard.ms`, and the node's safe detail: route taken, attempt number, `finding_codes`, error class and whether it was retryable, pair/record counts, normalizer method counts (exact/alias/fuzzy/rxnorm; never the inputs), token usage. `route_after_*` spans are LangGraph's conditional-edge functions. |
| `rxnorm.http`, `faers.http` | Child spans of the node that made the call: `server.address`, `url.path`, `http.response.status_code`, duration. `url.query` (which contains the drug name) only when redaction is off. |
| LLM call | Model, token counts, latency; prompt and completion only when redaction is off. |

Runs made with `demo.py --simulate-retry` use a **scripted simulated LLM** (`src/graph/simulated.py`), not a model. Draft 1 contains a fabricated "via CYP3A4 inhibition" mechanism and is rejected; draft 2 is clean and passes. These runs are tagged `llm:simulated LLM` and `simulated`, with metadata `llm = "simulated LLM"`.

Filters that work in Phoenix's span filter box (checked against Phoenix 20.15.0):

```
metadata['report_source'] == 'deterministic_fallback'
metadata['report_source'] == 'llm_retry'
'UNSUPPORTED_MECHANISM' in attributes['pharmguard']['finding_codes']
metadata['llm'] == 'simulated LLM'
```

## Redaction

Medication lists are health data. With `PHARMGUARD_TRACE_REDACT=true` (the default):

- **Phoenix / OpenInference:** `TraceConfig(hide_inputs, hide_outputs, hide_input_messages, hide_output_messages, hide_input_text, hide_output_text, hide_prompts, hide_choices)`. Span inputs and outputs show as `__REDACTED__`. The root span gets no `input.value` or `output.value`.
- **LangSmith:** `langsmith.Client(hide_inputs=True, hide_outputs=True)`.
- **PharmGuard's own attributes** carry no drug names or report text at all: node detail is filtered through a whitelist (`SAFE_DETAIL_KEYS`), and HTTP spans omit the query string.

**Still visible:** node and span names, timings, statuses, routes, attempt numbers, counts, finding codes, error classes, model name, token counts, HTTP host/path/status, and the metadata above (including the provenance line). A trace shows *that* a request had 3 drugs and fell back after an `UNSUPPORTED_MECHANISM` finding, not *which* drugs.

Checked in a live Phoenix: the redacted project contained none of the input drug names or report terms anywhere in its spans. The unredacted project contained them.

Set `PHARMGUARD_TRACE_REDACT=false` only for demos on the synthetic sample data (e.g. screenshots), ideally in a separate project.

## Privacy trade-off

- **Phoenix** can run entirely on your machine (`docker compose` or `phoenix serve`), so traces never leave it. The trade-off is that you operate and secure it yourself. By default it stores traces on local disk (`PHOENIX_WORKING_DIR`).
- **LangSmith** is a hosted service: traces are sent to and stored by a third party. Keep redaction on, and check your organisation's data-processing terms before sending anything that isn't synthetic.
- Both backends are off unless explicitly enabled, and both redact by default.

## Screenshots for the README

Record traces first (Phoenix running, `PHARMGUARD_TRACING=phoenix`):

```bash
PHOENIX_PROJECT_NAME=pharmguard python scripts/demo.py --simulate-retry lisinopril spironolactone aspirin
PHOENIX_PROJECT_NAME=pharmguard-demo-unredacted PHARMGUARD_TRACE_REDACT=false \
    python scripts/demo.py --simulate-retry lisinopril spironolactone aspirin
PHOENIX_PROJECT_NAME=pharmguard-demo-unredacted PHARMGUARD_TRACE_REDACT=false \
    python scripts/demo.py lisinopril spironolactone aspirin fictional_drug_xyz
```

1. **Retry path.** Project `pharmguard-demo-unredacted`, open the trace whose root is tagged `llm:simulated LLM`. The tree reads `pharmguard.request → pharmguard_graph → normalize → plan → retrieve → generate_llm → validate → generate_llm → validate → finalize`. Select the first `validate` span: `pharmguard.status = fail`, `pharmguard.finding_codes = ["UNSUPPORTED_MECHANISM"]`, `pharmguard.route = generate_llm`. Caption it "simulated LLM".
2. **Redaction.** Project `pharmguard`, the same simulated-retry trace, root span selected: metadata (`request_id`, `n_drugs: 3`, `report_source: llm_retry`, `llm_attempts: 2`, provenance line) and no input or output values. Node spans' inputs show `__REDACTED__`.
3. **HTTP child span.** Project `pharmguard-demo-unredacted`, the deterministic trace: `rxnorm.http` nested under `normalize`, with `server.address = rxnav.nlm.nih.gov`, `url.path = /REST/approximateTerm.json`, status 200 and its duration.
