"""Deploy the PharmGuard API to Google Cloud Run from a locally built linux/amd64 image.

Usage:
    python scripts/deploy_cloudrun.py --dry-run          # print every resource and setting, change nothing
    python scripts/deploy_cloudrun.py                    # build, push, deploy, then verify the live service
    python scripts/deploy_cloudrun.py --create-budget    # also create the $5 budget alert (warns only)

The data stays on Hugging Face: the app downloads the public build at start-up from the pinned
dataset revision and verifies it against the provenance sha256 (api/bootstrap.py).

The image is the tested ./Dockerfile, built here for linux/amd64 (no remote build, so Cloud Build
isn't needed). The forbidden-path guard from deploy_space.py runs on the files actually inside the
built image's /app, not on a list of what should be there.

Refuses to deploy if:
- the local build fails the Space checks (profile, synthetic, sources, file hashes);
- the dataset's provenance.json at the pinned revision doesn't match the local build;
- any file in the image's /app matches a forbidden pattern, or /app holds anything besides
  requirements-api.lock, api/ and src/.

After deploying it fails loudly unless (1) the service's latest ready revision runs exactly the
image digest that was pushed and (2) GET /health on the service URL returns this app's response
(status ok, data loaded, public profile, the pinned provenance sha256).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from api.settings import ApiSettings  # noqa: E402
from deploy_space import BUILD, Refused, Upload, check_build, guard  # noqa: E402
from src.data.provenance import PROVENANCE_FILE, file_sha256  # noqa: E402

PROJECT = "pharmguard-510020"
REGION = "us-east1"                       # South Carolina; Tier 1 pricing
REPO = "pharmguard"                       # Artifact Registry (Docker) repository, same region
IMAGE = "api"
SERVICE = "pharmguard"
APIS = ["run.googleapis.com", "artifactregistry.googleapis.com"]
BUDGET_API = "billingbudgets.googleapis.com"   # only with --create-budget
SETTINGS = {
    "cpu": "1",                           # 1 GiB needs >= 0.5 vCPU; concurrency > 1 needs >= 1 vCPU
    "memory": "1Gi",                      # ~400-500 MiB measured, plus the in-memory filesystem copy of the build
    "concurrency": str(ApiSettings.from_env({}).max_concurrency),   # the app's own limit (4)
    "min-instances": "0",
    "max-instances": "1",                 # one instance: the in-memory rate limiter sees all traffic
    "port": "7860",
    "timeout": "120s",                    # above the app's own 90 s LLM timeout (LLM mode is off here)
}
APP_FILES_TOP = {"requirements-api.lock", "api", "src"}


def image_ref(project: str) -> str:
    return f"{REGION}-docker.pkg.dev/{project}/{REPO}/{IMAGE}"


def cleanup_policy() -> list:
    """Keep only the newest image version; delete the rest (Artifact Registry applies this periodically)."""
    return [{"name": "keep-newest", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 1}},
            {"name": "delete-older", "action": {"type": "Delete"}, "condition": {"tagState": "any"}}]


def deploy_args(project: str, image_at_digest: str, env: Dict[str, str]) -> List[str]:
    args = ["gcloud", "run", "deploy", SERVICE, f"--project={project}", f"--region={REGION}",
            f"--image={image_at_digest}", "--allow-unauthenticated", "--ingress=all",
            "--cpu-throttling",           # request-based billing: CPU only while handling requests
            "--cpu-boost", "--execution-environment=gen2", "--quiet"]
    args += [f"--{k}={v}" for k, v in SETTINGS.items()]
    args.append("--set-env-vars=" + ",".join(f"{k}={v}" for k, v in env.items()))
    return args


def repo_exists(listing: str) -> bool:
    """`gcloud artifacts repositories list --format=value(name)` prints bare names (or full paths)."""
    return any(line.strip().split("/")[-1] == REPO for line in listing.splitlines())


def image_guard(paths: List[str]) -> None:
    """The deploy_space guard on the files inside the image's /app, plus an exact top-level check."""
    guard([Upload(p, content=b"") for p in paths], "image")
    top = {p.split("/")[0] for p in paths}
    if top != APP_FILES_TOP:
        raise Refused(f"REFUSED: the image's /app holds {sorted(top)}, expected {sorted(APP_FILES_TOP)}")


def run(cmd: List[str], quiet: bool = False) -> str:
    if not quiet:
        print("+ " + " ".join(cmd))
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(cmd[:4])}\n{out.stderr.strip()[-3000:]}")
    return out.stdout.strip()


