# Deployment

## Live

- **https://pharmguard.web.app**: Firebase Hosting in front of the Cloud Run service (the address to share).
- **https://pharmguard-rga6x46s6q-ue.a.run.app**: the Cloud Run service directly (also
  https://pharmguard-299086968921.us-east1.run.app). It stays reachable, because Hosting's rewrite
  reaches the service through it (see "Not used").
- **Data:** https://huggingface.co/datasets/shwetanshu2211/pharmguard-public-build, pinned at revision
  `a7b844d0d71994670f89d723fe5577e142e4c10e`. The app downloads the public build at start-up and verifies
  it against the provenance sha256 `fc037dc5f67b9c0dd05c4664e48a4888a155d285dc0e1a11369fc971dab31073`
  (api/bootstrap.py); without a verified build `/health` says why and `/v1/check` returns 503.

## Cloud Run

The service runs the tested `./Dockerfile` image, built locally for linux/amd64 and deployed by digest.

| Setting | Value |
|---|---|
| Project, region | `pharmguard-510020`, `us-east1` |
| Image | Artifact Registry `us-east1-docker.pkg.dev/pharmguard-510020/pharmguard/api`; cleanup policy keeps only the newest version |
| Instances | min 0, max 1 (the in-memory rate limiter then sees all traffic) |
| Billing | request-based (CPU only while handling requests, starting or stopping), startup CPU boost, gen2 |
| Size | 1 vCPU, 1 GiB (below 1 vCPU Cloud Run forces concurrency 1; the filesystem is in memory) |
| Concurrency | 4, the app's own limit (`ApiSettings.max_concurrency`) |
| Port, timeout | 7860, 120 s (Hosting cuts requests at 60 s; the app's own limits are 20 s per check and 10 s for FAERS) |
| Access | public HTTPS (`allUsers` has `roles/run.invoker`); HTTP redirects to HTTPS |
| Env | `PHARMGUARD_HF_DATASET`, `PHARMGUARD_HF_REVISION`, `PHARMGUARD_HF_PROVENANCE_SHA256`, `PHARMGUARD_TRUSTED_PROXY_HOPS=1`, `PHARMGUARD_TRUSTED_PROXY_RANGES=google` |
| APIs enabled | Cloud Run, Artifact Registry, Billing Budgets (for the budget only), and the Firebase APIs that adding Firebase enables; no Cloud Build |
| Budget | $5 on the project, email alerts at 50/90/100%. It only warns; max 1 instance is the real cap |

## Firebase Hosting

`firebase.json`: site `pharmguard`, one rewrite sending every path (`**`) to the Cloud Run service
`pharmguard` in `us-east1`. `hosting/public/` holds only an ignored `.gitkeep`, so Hosting serves nothing
itself and there is never a second copy of the page. `scripts/deploy_hosting.py` checks that and releases
the site. Each release clears Hosting's CDN cache, and `scripts/deploy_cloudrun.py` re-releases Hosting
after every Cloud Run deploy, so the CDN never serves a page from an older build.

### Caching

The app sets `Cache-Control` by path (api/app.py):

| Path | Cache-Control | Behaviour |
|---|---|---|
| `/static/*` (CSS, JS, fonts, favicon) | `public, max-age=3600, s-maxage=2592000` | kept by the CDN; browsers revalidate after an hour |
| `/` | `public, max-age=0, s-maxage=2592000`, with an `ETag` | kept by the CDN; browsers always revalidate |
| everything else (`/health`, `/v1/check`, `/docs`), and every error | `no-store` | never cached |

Every `/static/` URL in the page, and every font URL in the stylesheet, carries `?v=<build id>` (a hash
of the static files), so a page from a new release never loads a script or stylesheet cached for an old
one. The page still calls `/health` on load: that wakes the container while the visitor types.

Checked live: static files return `x-cache: HIT` after the first request. Twenty cached requests for
`app.js` and `style.css` produced no container log lines, while a `/health` request in the same window
did. `/health` and `/v1/check` always return `x-cache: MISS`.

## Deploy

```bash
python scripts/deploy_cloudrun.py --dry-run     # every resource and setting; guard on the local image
python scripts/deploy_cloudrun.py               # build, push, deploy, verify, re-release Hosting
python scripts/deploy_hosting.py --dry-run      # Hosting config check only
python scripts/update_proxy_ranges.py           # refresh the pinned Google ranges (the deploy does this too)
python scripts/update_proxy_ranges.py --check   # compare only
```

Needs `gcloud` (logged in, project selected, billing enabled), Docker, `hf auth login` (read-only use)
and the Firebase CLI (`firebase login`). `deploy_cloudrun.py` refuses if:
- the local build fails the dataset checks;
- the dataset's provenance at the pinned revision differs from the local build;
- the built image's `/app` holds a forbidden path, or anything besides `requirements-api.lock`, `api/`
  and `src/` (the guard from `scripts/deploy_space.py`).

Before building, it refreshes the pinned Google address list (see below) and prints what changed; commit
`api/trusted_proxies/google.json` with the deploy. After deploying, it fails unless the live revision runs
the pushed digest with 100% of traffic and `/health` returns this app's response (public profile, the
pinned provenance sha256).

