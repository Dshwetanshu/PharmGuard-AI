"""scripts/deploy_cloudrun.py: settings match the app, and the image guard refuses forbidden files (no cloud calls)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("deploy_cloudrun", ROOT / "scripts" / "deploy_cloudrun.py")
dc = importlib.util.module_from_spec(spec)
sys.modules["deploy_cloudrun"] = dc
spec.loader.exec_module(dc)

GOOD = ["requirements-api.lock", "api/app.py", "api/static/index.html", "src/graph/builder.py"]


def test_settings_match_the_plan_and_the_app():
    from api.settings import ApiSettings
    s = dc.SETTINGS
    assert s["concurrency"] == str(ApiSettings.from_env({}).max_concurrency) == "4"
    assert (s["cpu"], s["memory"], s["min-instances"], s["max-instances"], s["port"]) == ("1", "1Gi", "0", "1", "7860")
    assert dc.REGION.startswith("us-east") and dc.APIS == ["run.googleapis.com", "artifactregistry.googleapis.com"]
    assert dc.cleanup_policy()[0]["mostRecentVersions"]["keepCount"] == 1


def test_deploy_command_is_public_request_billed_and_pinned_by_digest():
    env = {"PHARMGUARD_HF_DATASET": "u/d", "PHARMGUARD_HF_REVISION": "a" * 40,
           "PHARMGUARD_HF_PROVENANCE_SHA256": "b" * 64, "PHARMGUARD_TRUSTED_PROXY_HOPS": "1"}
    args = dc.deploy_args("p", "us-east1-docker.pkg.dev/p/pharmguard/api@sha256:" + "c" * 64, env)
    for flag in ("--allow-unauthenticated", "--cpu-throttling", "--min-instances=0", "--max-instances=1",
                 "--concurrency=4", "--port=7860", "--memory=1Gi", "--cpu=1", "--region=us-east1"):
        assert flag in args, flag
    assert any(a.startswith("--image=") and "@sha256:" in a for a in args)
    assert "--set-env-vars=" + ",".join(f"{k}={v}" for k, v in env.items()) in args
    assert "--no-cpu-throttling" not in args


def test_image_guard_accepts_the_app_files():
    dc.image_guard(GOOD)


@pytest.mark.parametrize("extra", ["notes/UPGRADE_NOTES.md", "CLAUDE.md", ".env", "data/raw/x.csv",
                                   "data/profiles/research/processed/x.parquet", "processed/twosides.parquet",
                                   "src/__pycache__/x.pyc", "review/fda_brand_review.csv", ".claude/x",
                                   "tests/test_api.py"])
def test_image_guard_refuses_forbidden_or_unexpected_files(extra):
    with pytest.raises(dc.Refused):
        dc.image_guard(GOOD + [extra])


def _fake_cloud(monkeypatch, live_digest, health, percent=100):
    import io
    import json as _json
    svc = {"status": {"url": "https://x.run.app", "latestReadyRevisionName": "pharmguard-00001",
                      "traffic": [{"revisionName": "pharmguard-00001", "percent": percent}]}}
    rev = {"status": {"imageDigest": "us-east1-docker.pkg.dev/p/pharmguard/api@" + live_digest}}
    monkeypatch.setattr(dc, "run", lambda cmd, quiet=False: _json.dumps(svc if cmd[2] == "services" else rev))

    class Resp(io.StringIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(dc.urllib.request, "urlopen", lambda url, timeout=0: Resp(_json.dumps(health)))


GOOD_HEALTH = {"status": "ok", "data_loaded": True, "profile": "public", "required_profile": "public",
               "provenance_sha256": "f" * 64, "attribution": [], "disclaimer": "d"}
DIGEST = "sha256:" + "a" * 64


def test_verify_live_passes_on_the_pushed_digest_and_our_health(monkeypatch):
    _fake_cloud(monkeypatch, DIGEST, GOOD_HEALTH)
    assert dc.verify_live("p", DIGEST, "f" * 64) == "https://x.run.app"


@pytest.mark.parametrize("live, health, percent", [
    ("sha256:" + "b" * 64, GOOD_HEALTH, 100),                                  # a different image is live
    (DIGEST, GOOD_HEALTH, 0),                                                  # the new revision gets no traffic
    (DIGEST, {**GOOD_HEALTH, "provenance_sha256": "e" * 64}, 100),             # another build is loaded
    (DIGEST, {**GOOD_HEALTH, "data_loaded": False, "status": "unavailable"}, 100),
    (DIGEST, {"status": "ok"}, 100),                                           # not our app's response
], ids=["digest", "traffic", "provenance", "no-data", "not-our-app"])
def test_verify_live_fails_loudly(monkeypatch, live, health, percent):
    _fake_cloud(monkeypatch, live, health, percent)
    with pytest.raises(SystemExit):
        dc.verify_live("p", DIGEST, "f" * 64)


@pytest.mark.parametrize("listing, exists", [
    ("pharmguard", True),                                                     # what gcloud prints
    ("projects/p/locations/us-east1/repositories/pharmguard", True),
    ("other\npharmguard-old", False), ("", False),
])
def test_repo_exists_matches_the_bare_or_full_name(listing, exists):
    assert dc.repo_exists(listing) is exists
