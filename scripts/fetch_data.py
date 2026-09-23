"""Download the real datasets into data/raw/ (gitignored) and record a sha256 manifest.

Usage:
    python scripts/fetch_data.py                    # public profile: RxNorm, DDInter, SIDER
    python scripts/fetch_data.py --with-twosides    # + TWOSIDES (research profile; ~390 MB, local only)

Pinned URLs and hashes live in src/data/sources.py. A file whose sha256 (or the
publisher's md5) doesn't match its pin is rejected. data/raw/MANIFEST.json records
URL, version, license, download date, bytes and sha256 per file; ingestion copies
it into provenance.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.sources import SOURCES  # noqa: E402

UA = {"User-Agent": "PharmGuard/1.0 (research prototype; data fetch)"}


def _hashes(path: Path):
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
            md5.update(chunk)
    return sha.hexdigest(), md5.hexdigest()


def fetch(raw_dir: Path, keys, force: bool = False) -> dict:
    manifest_path = raw_dir / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for key in keys:
        src = SOURCES[key]
        if not src.files:
            print(f"[{key}] no downloadable files: {src.note}")
            continue
        entries = []
        for f in src.files:
            dest = raw_dir / key / f.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if force or not dest.exists():
                print(f"[{key}] downloading {f.url}")
                req = urllib.request.Request(f.url, headers=UA)
                tmp = dest.with_suffix(dest.suffix + ".part")
                with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as out:
                    while chunk := resp.read(1 << 20):
                        out.write(chunk)
                tmp.rename(dest)
            sha, md5 = _hashes(dest)
            if f.sha256 and sha != f.sha256:
                raise SystemExit(f"[{key}] sha256 mismatch for {f.name}: {sha} != pinned {f.sha256}")
            if f.md5 and md5 != f.md5:
                raise SystemExit(f"[{key}] md5 mismatch for {f.name}: {md5} != publisher {f.md5}")
            prev = next((e for e in manifest.get(key, {}).get("files", []) if e["name"] == f.name), {})
            entries.append({"name": f.name, "url": f.url, "bytes": dest.stat().st_size, "sha256": sha,
                            "sha256_pinned": bool(f.sha256), "md5_verified": bool(f.md5),
                            "downloaded_at": prev.get("downloaded_at") if prev.get("sha256") == sha
                            else dt.date.today().isoformat()})
            print(f"[{key}] {f.name}: {entries[-1]['bytes']:,} bytes sha256={sha[:16]}…"
                  + (" (pinned ✓)" if f.sha256 else " (not yet pinned)") + (" md5 ✓" if f.md5 else ""))
        manifest[key] = {"title": src.title, "version": src.version, "license": src.license,
                         "homepage": src.homepage, "profiles": list(src.profiles), "files": entries}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--with-twosides", action="store_true", help="Also fetch TWOSIDES (research profile only).")
    ap.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--force", action="store_true", help="Re-download even if files exist.")
    args = ap.parse_args()
    keys = ["rxnorm", "drugbank", "ddinter", "sider"] + (["twosides"] if args.with_twosides else [])
    fetch(Path(args.raw_dir), keys, args.force)
    print(f"Manifest: {Path(args.raw_dir) / 'MANIFEST.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