## Client IPs and rate limiting

The limit is 20 checks per client per 60 s, counted in memory (one instance, so one counter).
Measured live on 28 September 2026 (header names and counts only; addresses are never logged):

- **Directly:** Google's front end appends the caller's address to `X-Forwarded-For` and keeps anything
  the caller sent in front of it (0, 1 and 2 caller entries arrived as 1, 2 and 3). Only the rightmost
  entry can be trusted.
- **Through Hosting:** Hosting drops the caller's `X-Forwarded-For` and `Fastly-Client-IP`, writes
  `client, <CDN address>`, and Google's front end sees the CDN. The CDN address changes between
  requests, so keying on it would let every request through. It is not in Fastly's published ranges;
  it is in Google's own ranges (30 of 30 requests).

**Rule** (`api/ratelimit.py`, `PHARMGUARD_TRUSTED_PROXY_HOPS=1`, `PHARMGUARD_TRUSTED_PROXY_RANGES=google`):
if the rightmost `X-Forwarded-For` entry is in the pinned Google-operated list, key on the entry just
before it (the client address Hosting writes); otherwise key on the rightmost entry.

- **The list:** `api/trusted_proxies/google.json` holds Google's published `goog.json` minus `cloud.json`
  (Cloud customers' ranges), with both source URLs, their versions and the fetch date. It is built by
  `scripts/update_proxy_ranges.py`.
- **Stale lists:** a list more than 30 days old loads as empty. The key then falls back to the rightmost
  entry, which is still unforgeable. But through Hosting that entry is the CDN address, which changes
  between requests, so web.app traffic is effectively no longer limited per client.
- **Diagnostics:** `/health` reports counts and yes/no fields under `proxy`, never addresses:
  `rightmost_hop_in_google_list`, `trusted_proxy_entries_skipped`, and `proxy_list_stale`
  (yes once the pinned list is past 30 days).

**Monthly refresh.** Every `scripts/deploy_cloudrun.py` run refreshes the list and renews its date. If the
service hasn't been redeployed for close to a month, redeploy it:
1. Run `python scripts/deploy_cloudrun.py`, then commit `api/trusted_proxies/google.json`.
2. Check that `https://pharmguard.web.app/health` shows `"proxy_list_stale": false`.

If Google's lists can't be fetched during a deploy, the script warns and deploys with the pinned copy.

**Proven live** with forged `X-Forwarded-For` (including Google addresses) and forged `Fastly-Client-IP`
on every request: the 21st request in the window got 429 on https://pharmguard.web.app and on the
run.app URL. Both paths key on the same real client.

**Residual risk:** a Google-operated service that lets its users send custom headers from Google
addresses could forge the key on the direct run.app path. Its request would arrive with a Google
address as the rightmost entry, so the entry before it, which the caller chose, would become the key.
The caps still bound the cost: one instance, 4 concurrent checks, 20 s per check, and the project is on
the Google Cloud Free Trial.

## Live verification (28 September 2026)

On https://pharmguard.web.app (and before Hosting, the same checks on the run.app URL):

- `/health`: status ok, data loaded, profile public, provenance sha256 as pinned; six attribution notices.
- The six-drug check (Coumadin, warfarin, aspirin, simvastatin, clarithromycin, xyz123): deterministic
  report, validation passed (6 claims), 3 Major, 1 Minor, 2 ungraded listings, duplicate notice,
  xyz123 unrecognized, 6 grid cells. The page renders every state at 1440 and 375 px with no CSP
  violations, fonts loaded and only same-origin requests.
- Headers arrive intact through Hosting: `Content-Security-Policy` (as in api/app.py),
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`,
  `X-Request-ID`. Hosting adds `Strict-Transport-Security: max-age=31556926; includeSubDomains; preload`.
  HTTP redirects to HTTPS (301 on web.app, 302 on run.app).
- Rejected requests (JSON error with a request ID, no stack trace): malformed JSON 422, 1 or 13 drugs 422,
  markup in a name 422, LLM mode without a key 401, 20 KB body 413, wrong method 405, unknown path 404.
- Latency from the machine used for this deployment:

  | Path | Request | p50 | p95 | n |
  |---|---|---|---|---|
  | web.app | `/health` | 116 ms | 205 ms | 50 |
  | web.app | cached `style.css` | 66 ms | 82 ms | 30 |
  | web.app | six-drug check (server p50 56 ms, p95 77 ms) | 174 ms | 236 ms | 38 |
  | run.app | `/health` | 79 ms | 111 ms | 50 |
  | run.app | six-drug check (server p50 54 ms, p95 70 ms) | 138 ms | 161 ms | 40 |

- Cold start: on run.app, after 25 minutes idle (scaled to zero; the log shows a new instance
  starting), the first `/health` took 14.9 s end to end and the next one 82 ms. A deployment's first
  instance took 12.9 s from start to ready: about 7 s before the app's start-up began (image and Python
  start), then about 6 s to download, verify and load the build. Through web.app, after 25 minutes idle
  (again a new instance in the log), the first `/health` took 15.7 s and the next one 117 ms.

## Cost

**Cloud Run** uses request-based billing. The monthly free tier is 180,000 vCPU-seconds,
360,000 GiB-seconds and 2 million requests. After that, Tier 1 prices are $0.000024 per vCPU-second,
$0.0000025 per GiB-second and $0.40 per million requests.

**At demo traffic this is about $0.** 1,000 visits (about 9 requests each) plus 100 cold starts use
roughly 1% of the free tier. With the CDN, most of each visit's requests never reach the container.
The one image stays under Artifact Registry's 0.5 GB free storage.

**Hosting** (Blaze plan) includes 10 GB storage (it stores nothing) and 360 MB/day of transfer at no
cost, then $0.15/GB. That covers roughly 1,900 first visits a day at about 190 KB each.

**Worst case the caps allow:** one instance busy around the clock, about 2.63 million vCPU-seconds and
GiB-seconds a month. That is roughly $59 CPU + $6 memory after the free tier, plus $0.40 per million
requests (an estimate, not measured). The budget alert warns; it doesn't stop the service.

## Alternative: Hugging Face Spaces (PRO)

`scripts/deploy_space.py` deploys the same image as a Docker Space next to the dataset, with the same
dataset variables. Leave `PHARMGUARD_TRUSTED_PROXY_RANGES` unset there (the Google list describes
Firebase Hosting's hop), and measure the Spaces proxy's `X-Forwarded-For` count before trusting hops: it
was never measured, because the Space was never created.

Docker Spaces on the free cpu-basic hardware now need a PRO subscription: creating the Space returned
`402 Payment Required` on 26 September 2026. The dataset upload in the same run succeeded and is the
data source above.

## Not used

- **Turning off the run.app URL** (`gcloud run services update --no-default-url`), to make Hosting the
  only path, broke Hosting's rewrite: both URLs returned 404. It was re-enabled within a minute on
  28 September 2026.
- **Fastly's published ranges** don't contain Hosting's CDN hop (measured), so the key uses Google's
  ranges instead.
- **Vercel:** container images weren't available on the Hobby plan as of 26 September 2026 (the build
  fell back to zero-config detection); the attempt is in commit 2a6b5b0.
