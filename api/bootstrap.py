"""Optional start-up step: fetch the public build from a private Hugging Face dataset.

Enabled when PHARMGUARD_HF_DATASET is set. The revision must be a pinned commit
sha, and the downloaded provenance.json must hash to PHARMGUARD_HF_PROVENANCE_SHA256.
That provenance lists a sha256 for every other file in the build
(processed_files), and each downloaded file is checked against it. Any mismatch
raises BuildError: the service then reports why on /health and returns 503,
it never serves an unverified build. The token (HF_TOKEN, a read-only Space
secret) is passed to the downloader and never logged.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Callable, Optional

from src.data.provenance import PROVENANCE_FILE, file_sha256

# downloader(repo_id, revision, token, dest_dir) -> directory containing processed/
Downloader = Callable[[str, str, Optional[str], Path], Path]
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class BuildError(RuntimeError):
    """The build can't be used; the message is safe to show on /health."""


def hf_snapshot_download(repo_id: str, revision: str, token: Optional[str], dest: Path) -> Path:
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(repo_id=repo_id, repo_type="dataset", revision=revision, token=token,
                                  local_dir=str(dest), allow_patterns=["processed/*"]))


def verify_build(processed_dir: Path, expected_provenance_sha256: str) -> dict:
    """Check provenance.json against the pin, then every file against provenance."""
    prov_path = Path(processed_dir) / PROVENANCE_FILE
    if not prov_path.exists():
        raise BuildError("downloaded build has no processed/provenance.json")
    got = file_sha256(prov_path)
    if got != expected_provenance_sha256:
        raise BuildError(f"provenance.json sha256 {got[:12]}… does not match the pinned {expected_provenance_sha256[:12]}…")
    prov = json.loads(prov_path.read_text())
    files = prov.get("processed_files")
    if not files:
        raise BuildError("provenance.json lists no processed_files to verify")
    for name, sha in files.items():
        path = Path(processed_dir) / name
        if not path.exists():
            raise BuildError(f"{name} is listed in provenance but missing")
        if file_sha256(path) != sha:
            raise BuildError(f"{name} does not match its sha256 in provenance")
    extra = sorted(p.name for p in Path(processed_dir).iterdir()
                   if p.is_file() and p.name != PROVENANCE_FILE and p.name not in files)
    if extra:
        raise BuildError(f"files not listed in provenance: {extra}")
    return prov


def ensure_build(settings, downloader: Downloader = hf_snapshot_download) -> Optional[dict]:
    """Download and verify the build if a Hugging Face dataset is configured.
    Returns the verified provenance, or None when no download is configured."""
    if not settings.hf_dataset:
        return None
    if not settings.hf_revision or not _COMMIT_SHA.match(settings.hf_revision):
        raise BuildError("PHARMGUARD_HF_REVISION must be a pinned 40-character commit sha")
    if not settings.hf_provenance_sha256 or not re.fullmatch(r"[0-9a-f]{64}", settings.hf_provenance_sha256):
        raise BuildError("PHARMGUARD_HF_PROVENANCE_SHA256 must be the 64-character sha256 of provenance.json")
    dest = Path(settings.data_dir)
    staging = dest.parent / (dest.name + ".download")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        root = downloader(settings.hf_dataset, settings.hf_revision, settings.hf_token, staging)
    except Exception as exc:   # network, auth, missing revision: report the class, not the token
        shutil.rmtree(staging, ignore_errors=True)
        raise BuildError(f"download from {settings.hf_dataset}@{settings.hf_revision[:12]} failed: "
                         f"{type(exc).__name__}") from None
    try:
        prov = verify_build(Path(root) / "processed", settings.hf_provenance_sha256)
    except BuildError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    # Verified: move into place (replacing any earlier copy).
    shutil.rmtree(dest / "processed", ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.move(str(Path(root) / "processed"), str(dest / "processed"))
    shutil.rmtree(staging, ignore_errors=True)
    return prov
