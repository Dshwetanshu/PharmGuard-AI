# Deployment

## Live: Google Cloud Run

- **App:** https://pharmguard-rga6x46s6q-ue.a.run.app (also https://pharmguard-299086968921.us-east1.run.app)
- **Data:** https://huggingface.co/datasets/shwetanshu2211/pharmguard-public-build, pinned at revision
  `a7b844d0d71994670f89d723fe5577e142e4c10e`. The app downloads the public build at start-up and verifies
  it against the provenance sha256 `fc037dc5f67b9c0dd05c4664e48a4888a155d285dc0e1a11369fc971dab31073`
  (api/bootstrap.py); without a verified build `/health` says why and `/v1/check` returns 503.

The service runs the tested `./Dockerfile` image, built locally for linux/amd64 and deployed by digest.

| Setting | Value |
|---|---|
| Project, region | `pharmguard-510020`, `us-east1` |
| Image | Artifact Registry `us-east1-docker.pkg.dev/pharmguard-510020/pharmguard/api`; cleanup policy keeps only the newest version |
| Instances | min 0, max 1 (the in-memory rate limiter then sees all traffic) |
| Billing | request-based (CPU only while handling requests, starting or stopping), startup CPU boost, gen2 |
| Size | 1 vCPU, 1 GiB (below 1 vCPU Cloud Run forces concurrency 1; the filesystem is in memory) |
| Concurrency | 4, the app's own limit (`ApiSettings.max_concurrency`) |
| Port, timeout | 7860, 120 s |
| Access | public HTTPS (`allUsers` has `roles/run.invoker`); HTTP redirects to HTTPS |
| Env | `PHARMGUARD_HF_DATASET`, `PHARMGUARD_HF_REVISION`, `PHARMGUARD_HF_PROVENANCE_SHA256`, `PHARMGUARD_TRUSTED_PROXY_HOPS=1` |
| APIs enabled | Cloud Run, Artifact Registry, Billing Budgets (for the budget only); no Cloud Build |
| Budget | $5 on the project, email alerts at 50/90/100%. It only warns; max 1 instance is the real cap |

### Deploy

```bash
python scripts/deploy_cloudrun.py --dry-run     # every resource and setting; guard on the local image
python scripts/deploy_cloudrun.py               # build, push, deploy, verify
```

Needs `gcloud` (logged in, project selected, billing enabled), Docker, and `hf auth login` (read-only use).
The script refuses if the local build fails the dataset checks, if the dataset's provenance at the
pinned revision differs from the local build, or if the built image's `/app` holds a forbidden path or
anything besides `requirements-api.lock`, `api/` and `src/` (the guard from `scripts/deploy_space.py`).
After deploying it fails unless the live revision runs the pushed digest with 100% of traffic and
`/health` returns this app's response (public profile, the pinned provenance sha256).

### Client IPs and rate limiting

Measured on 28 September 2026: Google's front end adds exactly one `X-Forwarded-For` entry (the client)
and keeps anything the client sent before it (0, 1 and 2 client-supplied entries arrived as 1, 2 and 3).
So `PHARMGUARD_TRUSTED_PROXY_HOPS=1`: the rate-limit key is the rightmost entry, which the client can't
forge. Checked live: 22 requests to `/v1/check`, each with a different forged `X-Forwarded-For`, got
200 twenty times and then 429 with `Retry-After`. `/health` reports only counts (`proxy`), never addresses.

### Live verification (28 September 2026)

- `/health`: status ok, data loaded, profile public, provenance sha256 as pinned; six attribution notices.
- The six-drug check (Coumadin, warfarin, aspirin, simvastatin, clarithromycin, xyz123): deterministic
  report, validation passed (6 claims), 3 Major, 1 Minor, 2 ungraded listings, duplicate notice,
  xyz123 unrecognized, 6 grid cells. The page renders every state at 1440 and 375 px with no CSP
  violations and only same-origin requests.
- Headers: `Content-Security-Policy` (as in api/app.py), `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `X-Request-ID`. No HSTS header; `.app` is
  on the browsers' HSTS preload list.
- Rejected requests (JSON error with a request ID, no stack trace): malformed JSON 422, non-object body
  422, 1 or 13 drugs 422, markup in a name 422, LLM mode without a key 401, 20 KB body 413,
  wrong method 405, unknown path 404.
- Latency from the machine used for this deployment: `/health` p50 79 ms, p95 111 ms (n=50); six-drug check
  p50 138 ms, p95 161 ms (n=40), of which the server reported p50 54 ms, p95 70 ms.
- Cold start: after 25 minutes idle (scaled to zero; the log shows a new instance starting), the first
  `/health` took 14.9 s end to end; the next one 82 ms. The deployment's first instance took 12.9 s from
  start to ready: about 7 s before the app's start-up began (image and Python start), then about 6 s to
  download, verify and load the build.

### Cost

Request-based billing; the free tier is 180,000 vCPU-seconds, 360,000 GiB-seconds and 2 million
requests a month (Tier 1 prices after that: $0.000024 per vCPU-second, $0.0000025 per GiB-second,
$0.40 per million requests). At demo traffic this is about $0: 1,000 visits (about 9 requests each)
plus 100 cold starts use roughly 1% of the free tier, and the one image stays under Artifact Registry's
0.5 GB free storage. The worst case the cap allows is one instance busy around the clock: about 2.63 million
vCPU-seconds and GiB-seconds a month, roughly $59 CPU + $6 memory after the free tier, plus
$0.40 per million requests (estimate, not measured). The budget alert warns; it doesn't stop the service.

## Alternative: Hugging Face Spaces (PRO)

`scripts/deploy_space.py` deploys the same image as a Docker Space next to the dataset, with the same
environment variables (measure the proxy's `X-Forwarded-For` count before trusting hops; it was never
measured because the Space was never created). Docker Spaces on
the free cpu-basic hardware now need a PRO subscription: creating the Space returned `402 Payment
Required` on 26 September 2026. The dataset upload in the same run succeeded and is the data source
above.

## Not used

- Vercel container images weren't available on the Hobby plan as of 26 September 2026 (the build fell back to zero-config detection); the attempt is in commit 2a6b5b0.
