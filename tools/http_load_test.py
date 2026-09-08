"""Read-only real HTTP load probe. A finite sample is not an availability SLA."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import UTC, datetime
import json
import os
import time
from urllib.parse import urlsplit

import httpx


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


async def measure(client, url, *, concurrency=100, requests=100):
    if not 1 <= concurrency <= 1000 or not 1 <= requests <= 100000:
        raise ValueError("invalid concurrency or request count")
    started_at = datetime.now(UTC).isoformat()
    started = time.perf_counter()
    statuses, errors, elapsed, completed = Counter(), Counter(), [], []
    queue = asyncio.Queue()
    for i in range(requests):
        queue.put_nowait(i)

    async def worker():
        while not queue.empty():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            request_start = time.perf_counter()
            try:
                response = await client.get(url)
                latency = (time.perf_counter() - request_start) * 1000
                statuses[str(response.status_code)] += 1
                if 200 <= response.status_code < 300:
                    completed.append(latency)
                else:
                    errors[f"HTTP_{response.status_code}"] += 1
            except httpx.RequestError as exc:
                latency = (time.perf_counter() - request_start) * 1000
                errors[type(exc).__name__] += 1
            elapsed.append(latency)

    await asyncio.gather(*(worker() for _ in range(min(concurrency, requests))))
    duration = time.perf_counter() - started
    return {
        "transport": "HTTP_NETWORK", "started_at": started_at,
        "ended_at": datetime.now(UTC).isoformat(), "duration_seconds": round(duration, 3),
        "concurrency": concurrency, "requests": requests, "completed": len(completed),
        "failed": requests - len(completed), "status_counts": dict(statuses), "error_counts": dict(errors),
        "sample_success_pct": round(len(completed) * 100 / requests, 3),
        "latency_ms": {"p50": percentile(elapsed, .50), "p95": percentile(elapsed, .95), "p99": percentile(elapsed, .99)},
        "success_latency_p95_ms": percentile(completed, .95),
        "sla_verified": False,
        "boundary": "Finite read-only HTTP sample; provider/business coverage depends on the selected route. No long-term availability claim.",
    }


async def run(args):
    parsed = urlsplit(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("URL must be HTTP(S) without credentials, query or fragment")
    username, password = os.getenv("PRISM_LOAD_USERNAME"), os.getenv("PRISM_LOAD_PASSWORD")
    if bool(username) != bool(password):
        raise ValueError("both load-test authentication environment variables are required")
    headers = {"X-Owner-ID": args.owner} if args.owner else {}
    async with httpx.AsyncClient(
        timeout=args.timeout, trust_env=False, follow_redirects=False, headers=headers,
        auth=(username, password) if username else None,
        limits=httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency),
    ) as client:
        result = await measure(client, args.url, concurrency=args.concurrency, requests=args.requests)
    result["target"] = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["failed"] == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/health")
    parser.add_argument("--owner")
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    if not 0 < args.timeout <= 300:
        parser.error("timeout must be between 0 and 300 seconds")
    try:
        return asyncio.run(run(args))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
