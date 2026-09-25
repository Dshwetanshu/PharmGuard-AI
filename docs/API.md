# PharmGuard API

A FastAPI service in front of the LangGraph state machine (deterministic planning and
bounded LLM retry). The code is in `api/`. Request handling (`api/service.py`) doesn't
depend on any web framework; `api/app.py` maps it to HTTP. The graphs are built once at
start-up, never per request.

```bash
docker build -t pharmguard-api .
docker run --rm -p 7860:7860 -v "$PWD/data/profiles/public:/data/public:ro" pharmguard-api
open http://127.0.0.1:7860/          # page;  /docs for the OpenAPI UI
```

Without Docker: `pip install --require-hashes --no-deps -r requirements-api.lock`, then
`PHARMGUARD_DATA_DIR=data/profiles/public uvicorn api.app:app --port 7860 --no-access-log`.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| POST | `/v1/check` | the report and its metadata (below) |
| GET | `/health` | status, reason if unavailable, build profile, provenance sha256, record counts, whether an LLM is configured, disclaimer, attribution notices. 200 when the data is loaded, 503 otherwise. |
| GET | `/v1/graph` | the graph topology as Mermaid |
| GET | `/` | a small page to try it |
| GET | `/docs`, `/openapi.json` | the FastAPI docs |

`POST /v1/check` body:

```json
{"drugs": ["warfarin", "aspirin"], "mode": "deterministic", "include_evidence": false,
 "include_trajectory": false, "faers": false}
```

- `drugs`: 2 to 12 names, checked by the same validator as the app (`src/input_validation.py`).
- `mode`: `deterministic` (default), `llm` or `auto`. LLM mode requires an `X-API-Key` header
  matching `PHARMGUARD_API_KEY` and a configured provider key; otherwise the request gets 401
  (missing or wrong key) or 503 (no provider). `auto` uses the LLM only when both are present,
  and deterministic mode otherwise.
- `faers`: query openFDA FAERS for pairs with no curated record. It's capped at
  `PHARMGUARD_FAERS_MAX_PAIRS` pairs (5) and `PHARMGUARD_FAERS_BUDGET_S` seconds (10) per
  request. Pairs over the cap are counted in `faers.skipped_pairs`.

The response has these fields:
- `request_id`, `report_markdown` (the complete report) and `report_source`
- `mode`: the resolved mode
- `validation`: passed, finding codes, clinical claims, citations
- `unresolved_inputs`
- `data`: profile, data line, provenance sha256
- `disclaimer` and `attribution` (the notices from `src/data/attribution.py`)
- `faers`
- `timings_ms`: graph, per node, total
- `evidence` and `trajectory`, only when requested

Errors are always `{"request_id", "error": {"code", "message"}}`, never a stack trace.

| Status | Codes |
|---|---|
| 401 | `llm_requires_api_key` |
| 413 | `body_too_large` (16 KB) |
| 422 | `invalid_drug_count`, `invalid_drug_name`, `invalid_mode`, `invalid_json`, … |
| 429 | `rate_limited` (with `Retry-After`) |
| 503 | `data_unavailable`, `llm_not_configured`, `busy` |
| 504 | `timeout` |

## Public defaults and safety

- **Fail closed.** The server requires the `public` build (`PHARMGUARD_REQUIRED_PROFILE`).
  A missing, synthetic, research-profile or unverified build leaves the server up, with
  `/health` giving the reason (HTTP 503) and `/v1/check` returning 503. There is no fall-back
  to the synthetic sample.
- **Mode and data.** Deterministic mode by default. Live RxNorm is off: the local RxNorm
  vocabulary covers normalization. Tracing is off.
- **Rate limit.** Per client IP, `PHARMGUARD_RATE_LIMIT` (default `20/60`: 20 requests per 60
  s), counted before the body is parsed. Behind the Hugging Face Spaces proxy, set
  `PHARMGUARD_TRUSTED_PROXY_HOPS=1`: the client is then the right-most `X-Forwarded-For`
  entry, since entries further left can be forged. With the default of 0 the header is
  ignored. Uvicorn runs with `--no-proxy-headers`, so only this rule applies.
- **Timeouts and concurrency.** 20 s deterministic and 90 s LLM (`PHARMGUARD_TIMEOUT_S`,
  `PHARMGUARD_LLM_TIMEOUT_S`). At most `PHARMGUARD_MAX_CONCURRENCY` (4) checks run at once;
  beyond that the server returns 503 `busy`. A timed-out run keeps its slot until it
  finishes, because Python threads can't be killed.
- **Logs.** Every response carries `X-Request-ID`, and every log line carries `request_id`.
  Logs record counts, modes and codes: never drug names, report text or client IPs.
- **Page.** All user and server text is escaped before it reaches the DOM. The report
  markdown is escaped, then rendered by a small renderer (tested with Node in
  `tests/test_api.py`). The page has no inline script, and its CSP allows only same-origin
  resources. "Listed by DDInter without a severity grade" is collapsed with its count, while
  the markdown report stays complete. Every report starts with "How your entries were read"
  (for example "Coumadin → warfarin (brand name, Drugs@FDA)" or "warfrin → warfarin (spelling
  match: check this)"). A red notice appears when two entries are the same drug. DDInter citations aren't deep-linked (docs/DATASETS.md explains why).

## Build download (optional, for Hugging Face Spaces)

Set `PHARMGUARD_HF_DATASET` (the dataset repo; public for the demo), `PHARMGUARD_HF_REVISION`
(a 40-character commit sha) and `PHARMGUARD_HF_PROVENANCE_SHA256`. `HF_TOKEN` (a read-only Space
secret) is needed only for a private dataset. At start-up, `api/bootstrap.py` does the following:
1. downloads `processed/*` at that revision into a staging directory;
2. checks that `provenance.json` hashes to the pinned value;
3. checks every file against the `processed_files` sha256 list in that provenance (a missing,
   changed or unlisted file fails);
4. only then moves the build into `PHARMGUARD_DATA_DIR`.

Any failure is reported on `/health` and the server fails closed. The token is passed only to
the downloader and never logged or echoed. Tested with a fake downloader.

## Measured locally (2026-09-24, OrbStack on Apple Silicon, public build mounted)

| | |
|---|---|
| Image (linux/arm64) | 167 MB compressed, 564 MB unpacked (`docker image ls` shows 762 MB, which includes storage overhead) |
| Image (linux/amd64, built with buildx) | 174 MB compressed, 560 MB unpacked |
| Cold start to `/health` 200 | 16.9 s on the first run after the build; 2.8 s on later runs |
| End-to-end latency, 47 cases × 5 rounds, deterministic | p50 22.7 ms, p95 125.5 ms (server-side p50 18.1, p95 121.0) |
| Memory after the benchmark | 494 MiB |

EDG-01 (a single drug) is rejected with 422 by design, so 47 of the 48 cases (the suite at
the time) were timed.
Measured with `python scripts/bench_api.py --rounds 5` against a container started with
`PHARMGUARD_RATE_LIMIT=1000/60`. The amd64 image was only smoke-tested, under emulation.
