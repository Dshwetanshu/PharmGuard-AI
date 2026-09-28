"""Per-client sliding-window rate limiting and client IP resolution (framework-free)."""
from __future__ import annotations

import datetime
import ipaddress
import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Callable, Deque, Dict, List, Mapping, Optional, Tuple, Union


TRUSTED_RANGES_DIR = Path(__file__).resolve().parent / "trusted_proxies"
KNOWN_RANGES = ("google",)
MAX_RANGE_AGE_DAYS = 30          # an older pinned list is ignored (fail safe: key on the rightmost entry)
Networks = Tuple[Union[ipaddress.IPv4Network, ipaddress.IPv6Network], ...]


def load_trusted_networks(name: str, today: Optional[datetime.date] = None) -> Networks:
    """Pinned proxy ranges by name ("" = none). "google": Google-operated ranges (goog.json minus
    cloud.json, api/trusted_proxies/google.json, built by scripts/update_proxy_ranges.py), where
    Firebase Hosting's CDN connects from. A list older than MAX_RANGE_AGE_DAYS loads as empty."""
    if not name:
        return ()
    if name not in KNOWN_RANGES:
        raise ValueError(f"unknown trusted proxy ranges {name!r}")
    doc = json.loads((TRUSTED_RANGES_DIR / f"{name}.json").read_text())
    age = ((today or datetime.date.today()) - datetime.date.fromisoformat(doc["fetched"])).days
    if age > MAX_RANGE_AGE_DAYS:
        return ()
    return tuple(ipaddress.ip_network(n) for n in doc["networks"])


def _in(addr: str, networks: Networks) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in n for n in networks)


def _key_index(parts: List[str], trusted_proxy_hops: int, trusted_networks: Networks) -> Optional[int]:
    if trusted_proxy_hops <= 0 or len(parts) < trusted_proxy_hops:
        return None
    i = len(parts) - trusted_proxy_hops
    # Firebase Hosting drops the caller's X-Forwarded-For and writes "client, <CDN>"; the CDN connects
    # from a Google-operated address. If that is the entry here, key on the one just before it (one
    # step only). Directly, this entry is the caller's own address and is used as is.
    if i > 0 and _in(parts[i], trusted_networks):
        i -= 1
    return i


def client_ip(headers: Mapping[str, str], peer: Optional[str], trusted_proxy_hops: int,
              trusted_networks: Networks = ()) -> str:
    """The client address. Behind N trusted proxies (Google's front end: N=1), the client is the
    N-th X-Forwarded-For entry from the right; entries further left were supplied by the client and
    can be forged. If that entry is in `trusted_networks` (Firebase Hosting's CDN), the entry just
    before it is used instead. With no trusted proxy, X-Forwarded-For is ignored."""
    parts = [p.strip() for p in (headers.get("x-forwarded-for") or "").split(",") if p.strip()]
    i = _key_index(parts, trusted_proxy_hops, trusted_networks)
    return parts[i] if i is not None else (peer or "unknown")


def proxy_summary(headers: Mapping[str, str], peer: Optional[str], trusted_proxy_hops: int,
                  trusted_networks: Networks = ()) -> dict:
    """Counts and names only, for checking the proxy set-up: how many X-Forwarded-For entries arrived,
    how many hops are trusted, whether the rate-limit key is the TCP peer (behind a proxy that means
    it is keying on the proxy), which client-address headers arrived, and where Fastly-Client-IP sits
    in X-Forwarded-For. No addresses are returned."""
    xff = headers.get("x-forwarded-for") or ""
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    fastly = (headers.get("fastly-client-ip") or "").strip()
    i = _key_index(parts, trusted_proxy_hops, trusted_networks)
    # Where Fastly-Client-IP (set by Firebase Hosting's CDN) sits in X-Forwarded-For, counted from the
    # right: a position, never the address.
    fastly_pos = next((len(parts) - i for i in range(len(parts) - 1, -1, -1) if parts[i] == fastly), None) \
        if fastly else None
    return {"forwarded_for_entries": len(parts), "trusted_proxy_hops": trusted_proxy_hops,
            "client_key_is_tcp_peer": client_ip(headers, peer, trusted_proxy_hops, trusted_networks) == (peer or "unknown"),
            "trusted_proxy_entries_skipped": (len(parts) - trusted_proxy_hops - i) if i is not None else 0,
            "client_key_is_fastly_client_ip": bool(fastly) and i is not None and parts[i] == fastly,
            "rightmost_hop_in_google_list": bool(parts) and _in(parts[-1], _google_for_diagnostics()),
            "client_ip_headers": sorted(h for h in CLIENT_IP_HEADERS if headers.get(h)),
            "fastly_client_ip_position_from_right": fastly_pos}


_GOOGLE_DIAG: list = []


def _google_for_diagnostics() -> Networks:
    """The pinned Google list, for the yes/no in /health even while it isn't used for keys."""
    if not _GOOGLE_DIAG:
        _GOOGLE_DIAG.append(load_trusted_networks("google"))
    return _GOOGLE_DIAG[0]


# Header names that proxies use for the client address; /health reports which ones arrived (names only).
CLIENT_IP_HEADERS = ("x-forwarded-for", "fastly-client-ip", "x-real-ip", "forwarded", "true-client-ip",
                     "x-client-ip", "x-appengine-user-ip", "x-forwarded-host")


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic,
                 max_keys: int = 10_000):
        self.limit, self.window_s, self.clock, self.max_keys = limit, window_s, clock, max_keys
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> Tuple[bool, float]:
        """(allowed, retry_after_seconds). An allowed call is counted."""
        now = self.clock()
        with self._lock:
            if len(self._hits) > self.max_keys:          # bound memory: drop idle clients
                for k in [k for k, q in self._hits.items() if not q or q[-1] <= now - self.window_s]:
                    del self._hits[k]
            q = self._hits[key]
            while q and q[0] <= now - self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return False, round(q[0] + self.window_s - now, 1)
            q.append(now)
            return True, 0.0