def remote_provenance_sha(dataset: str, revision: str) -> str:
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(dataset, f"processed/{PROVENANCE_FILE}", repo_type="dataset", revision=revision)
    return file_sha256(Path(path))


def image_files(tag: str) -> List[str]:
    listing = run(["docker", "run", "--rm", "--platform", "linux/amd64", "--entrypoint", "sh", tag, "-c",
                   "cd /app && find . -type f | sed 's|^./||' | sort"], quiet=True)
    return [ln for ln in listing.splitlines() if ln]


def verify_live(project: str, digest: str, prov_sha: str) -> str:
    """Fail loudly unless the live revision runs `digest` and /health is this app's response."""
    svc = json.loads(run(["gcloud", "run", "services", "describe", SERVICE, f"--project={project}",
                          f"--region={REGION}", "--format=json"], quiet=True))
    url = svc["status"]["url"]
    rev_name = svc["status"]["latestReadyRevisionName"]
    rev = json.loads(run(["gcloud", "run", "revisions", "describe", rev_name, f"--project={project}",
                          f"--region={REGION}", "--format=json"], quiet=True))
    live = rev.get("status", {}).get("imageDigest", "")
    if not live.endswith("@" + digest):
        raise SystemExit(f"FAILED: revision {rev_name} runs {live or '(no digest)'}, not the pushed {digest}")
    traffic = svc["status"].get("traffic", [])
    if not any(t.get("revisionName") == rev_name and t.get("percent") == 100 for t in traffic):
        raise SystemExit(f"FAILED: revision {rev_name} doesn't serve 100% of traffic: {traffic}")
    health, err = None, None
    for _ in range(30):                   # the first request may wait for a cold start
        try:
            with urllib.request.urlopen(url + "/health", timeout=30) as r:
                health = json.load(r)
                break
        except Exception as exc:          # noqa: BLE001 (report after retries)
            err = exc
            time.sleep(5)
    if health is None:
        raise SystemExit(f"FAILED: {url}/health unreachable: {err}")
    expected = {"status": "ok", "data_loaded": True, "profile": "public", "required_profile": "public",
                "provenance_sha256": prov_sha}
    wrong = {k: health.get(k) for k, v in expected.items() if health.get(k) != v}
    if wrong or "attribution" not in health or "disclaimer" not in health:
        raise SystemExit(f"FAILED: {url}/health is not the expected app response: {wrong or health}")
    print(f"Verified: revision {rev_name} runs {digest} and serves 100% of traffic; /health ok "
          f"(public build, provenance {prov_sha[:12]}...).")
    return url


def warn_if_ranges_changed() -> None:
    """Warn (don't refuse) when Google's published lists differ from the pinned copy."""
    import update_proxy_ranges
    try:
        diffs = update_proxy_ranges.changed_since_pinned()
    except Exception as exc:              # noqa: BLE001 (a warning, never a blocker)
        diffs = [f"could not compare with the published lists: {type(exc).__name__}"]
    for d in diffs:
        print(f"WARNING: Google ranges: {d}")


