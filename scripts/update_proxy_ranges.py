"""Build the Google-operated address list: Google's published goog.json minus cloud.json.

Usage:
    python scripts/update_proxy_ranges.py            # fetch both lists and rewrite the pinned copy
    python scripts/update_proxy_ranges.py --check    # compare the published lists with the pinned copy

goog.json lists every Google address range, including the ones Google Cloud customers use
(cloud.json). Subtracting cloud.json leaves ranges Google itself operates, where Firebase Hosting's
CDN connects from. api/ratelimit.py loads the pinned copy only when
PHARMGUARD_TRUSTED_PROXY_RANGES=google, to recognise Hosting's hop in X-Forwarded-For.
"""
from __future__ import annotations

import argparse
import datetime
import ipaddress
import json
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
PINNED = ROOT / "api" / "trusted_proxies" / "google.json"
GOOG = "https://www.gstatic.com/ipranges/goog.json"
CLOUD = "https://www.gstatic.com/ipranges/cloud.json"


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def prefixes(doc: dict) -> List[ipaddress._BaseNetwork]:
    return [ipaddress.ip_network(p.get("ipv4Prefix") or p.get("ipv6Prefix")) for p in doc["prefixes"]]


def subtract(keep: List[ipaddress._BaseNetwork], remove: List[ipaddress._BaseNetwork]) -> List[str]:
    """Every address in `keep` that isn't in `remove`, as collapsed networks."""
    out = []
    for net in keep:
        pieces = [net]
        for r in remove:
            if r.version != net.version:
                continue
            nxt = []
            for p in pieces:
                if p.subnet_of(r):
                    continue                      # wholly a customer range: drop it
                nxt.extend(p.address_exclude(r) if r.subnet_of(p) else [p])
            pieces = nxt
        out.extend(pieces)
    v4 = ipaddress.collapse_addresses(n for n in out if n.version == 4)
    v6 = ipaddress.collapse_addresses(n for n in out if n.version == 6)
    return [str(n) for n in list(v4) + list(v6)]


def build() -> Dict:
    goog, cloud = fetch(GOOG), fetch(CLOUD)
    return {"sources": {"goog": GOOG, "cloud": CLOUD},
            "source_versions": {"goog": {"syncToken": goog.get("syncToken"), "creationTime": goog.get("creationTime")},
                                "cloud": {"syncToken": cloud.get("syncToken"), "creationTime": cloud.get("creationTime")}},
            "fetched": datetime.date.today().isoformat(),
            "purpose": "Google-operated ranges (goog.json minus cloud.json): an X-Forwarded-For entry from these is "
                       "Firebase Hosting's CDN hop, not the client",
            "networks": subtract(prefixes(goog), prefixes(cloud))}


def diff(old: List[str], new: List[str]) -> List[str]:
    added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
    out = []
    if added:
        out.append(f"{len(added)} ranges added: " + ", ".join(added[:10]) + (" ..." if len(added) > 10 else ""))
    if removed:
        out.append(f"{len(removed)} ranges removed: " + ", ".join(removed[:10]) + (" ..." if len(removed) > 10 else ""))
    return out


def changed_since_pinned() -> List[str]:
    """Differences between the published lists and the pinned copy (empty when they agree)."""
    return diff(json.loads(PINNED.read_text())["networks"], build()["networks"])


def refresh() -> List[str]:
    """Fetch the published lists, rewrite the pinned copy with today's date, and return what changed.
    scripts/deploy_cloudrun.py runs this first, so every redeploy renews the list."""
    old = json.loads(PINNED.read_text())["networks"] if PINNED.exists() else []
    doc = build()
    PINNED.write_text(json.dumps(doc, indent=1) + "\n")
    return diff(old, doc["networks"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="compare only; don't rewrite the pinned copy")
    args = ap.parse_args()
    if args.check:
        diffs = changed_since_pinned()
        print("\n".join(diffs) if diffs else f"Pinned Google ranges match the published lists.")
        return 1 if diffs else 0
    doc = build()
    PINNED.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"Wrote {PINNED.relative_to(ROOT)}: {len(doc['networks'])} networks "
          f"(goog {doc['source_versions']['goog']['creationTime']}, cloud {doc['source_versions']['cloud']['creationTime']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
