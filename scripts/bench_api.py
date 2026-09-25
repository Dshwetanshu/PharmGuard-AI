"""End-to-end latency of a running PharmGuard API over the evaluation cases.

Usage (the server's rate limit must allow the burst, e.g. PHARMGUARD_RATE_LIMIT=1000/60):
    python scripts/bench_api.py --url http://127.0.0.1:7860 --rounds 5

Client-side wall time per POST /v1/check (deterministic mode), after one warm-up
request. Cases the API rejects by design (fewer than 2 drugs) are listed, not timed.
Standard library only, so it can run anywhere.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evaluation.test_cases import TEST_CASES  # noqa: E402


def post(url: str, drugs) -> tuple:
    req = urllib.request.Request(url + "/v1/check", data=json.dumps({"drugs": drugs, "mode": "deterministic"}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read())
            status = r.status
    except urllib.error.HTTPError as e:
        body, status = json.loads(e.read() or b"{}"), e.code
    return status, (time.perf_counter() - t) * 1000, body


def pct(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:7860")
    ap.add_argument("--rounds", type=int, default=5)
    args = ap.parse_args()
    post(args.url, ["warfarin", "aspirin"])                      # warm-up
    times, server, rejected, failed = [], [], {}, []
    for _ in range(args.rounds):
        for c in TEST_CASES:
            status, ms, body = post(args.url, c.input_drugs)
            if status == 200:
                times.append(ms)
                server.append(body["timings_ms"]["total"])
                if not body["validation"]["passed"]:
                    failed.append(c.case_id)
            else:
                rejected[c.case_id] = f"{status} {body.get('error', {}).get('code')}"
    print(f"timed requests: {len(times)} ({len(times) // args.rounds} cases x {args.rounds} rounds)")
    print(f"end-to-end ms: p50 {statistics.median(times):.1f}  p95 {pct(times, 0.95):.1f}  max {max(times):.1f}")
    print(f"server-side ms (timings_ms.total): p50 {statistics.median(server):.1f}  p95 {pct(server, 0.95):.1f}")
    print(f"rejected by design: {rejected or 'none'}")
    print(f"reports failing validation: {sorted(set(failed)) or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
