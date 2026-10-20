"""Bounded local non-AI HTTP benchmark; only login/logout write temporary sessions."""

import argparse
import http.cookiejar
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]


def local_origin(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Only an explicit loopback application origin is supported")
    return value.rstrip("/")


def metrics(samples):
    durations = sorted(s["ms"] for s in samples)
    if not durations or any(not math.isfinite(v) or v < 0 for v in durations):
        raise ValueError("valid nonempty timings required")
    return {"requests": len(samples), "errors": sum(not s["ok"] for s in samples),
            "mean_ms": round(mean(durations), 3), "p50_ms": round(durations[math.ceil(len(durations) * .5) - 1], 3),
            "p95_ms": round(durations[math.ceil(len(durations) * .95) - 1], 3), "max_ms": round(max(durations), 3)}


def benchmark(base, password, concurrency=10, per_endpoint=30):
    base = local_origin(base)
    if not 1 <= concurrency <= 20 or not 1 <= per_endpoint <= 100:
        raise ValueError("concurrency 1..20 and per-endpoint requests 1..100 required")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def authenticated(path, payload=None, token=None):
        headers = {"Origin": base, "Content-Type": "application/json"}
        if token:
            headers["X-CSRF-Token"] = token
        req = urllib.request.Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                                     headers=headers)
        with opener.open(req, timeout=10) as response:
            raw = response.read()
            return json.loads(raw) if raw else None

    login = authenticated("/api/v1/auth/login", {"username": "student01", "password": password})
    try:
        if authenticated("/api/v1/auth/me")["user"]["role"] != "student":
            raise ValueError("Benchmark requires the existing student01 test account")
        courses = authenticated("/api/v1/courses")["items"]
        if not courses:
            raise ValueError("A course membership is required")
        course = urllib.parse.quote(courses[0]["id"], safe="")
        prefix = f"/api/v1/courses/{course}"
        paths = {"health": "/health", "outline": prefix + "/outline", "profile": prefix + "/profile",
                 "events": prefix + "/learning-events?limit=20", "snapshots": prefix + "/profile/snapshots",
                 "recommendations": prefix + "/recommendations"}
        cookie = "; ".join(f"{c.name}={c.value}" for c in jar)

        def measure(item):
            label, path = item
            start = time.perf_counter()
            ok = False
            try:
                req = urllib.request.Request(base + path, headers={"Cookie": cookie})
                with urllib.request.urlopen(req, timeout=10) as response:
                    json.loads(response.read())
                    ok = response.status == 200
            except (OSError, ValueError):
                pass
            return label, {"ok": ok, "ms": (time.perf_counter() - start) * 1000}

        # Warm up once per endpoint. Never send AI, export, feedback or grading requests.
        for item in paths.items():
            if not measure(item)[1]["ok"]:
                raise ValueError("Read API warmup failed; no benchmark acceptance reported")
        tasks = list(paths.items()) * per_endpoint
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(measure, tasks))
        elapsed = time.perf_counter() - start
        summaries = {label: metrics([r for key, r in results if key == label]) for label in paths}
        return {"version": "read-http-benchmark-v1", "concurrency": concurrency,
                "requests_per_endpoint": per_endpoint, "total_requests": len(results),
                "wall_seconds": round(elapsed, 6), "requests_per_second": round(len(results) / elapsed, 3),
                "endpoints": summaries, "p95_target_ms": 1000,
                "meets_target": all(m["errors"] == 0 and m["p95_ms"] < 1000 for m in summaries.values()),
                "errors": sum(m["errors"] for m in summaries.values()),
                "limitations": "Warm local HTTP measurements on current data only; not production load, cold start, AI latency, browser timing or a representative large-course claim. No answers or credentials stored."}
    finally:
        authenticated("/api/v1/auth/logout", {}, login["csrf_token"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--per-endpoint", type=int, default=30)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/ci/read-api-benchmark.json")
    parser.add_argument("--enforce-latency", action="store_true")
    args = parser.parse_args()
    password = os.environ.get("BENCHMARK_PASSWORD", "")
    if not password:
        parser.error("Set BENCHMARK_PASSWORD in the process environment; never pass it as a command argument")
    try:
        report = benchmark(args.base_url, password, args.concurrency, args.per_endpoint)
    except (OSError, ValueError, KeyError):
        raise SystemExit("Read benchmark failed. Check local service, account and schema; request contents suppressed.") from None
    report["latency_enforced"] = args.enforce_latency
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"requests": report["total_requests"], "errors": report["errors"], "meets_p95_target": report["meets_target"]}))
    raise SystemExit(1 if report["errors"] or (args.enforce_latency and not report["meets_target"]) else 0)


if __name__ == "__main__":
    main()
