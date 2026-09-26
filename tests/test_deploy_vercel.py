"""scripts/deploy_vercel.py uploads only the image's code and refuses forbidden paths (no uploads in tests)."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("deploy_vercel", ROOT / "scripts" / "deploy_vercel.py")
dv = importlib.util.module_from_spec(spec)
sys.modules["deploy_vercel"] = dv
spec.loader.exec_module(dv)


def test_upload_list_is_the_image_code_only():
    ups = dv.planned()
    dv.vercel_guard(ups)
    dv.check_vercelignore(ups)
    names = {u.path_in_repo for u in ups}
    assert {"Dockerfile.vercel", ".vercelignore", "requirements-api.lock", "LICENSE", "api/app.py",
            "api/static/index.html", "src/graph/builder.py"} <= names
    assert {n.split("/")[0] for n in names} == {"Dockerfile.vercel", ".vercelignore", "requirements-api.lock",
                                                "LICENSE", "api", "src"}
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)


@pytest.mark.parametrize("path", [
    "notes/UPGRADE_NOTES.md", "CLAUDE.md", ".env", ".env.production", "data/raw/ddinter/a.csv",
    "data/profiles/public/processed/interactions.parquet", "data/profiles/research/processed/x.parquet",
    "review/fda_brand_review.csv", "processed/twosides_signals.parquet", ".venv/bin/python",
    "src/__pycache__/x.pyc", ".pytest_cache/v/cache", "tests/test_api.py", "results/trajectory.json",
    ".claude/skills/x/SKILL.md", ".git/config", "src/.DS_Store",
])
def test_guard_refuses_forbidden_paths(path):
    with pytest.raises(dv.Refused):
        dv.vercel_guard([dv.Upload(path, content=b"x")])


def test_guard_allows_the_code_under_src_data():
    dv.vercel_guard([dv.Upload("src/data/attribution.py", content=b"x")])     # 'data' only forbidden at the root


def test_vercelignore_must_match_the_stage(monkeypatch):
    ups = dv.planned() + [dv.Upload("scripts/deploy_space.py", content=b"x")]
    with pytest.raises(dv.Refused):
        dv.check_vercelignore(ups)


def test_dockerfile_vercel_keeps_the_tested_image():
    """Same base digest, hashed lock, non-root user and proxy-header handling as ./Dockerfile; listens on $PORT."""
    base = (ROOT / "Dockerfile").read_text()
    vc = (ROOT / "Dockerfile.vercel").read_text()
    digest = re.search(r"^FROM (\S+)", base, re.M).group(1)
    assert re.search(r"^FROM (\S+)", vc, re.M).group(1) == digest and "@sha256:" in digest
    assert "pip install --require-hashes --no-deps -r requirements-api.lock" in vc
    assert "USER pharmguard" in vc and "--uid 1000" in vc
    assert '--port \\"${PORT:-8080}\\"' in vc and "PORT=8080" in vc
    assert "--no-proxy-headers" in vc and "PHARMGUARD_REQUIRED_PROFILE=public" in vc
    assert "PHARMGUARD_DATA_DIR=/tmp/" in vc          # writable even if the root filesystem isn't
    for line in ("COPY requirements-api.lock .", "COPY --chown=pharmguard:pharmguard src/ ./src/",
                 "COPY --chown=pharmguard:pharmguard api/ ./api/"):
        assert line in base and line in vc
