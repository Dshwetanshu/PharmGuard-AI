"""scripts/deploy_space.py refuses anything but the public build (no uploads in tests)."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("deploy_space", ROOT / "scripts" / "deploy_space.py")
deploy = importlib.util.module_from_spec(spec)
sys.modules["deploy_space"] = deploy          # dataclasses look the module up by name
spec.loader.exec_module(deploy)


@pytest.mark.parametrize("path", ["processed/twosides_signals.parquet", "data/profiles/research/processed/x.parquet",
                                  "notes/UPGRADE_NOTES.md", "CLAUDE.md", ".env", ".env.local",
                                  "data/raw/ddinter/a.csv", "src/__pycache__/x.pyc",
                                  "data/profiles/public/review/fda_brand_review.csv", "review/fda_brand_review.csv",
                                  ".claude/skills/redesign-skill/SKILL.md"])
def test_guard_refuses_forbidden_paths(path):
    with pytest.raises(deploy.Refused):
        deploy.guard([deploy.Upload(path, content=b"x")], "test")


def test_space_file_list_has_only_code_and_no_forbidden_paths():
    ups = deploy.space_uploads("u/pharmguard-public-build", "u/pharmguard")
    deploy.guard(ups, "Space")
    names = {u.path_in_repo for u in ups}
    assert {"Dockerfile", "requirements-api.lock", "LICENSE", "README.md", "api/app.py", "src/graph/builder.py"} <= names
    assert not any(n.startswith(("data/", "tests/", "notes/", "results/")) for n in names)
    readme = next(u for u in ups if u.path_in_repo == "README.md").content.decode()
    assert "sdk: docker" in readme and "app_port: 7860" in readme and "\nlicense: mit\n" in readme
    assert "https://u-pharmguard.hf.space/?drugs=warfarin,aspirin" in readme and "deterministic mode" in readme


def _fake_build(tmp_path, test_data_dir, **prov_updates):
    b = tmp_path / "processed"
    shutil.copytree(Path(test_data_dir) / "processed", b)
    prov = json.loads((b / "provenance.json").read_text())
    prov.update(prov_updates)
    (b / "provenance.json").write_text(json.dumps(prov))
    return b


@pytest.mark.parametrize("updates,message", [
    ({}, "not 'public'"),                                                    # the synthetic sample
    ({"profile": "research", "mode": "full"}, "not 'public'"),
    ({"profile": "public", "synthetic": False, "not_for_redistribution": True}, "not for redistribution"),
    ({"profile": "public", "synthetic": False, "source_order": ["rxnorm", "ddinter", "twosides"]}, "TWOSIDES"),
    ({"profile": "public", "synthetic": False}, "only DDInter"),             # sample has TWOSIDES-shaped rows
])
def test_check_build_refuses(tmp_path, test_data_dir, sample_ingest_report, updates, message):
    with pytest.raises(deploy.Refused, match=message):
        deploy.check_build(_fake_build(tmp_path, test_data_dir, **updates))


def test_app_url():
    assert deploy.app_url("Some_User/Pharm.Guard") == "https://some-user-pharm-guard.hf.space"
