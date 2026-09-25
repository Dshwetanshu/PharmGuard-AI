"""scripts/fetch_data.py: pinned hashes are enforced; the manifest records what was fetched (no network)."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest

from src.data import sources
from src.data.sources import Source, SourceFile

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("fetch_data", ROOT / "scripts" / "fetch_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def fake_source(monkeypatch):
    body = b"DDInterID_A,Drug_A,DDInterID_B,Drug_B,Level\n"
    good = hashlib.sha256(body).hexdigest()
    mod = _load()
    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda req, timeout=None: _Resp(body))

    def install(sha):
        src = Source("fx", "Fixture", "v1", "CC0", "https://example.invalid",
                     [SourceFile("https://example.invalid/fx.csv", "fx.csv", sha256=sha)])
        monkeypatch.setitem(mod.SOURCES, "fx", src)
        return mod
    install.body = body
    return install, good


def test_first_download_records_manifest(tmp_path, fake_source):
    install, good = fake_source
    mod = install(None)
    m = mod.fetch(tmp_path, ["fx"])
    entry = m["fx"]["files"][0]
    assert (entry["sha256"], entry["sha256_pinned"], entry["bytes"]) == (good, False, len(install.body))
    assert json.loads((tmp_path / "MANIFEST.json").read_text())["fx"]["license"] == "CC0"


def test_pinned_hash_mismatch_is_rejected(tmp_path, fake_source):
    install, _ = fake_source
    mod = install("0" * 64)
    with pytest.raises(SystemExit, match="sha256 mismatch"):
        mod.fetch(tmp_path, ["fx"])


def test_twosides_is_research_only_and_every_public_file_is_pinned():
    assert [s.key for s in sources.sources_for("public")] == ["rxnorm", "drugbank", "ddinter", "sider", "drugsatfda"]
    assert "twosides" in [s.key for s in sources.sources_for("research")]
    for s in sources.SOURCES.values():
        assert all(f.sha256 and len(f.sha256) == 64 for f in s.files), s.key
