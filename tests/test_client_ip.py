"""Client IP for rate limiting behind Google's front end, directly and through Firebase Hosting (Fastly).

Shapes measured live on 28 September 2026 (see docs/DEPLOYMENT.md): directly, Google appends the
client to X-Forwarded-For (anything the client sent stays in front); through Hosting, Hosting drops the
client's X-Forwarded-For, writes "client, <CDN address>", and overwrites Fastly-Client-IP.
"""
from __future__ import annotations

import ipaddress
import json

import pytest

from api.ratelimit import client_ip, load_trusted_networks, proxy_summary

FASTLY = load_trusted_networks("fastly")
CDN = str(next(ipaddress.ip_network("151.101.0.0/16").hosts()))      # a Fastly address (in the pinned list)
CLIENT, ATTACKER, FORGED = "198.51.100.7", "192.0.2.44", "203.0.113.9"


@pytest.mark.parametrize("headers, expected", [
    ({"x-forwarded-for": CLIENT}, CLIENT),                                           # direct
    ({"x-forwarded-for": f"{FORGED}, {ATTACKER}"}, ATTACKER),                        # direct, forged XFF
    ({"x-forwarded-for": f"{FORGED}, {CDN}, {ATTACKER}", "fastly-client-ip": FORGED}, ATTACKER),  # forged "via CDN"
    ({"x-forwarded-for": f"{CLIENT}, {CDN}", "fastly-client-ip": CLIENT}, CLIENT),   # through Hosting
    ({"x-forwarded-for": f"{CLIENT}, {CDN}"}, CLIENT),                               # Hosting, no Fastly header
    ({"x-forwarded-for": CDN}, CDN),                                                  # nothing left of the CDN hop
])
def test_client_key_is_the_first_untrusted_hop(headers, expected):
    assert client_ip(headers, "10.0.0.1", 1, FASTLY) == expected


def test_without_trusted_ranges_hosting_traffic_keys_on_the_cdn():
    assert client_ip({"x-forwarded-for": f"{CLIENT}, {CDN}"}, "10.0.0.1", 1) == CDN


def test_ranges_load_from_the_pinned_list_and_are_off_by_default():
    assert load_trusted_networks("") == () and len(FASTLY) >= 19
    with pytest.raises(ValueError):
        load_trusted_networks("somewhere")
    assert any(ipaddress.ip_address(CDN) in n for n in FASTLY)
    assert not any(ipaddress.ip_address(CLIENT) in n for n in FASTLY)


def test_proxy_summary_counts_skipped_trusted_hops_without_addresses():
    out = proxy_summary({"x-forwarded-for": f"{CLIENT}, {CDN}", "fastly-client-ip": CLIENT}, "10.0.0.1", 1, FASTLY)
    assert out["trusted_proxy_entries_skipped"] == 1 and out["client_key_is_fastly_client_ip"] is True
    assert CLIENT not in json.dumps(out) and CDN not in json.dumps(out)