def create_budget(project: str) -> None:
    acct = run(["gcloud", "billing", "projects", "describe", project, "--format=value(billingAccountName)"])
    if not acct:
        raise SystemExit("FAILED: billing isn't enabled for the project")
    run(["gcloud", "services", "enable", BUDGET_API, f"--project={project}"])
    run(["gcloud", "billing", "budgets", "create", f"--billing-account={acct.split('/')[-1]}",
         "--display-name=pharmguard $5", "--budget-amount=5USD", f"--filter-projects=projects/{project}",
         "--threshold-rule=percent=0.5", "--threshold-rule=percent=0.9", "--threshold-rule=percent=1.0"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--project", default=PROJECT)
    ap.add_argument("--dataset", default=None, help="HF dataset repo id (default <hf user>/pharmguard-public-build)")
    ap.add_argument("--revision", default=None, help="pinned dataset commit (default: the dataset's current commit)")
    ap.add_argument("--trusted-proxy-hops", type=int, default=1)
    ap.add_argument("--trusted-proxy-ranges", default="google", choices=["google", ""],
                    help="pinned ranges whose X-Forwarded-For hop is stepped past ('' = none)")
    ap.add_argument("--create-budget", action="store_true", help="also create the $5 budget alert (warns only)")
    args = ap.parse_args()

    from huggingface_hub import HfApi
    api = HfApi()
    dataset = args.dataset or f"{api.whoami()['name']}/pharmguard-public-build"
    revision = args.revision or api.repo_info(dataset, repo_type="dataset").sha
    check_build(BUILD)
    prov_sha = file_sha256(BUILD / PROVENANCE_FILE)
    remote_sha = remote_provenance_sha(dataset, revision)
    if remote_sha != prov_sha:
        raise Refused(f"REFUSED: {dataset}@{revision[:12]} provenance {remote_sha[:12]}... != local {prov_sha[:12]}...")
    if args.trusted_proxy_ranges:
        warn_if_ranges_changed()
    env = {"PHARMGUARD_HF_DATASET": dataset, "PHARMGUARD_HF_REVISION": revision,
           "PHARMGUARD_HF_PROVENANCE_SHA256": prov_sha, "PHARMGUARD_TRUSTED_PROXY_HOPS": str(args.trusted_proxy_hops),
           # Firebase Hosting's CDN hop is Google-operated: key on the client entry Hosting writes before it.
           "PHARMGUARD_TRUSTED_PROXY_RANGES": args.trusted_proxy_ranges}
    ref = image_ref(args.project)
    tag = f"{ref}:{time.strftime('%Y%m%d-%H%M%S')}"

    print(f"Project: {args.project}   Region: {REGION}")
    print(f"APIs to enable: {', '.join(APIS)}" + (f", {BUDGET_API} (budget only)" if args.create_budget else ""))
    print(f"Artifact Registry: {REGION}-docker.pkg.dev/{args.project}/{REPO} (Docker), cleanup policy: "
          + json.dumps(cleanup_policy()))
    print(f"Image: {tag}  (docker buildx --platform linux/amd64 --provenance=false, from ./Dockerfile)")
    print(f"Cloud Run service {SERVICE!r}: " + ", ".join(f"{k}={v}" for k, v in SETTINGS.items())
          + ", request-based billing (--cpu-throttling), startup CPU boost, gen2, public (allUsers invoker), "
            "ingress all")
    print("Environment variables:" + "".join(f"\n  {k}={v}" for k, v in env.items()))
    print(f"Dataset: https://huggingface.co/datasets/{dataset} @ {revision} (provenance matches the local build)")
    print("Budget: $5 on this project, alerts at 50/90/100% (warns only; max-instances=1 is the real cap)"
          + ("" if args.create_budget else " -- not created unless --create-budget"))
    print("Secrets: none (the dataset is public).")
    if args.dry_run:
        files = image_files("pharmguard-api:cloudrun") if shutil.which("docker") else []
        if files:
            image_guard(files)
            print(f"Local image pharmguard-api:cloudrun /app: {len(files)} files, guard passed.")
        print("\nDry run: nothing was built, pushed, created or deployed.")
        return 0

    run(["gcloud", "services", "enable", *APIS, f"--project={args.project}"])
    repos = run(["gcloud", "artifacts", "repositories", "list", f"--project={args.project}",
                 f"--location={REGION}", "--format=value(name)"], quiet=True)
    if not repo_exists(repos):
        run(["gcloud", "artifacts", "repositories", "create", REPO, "--repository-format=docker",
             f"--location={REGION}", f"--project={args.project}", "--description=PharmGuard API images"])
    with tempfile.TemporaryDirectory() as tmp:
        policy = Path(tmp) / "cleanup-policy.json"
        policy.write_text(json.dumps(cleanup_policy()))
        run(["gcloud", "artifacts", "repositories", "set-cleanup-policies", REPO, f"--project={args.project}",
             f"--location={REGION}", f"--policy={policy}", "--no-dry-run"])
    run(["docker", "buildx", "build", "--platform", "linux/amd64", "--provenance=false", "--load", "-t", tag, str(ROOT)])
    image_guard(image_files(tag))
    run(["gcloud", "auth", "configure-docker", f"{REGION}-docker.pkg.dev", "--quiet"], quiet=True)
    run(["docker", "push", tag])
    repo_digest = run(["docker", "image", "inspect", tag, "--format", "{{json .RepoDigests}}"], quiet=True)
    digests = [d for d in json.loads(repo_digest) if d.startswith(ref + "@")]
    if len(digests) != 1 or not re.fullmatch(r".+@sha256:[0-9a-f]{64}", digests[0]):
        raise SystemExit(f"FAILED: no single pushed digest for {ref}: {repo_digest}")
    image_at_digest = digests[0]
    digest = image_at_digest.split("@", 1)[1]
    print(f"Pushed {image_at_digest}")
    run(deploy_args(args.project, image_at_digest, env))
    url = verify_live(args.project, digest, prov_sha)
    if (ROOT / "firebase.json").exists():
        import deploy_hosting            # re-release Hosting: clears its CDN cache so no stale page is served
        deploy_hosting.release(args.project)
    if args.create_budget:
        create_budget(args.project)
    print(f"Live: {url}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
