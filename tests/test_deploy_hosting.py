"""scripts/deploy_hosting.py: Hosting serves nothing itself and rewrites every path to the service."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("deploy_hosting", ROOT / "scripts" / "deploy_hosting.py")
dh = importlib.util.module_from_spec(spec)
sys.modules["deploy_hosting"] = dh
spec.loader.exec_module(dh)


def _copy(tmp_path):
    shutil.copy(ROOT / "firebase.json", tmp_path / "firebase.json")
    (tmp_path / "hosting" / "public").mkdir(parents=True)
    (tmp_path / "hosting" / "public" / ".gitkeep").write_text("")
    return tmp_path


def test_repo_config_passes():
    cfg = dh.check_config()
    assert cfg["rewrites"] == [{"source": "**", "run": {"serviceId": "pharmguard", "region": "us-east1"}}]


def test_refuses_any_file_hosting_would_serve(tmp_path):
    root = _copy(tmp_path)
    (root / "hosting" / "public" / "index.html").write_text("<p>stale copy</p>")
    with pytest.raises(dh.Refused):
        dh.check_config(root)


@pytest.mark.parametrize("change", [
    {"rewrites": [{"source": "/api/**", "run": {"serviceId": "pharmguard", "region": "us-east1"}}]},
    {"rewrites": [{"source": "**", "run": {"serviceId": "other", "region": "us-east1"}}]},
    {"site": "somewhere-else"},
    {"ignore": []},
])
def test_refuses_a_changed_rewrite_site_or_ignore(tmp_path, change):
    root = _copy(tmp_path)
    cfg = json.loads((root / "firebase.json").read_text())
    cfg["hosting"].update(change)
    (root / "firebase.json").write_text(json.dumps(cfg))
    with pytest.raises(dh.Refused):
        dh.check_config(root)
