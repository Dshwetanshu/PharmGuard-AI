"""Deploy the PharmGuard API to Vercel (container image on Fluid compute) with the Vercel CLI.

Usage:
    python scripts/deploy_vercel.py --dry-run     # list every file that would be uploaded, change nothing
    python scripts/deploy_vercel.py               # stage, set env vars, `vercel deploy --prod`

The data stays on Hugging Face: the app downloads the public build at start-up from the pinned
dataset revision and verifies it against the provenance sha256 (api/bootstrap.py).

What gets uploaded: the CLI uploads a folder, so this script never runs it in the repo. It copies
exactly STAGE_FILES and STAGE_DIRS (the same code the Space image used, plus Dockerfile.vercel)
into .vercel-deploy/ and deploys from there; .vercelignore is a second, allowlist layer. The
dry run prints that list with sizes.

Refuses to deploy if:
- the local build fails the Space checks (profile, synthetic, sources, file hashes);
- the dataset's provenance.json at the pinned revision doesn't match the local build;
- any staged path matches a forbidden pattern (research build, TWOSIDES, notes/, CLAUDE.md, .env*,
  data/, review/, .venv, caches), or the staging folder holds anything not on the list;
- .vercelignore doesn't allow exactly the staged top-level entries.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from deploy_space import BUILD, Refused, Upload, check_build, guard, show  # noqa: E402
from src.data.provenance import PROVENANCE_FILE, file_sha256  # noqa: E402

STAGE = ROOT / ".vercel-deploy"
STAGE_FILES = ["Dockerfile.vercel", ".vercelignore", "requirements-api.lock", "LICENSE"]
STAGE_DIRS = ["api", "src"]
# On top of deploy_space.FORBIDDEN (substrings anywhere: research, twosides, notes/, claude.md, .claude/,
# .env, data/raw, review/, __pycache__, .pyc): top-level folders that must never be uploaded, and caches.
FORBIDDEN_ROOTS = ("data", "notes", ".venv", "venv", "tests", "results", ".git", ".vercel-deploy", "review")
FORBIDDEN_ANYWHERE = (".pytest_cache", ".mypy_cache", ".ruff_cache", ".ipynb_checkpoints", ".ds_store")
PORT = "8080"


def planned() -> List[Upload]:
    out = [Upload(f, local=ROOT / f) for f in STAGE_FILES]
    for d in STAGE_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc" and p.name != ".DS_Store":
                out.append(Upload(str(p.relative_to(ROOT)), local=p))
    return out


def vercel_guard(uploads: List[Upload]) -> None:
    guard(uploads, "Vercel")                          # the Space rules, unchanged
    for u in uploads:
        path = u.path_in_repo.lower()
        top = path.split("/")[0]
        if top in FORBIDDEN_ROOTS:
            raise Refused(f"REFUSED: Vercel file {u.path_in_repo!r} is under forbidden folder {top!r}")
        for bad in FORBIDDEN_ANYWHERE:
            if bad in path:
                raise Refused(f"REFUSED: Vercel file {u.path_in_repo!r} matches forbidden pattern {bad!r}")


def vercelignore_allows() -> set:
    """Top-level names the allowlist .vercelignore lets through (lines of the form !name)."""
    lines = [ln.strip() for ln in (ROOT / ".vercelignore").read_text().splitlines()]
    if "/*" not in lines:
        raise Refused("REFUSED: .vercelignore must start from '/*' (ignore everything, then allow)")
    return {ln[1:].strip("/") for ln in lines if ln.startswith("!")}


def check_vercelignore(uploads: List[Upload]) -> None:
    top = {u.path_in_repo.split("/")[0] for u in uploads}
    allowed = vercelignore_allows()
    if top != allowed:
        raise Refused(f"REFUSED: .vercelignore allows {sorted(allowed)} but the stage holds {sorted(top)}")


def remote_provenance_sha(dataset: str, revision: str) -> str:
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(dataset, f"processed/{PROVENANCE_FILE}", repo_type="dataset", revision=revision)
    return file_sha256(Path(path))


def stage(uploads: List[Upload]) -> None:
    """Rebuild .vercel-deploy/ with exactly `uploads` (keeping only the CLI's .vercel/ link)."""
    STAGE.mkdir(exist_ok=True)
    for p in STAGE.iterdir():
        if p.name != ".vercel":
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    for u in uploads:
        dest = STAGE / u.path_in_repo
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(u.local, dest)
    on_disk = sorted(str(p.relative_to(STAGE)) for p in STAGE.rglob("*")
                     if p.is_file() and ".vercel" not in p.relative_to(STAGE).parts[:1])
    if on_disk != sorted(u.path_in_repo for u in uploads):
        raise Refused("REFUSED: the staging folder differs from the planned upload list")


def run(cmd: List[str], stdin: str = None) -> str:
    out = subprocess.run(cmd, cwd=STAGE, input=stdin, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"{' '.join(cmd[:3])} failed:\n{out.stderr.strip()[-2000:]}")
    return out.stdout.strip()


def set_env(name: str, value: str) -> None:
    """Production env var, replacing any existing value (values are not secrets)."""
    subprocess.run(["vercel", "env", "rm", name, "production", "--yes"], cwd=STAGE, capture_output=True)
    run(["vercel", "env", "add", name, "production"], stdin=value + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--project", default="pharmguard")
    ap.add_argument("--dataset", default=None, help="HF dataset repo id (default <hf user>/pharmguard-public-build)")
    ap.add_argument("--revision", default=None, help="pinned dataset commit (default: the dataset's current commit)")
    ap.add_argument("--trusted-proxy-hops", type=int, default=1)
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
    uploads = planned()
    vercel_guard(uploads)
    check_vercelignore(uploads)
    env: Dict[str, str] = {"PHARMGUARD_HF_DATASET": dataset, "PHARMGUARD_HF_REVISION": revision,
                           "PHARMGUARD_HF_PROVENANCE_SHA256": prov_sha,
                           "PHARMGUARD_TRUSTED_PROXY_HOPS": str(args.trusted_proxy_hops), "PORT": PORT}
    print(f"Dataset: https://huggingface.co/datasets/{dataset} @ {revision}")
    print(f"provenance.json sha256 (local build = dataset at that revision): {prov_sha}")
    print("Checks passed: build checks, remote provenance matches, no forbidden paths, .vercelignore matches.")
    show(f"Vercel upload (project {args.project!r}, from {STAGE.relative_to(ROOT)}/)", uploads)
    print("\nProduction environment variables:" + "".join(f"\n  {k}={v}" for k, v in env.items()))
    print("Secrets: none (the dataset is public).")
    if args.dry_run:
        print("\nDry run: nothing was staged, created or uploaded.")
        return 0

    stage(uploads)
    if not (STAGE / ".vercel" / "project.json").exists():
        run(["vercel", "link", "--yes", "--project", args.project])
    for k, v in env.items():
        set_env(k, v)
    url = run(["vercel", "deploy", "--prod", "--yes"]).splitlines()[-1]
    print(f"Deployed: {url}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
