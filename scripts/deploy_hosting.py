"""Release the Firebase Hosting site that fronts the Cloud Run service (pharmguard.web.app).

Usage:
    python scripts/deploy_hosting.py --dry-run     # print the config, change nothing
    python scripts/deploy_hosting.py               # firebase deploy --only hosting (also clears the CDN cache)

Hosting serves nothing itself: hosting/public/ holds only ignored dotfiles, and one rewrite sends
every path to the Cloud Run service, so there is never a second copy of the page. Each release
clears Hosting's CDN cache, so scripts/deploy_cloudrun.py runs this after every Cloud Run deploy.

Refuses if firebase.json doesn't rewrite every path to the expected service and region, or if
hosting/public/ holds any file Hosting would serve.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "pharmguard-510020"
SITE = "pharmguard"
SERVICE, REGION = "pharmguard", "us-east1"


class Refused(SystemExit):
    pass


def check_config(root: Path = ROOT) -> dict:
    cfg = json.loads((root / "firebase.json").read_text())["hosting"]
    expected = [{"source": "**", "run": {"serviceId": SERVICE, "region": REGION}}]
    if cfg.get("site") != SITE or cfg.get("rewrites") != expected:
        raise Refused(f"REFUSED: firebase.json must rewrite every path to {SERVICE} in {REGION} on site {SITE}")
    if "**/.*" not in cfg.get("ignore", []):
        raise Refused("REFUSED: firebase.json must ignore dotfiles")
    public = root / cfg["public"]
    served = [p for p in public.rglob("*") if p.is_file() and not any(part.startswith(".") for part in
                                                                       p.relative_to(public).parts)]
    if served:
        raise Refused(f"REFUSED: Hosting would serve files itself: {[str(p.relative_to(root)) for p in served]}")
    return cfg


def firebase_bin() -> list:
    found = shutil.which("firebase")
    if not found:
        prefix = subprocess.run(["npm", "prefix", "-g"], capture_output=True, text=True).stdout.strip()
        candidate = Path(prefix) / "bin" / "firebase"
        found = str(candidate) if candidate.exists() else None
    return [found] if found else ["npx", "--yes", "firebase-tools"]


def release(project: str = PROJECT) -> None:
    check_config()
    cmd = firebase_bin() + ["deploy", "--only", f"hosting:{SITE}", "--project", project, "--non-interactive"]
    print("+ " + " ".join(cmd))
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"FAILED: firebase deploy\n{(out.stdout + out.stderr).strip()[-3000:]}")
    print(f"Hosting released: https://{SITE}.web.app (CDN cache cleared)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--project", default=PROJECT)
    args = ap.parse_args()
    cfg = check_config()
    print(f"Site: https://{SITE}.web.app (project {args.project})")
    print(f"Rewrite: every path -> Cloud Run service {SERVICE!r} in {REGION}; public folder {cfg['public']!r} "
          "serves nothing (dotfiles ignored)")
    if args.dry_run:
        print("\nDry run: nothing was released.")
        return 0
    release(args.project)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
