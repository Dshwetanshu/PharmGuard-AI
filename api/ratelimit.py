"""Per-client sliding-window rate limiting and client IP resolution (framework-free)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Mapping, Optional, Tuple


def client_ip(headers: Mapping[str, str], peer: Optional[str], trusted_proxy_hops: int) -> str:
    """The client address. Behind N trusted proxies (the Spaces proxy: N=1), the client is
    the N-th X-Forwarded-For entry from the right: entries further left were supplied by
    the client and can be forged. With no trusted proxy, X-Forwarded-For is ignored."""
    if trusted_proxy_hops > 0:
        xff = headers.get("x-forwarded-for") or ""
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= trusted_proxy_hops:
            return parts[-trusted_proxy_hops]
    return peer or "unknown"


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
