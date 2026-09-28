"""scripts/update_proxy_ranges.py: goog.json minus cloud.json, and the refresh the deploy runs first."""
from __future__ import annotations

import datetime
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("update_proxy_ranges", ROOT / "scripts" / "update_proxy_ranges.py")
upr = importlib.util.module_from_spec(spec)
sys.modules["update_proxy_ranges"] = upr
spec.loader.exec_module(upr)

GOOG = {"syncToken": "1", "creationTime": "t", "prefixes": [{"ipv4Prefix": "8.8.0.0/16"}, {"ipv4Prefix": "34.0.0.0/15"},
                                                             {"ipv6Prefix": "2001:4860::/32"}]}
CLOUD = {"syncToken": "1", "creationTime": "t", "prefixes": [{"ipv4Prefix": "34.0.0.0/15"}, {"ipv4Prefix": "8.8.8.0/24"}]}


def _fake(monkeypatch, goog=GOOG, cloud=CLOUD):
    monkeypatch.setattr(upr, "fetch", lambda url: goog if url == upr.GOOG else cloud)


def test_google_operated_is_goog_minus_cloud(monkeypatch):
    _fake(monkeypatch)
    nets = upr.build()["networks"]
    assert "34.0.0.0/15" not in nets and not any(n.startswith("8.8.8.") for n in nets)
    assert "8.8.9.0/24" in nets or "8.8.16.0/20" in nets          # the rest of 8.8.0.0/16 remains
    assert "2001:4860::/32" in nets


def test_refresh_reports_changes_and_renews_the_date(tmp_path, monkeypatch):
    pinned = tmp_path / "google.json"
    pinned.write_text(json.dumps({"fetched": "2000-01-01", "networks": ["8.8.0.0/16"]}))
    monkeypatch.setattr(upr, "PINNED", pinned)
    _fake(monkeypatch)
    changes = upr.refresh()
    doc = json.loads(pinned.read_text())
    assert doc["fetched"] == datetime.date.today().isoformat()
    assert any("added" in c for c in changes) and any("removed" in c for c in changes)
    assert upr.refresh() == []                                   # a second refresh: nothing changed
