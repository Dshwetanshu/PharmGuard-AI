"""Client IP for rate limiting behind Google's front end, directly and through Firebase Hosting.

Shapes measured live on 28 September 2026 (docs/DEPLOYMENT.md): directly, Google appends the caller's
address to X-Forwarded-For (anything the caller sent stays in front); through Hosting, Hosting drops
the caller's X-Forwarded-For and writes "client, <CDN address>", and the CDN address is Google-operated.
Rule: if the rightmost entry is in the pinned Google-operated list, key on the entry just before it;
otherwise key on the rightmost. A stale list fails safe: it is ignored.
"""
from __future__ import annotations

import datetime
import json

import pytest

from api import ratelimit
from api.ratelimit import client_ip, load_trusted_networks, proxy_summary

_FETCHED = datetime.date.fromisoformat(
    json.loads((ratelimit.TRUSTED_RANGES_DIR / "google.json").read_text())["fetched"])
GOOGLE = load_trusted_networks("google", today=_FETCHED)
_first = json.loads((ratelimit.TRUSTED_RANGES_DIR / "google.json").read_text())["networks"][0]
import ipaddress  # noqa: E402
CDN = str(next(ipaddress.ip_network(_first).hosts()))          # a Google-operated address from the list
CLIENT, ATTACKER, FORGED = "198.51.100.7", "192.0.2.44", "203.0.113.9"


@pytest.mark.parametrize("headers, expected", [
    ({"x-forwarded-for": CLIENT}, CLIENT),                                          # direct
    ({"x-forwarded-for": f"{FORGED}, {ATTACKER}"}, ATTACKER),                       # direct, forged entry in front
    ({"x-forwarded-for": f"{FORGED}, {CDN}, {ATTACKER}"}, ATTACKER),                # direct, forged "CDN" hop
    ({"x-forwarded-for": f"{CLIENT}, {CDN}", "fastly-client-ip": FORGED}, CLIENT),  # through Hosting
    ({"x-forwarded-for": f"{FORGED}, {CDN}, {CDN}"}, CDN),                          # only one step, never two
    ({"x-forwarded-for": CDN}, CDN),                                                 # nothing before the hop
])
def test_rightmost_or_the_entry_before_a_google_hop(headers, expected):
    assert client_ip(headers, "10.0.0.1", 1, GOOGLE) == expected


def test_forged_fastly_header_is_never_the_key():
    h = {"x-forwarded-for": ATTACKER, "fastly-client-ip": FORGED}
    assert client_ip(h, "10.0.0.1", 1, GOOGLE) == ATTACKER


def test_a_stale_list_fails_safe_to_the_rightmost_entry(tmp_path, monkeypatch):
    doc = json.loads((ratelimit.TRUSTED_RANGES_DIR / "google.json").read_text())
    doc["fetched"] = (_FETCHED - datetime.timedelta(days=ratelimit.MAX_RANGE_AGE_DAYS + 1)).isoformat()
    (tmp_path / "google.json").write_text(json.dumps(doc))
    monkeypatch.setattr(ratelimit, "TRUSTED_RANGES_DIR", tmp_path)
    stale = load_trusted_networks("google")
    assert stale == ()
    assert client_ip({"x-forwarded-for": f"{CLIENT}, {CDN}"}, "10.0.0.1", 1, stale) == CDN


def test_ranges_are_off_by_default_and_only_google_is_known():
    assert load_trusted_networks("") == ()
    for name in ("fastly", "../etc", "cloud"):
        with pytest.raises(ValueError):
            load_trusted_networks(name)
    assert len(GOOGLE) > 100 and not any(ipaddress.ip_address(CLIENT) in n for n in GOOGLE)


def test_proxy_summary_reports_the_google_hop_as_yes_no_only():
    out = proxy_summary({"x-forwarded-for": f"{CLIENT}, {CDN}"}, "10.0.0.1", 1, GOOGLE)
    assert out["rightmost_hop_in_google_list"] is True and out["trusted_proxy_entries_skipped"] == 1
    direct = proxy_summary({"x-forwarded-for": CLIENT}, "10.0.0.1", 1, ())
    assert direct["rightmost_hop_in_google_list"] is False and direct["trusted_proxy_entries_skipped"] == 0
    assert CLIENT not in json.dumps(out) and CDN not in json.dumps(out)


def test_health_says_whether_the_pinned_list_is_stale(tmp_path, monkeypatch):
    fresh = proxy_summary({"x-forwarded-for": CLIENT}, "10.0.0.1", 1, GOOGLE)
    assert fresh["proxy_list_stale"] is False
    fetched = _FETCHED
    limit = datetime.timedelta(days=ratelimit.MAX_RANGE_AGE_DAYS)
    assert ratelimit.proxy_list_stale("google", today=fetched + limit) is False          # day 30: still used
    assert ratelimit.proxy_list_stale("google", today=fetched + limit + datetime.timedelta(days=1)) is True
    doc = json.loads((ratelimit.TRUSTED_RANGES_DIR / "google.json").read_text())
    doc["fetched"] = (_FETCHED - datetime.timedelta(days=ratelimit.MAX_RANGE_AGE_DAYS + 1)).isoformat()
    (tmp_path / "google.json").write_text(json.dumps(doc))
    monkeypatch.setattr(ratelimit, "TRUSTED_RANGES_DIR", tmp_path)
    ratelimit._GOOGLE_DIAG.clear()
    try:
        assert ratelimit.proxy_list_stale("google") is True
        stale = proxy_summary({"x-forwarded-for": f"{CLIENT}, {CDN}"}, "10.0.0.1", 1, load_trusted_networks("google"))
        assert stale["proxy_list_stale"] is True and stale["trusted_proxy_entries_skipped"] == 0
    finally:
        ratelimit._GOOGLE_DIAG.clear()
