from __future__ import annotations

import argparse
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urljoin, urlsplit
from urllib.request import Request, urlopen

if __package__ in {None, ""}:
    from _bootstrap import ensure_repo_root

    ensure_repo_root()

from scripts.perf.reporting import build_report, duration_summary, write_report


_SENSITIVE_QUERY_MARKERS = ("password", "secret", "token", "cookie", "session", "api_key", "apikey")


@dataclass(frozen=True)
class RequestSample:
    duration_seconds: float
    status_code: int
    response_bytes: int


def request_once(url: str, *, cookie: str | None, timeout_seconds: float) -> RequestSample:
    headers = {"Accept": "application/json", "User-Agent": "womap-performance-harness/1"}
    if cookie:
        headers["Cookie"] = cookie
    request = Request(url, headers=headers, method="GET")
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
            status_code = response.status
    except HTTPError as exc:
        body = exc.read()
        status_code = exc.code
    except (URLError, TimeoutError, OSError):
        return RequestSample(time.perf_counter() - started, 0, 0)
    return RequestSample(time.perf_counter() - started, status_code, len(body))


def benchmark_endpoint(
    url: str,
    *,
    samples: int,
    warmups: int,
    concurrency: int,
    timeout_seconds: float,
    cookie: str | None = None,
) -> dict[str, object]:
    for _ in range(warmups):
        request_once(url, cookie=cookie, timeout_seconds=timeout_seconds)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(
                request_once,
                url,
                cookie=cookie,
                timeout_seconds=timeout_seconds,
            )
            for _ in range(samples)
        ]
        results = [future.result() for future in as_completed(futures)]
    elapsed = time.perf_counter() - started
    summary = duration_summary((result.duration_seconds for result in results), elapsed)
    summary.update(
        {
            "status_counts": {
                str(status): sum(result.status_code == status for result in results)
                for status in sorted({result.status_code for result in results})
            },
            "response_bytes": sum(result.response_bytes for result in results),
            "failed_requests": sum(result.status_code == 0 or result.status_code >= 400 for result in results),
        }
    )
    return summary


def parse_endpoint(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("endpoint must use NAME=/relative/path")
    name, path = value.split("=", maxsplit=1)
    if not name.replace("-", "_").isalnum() or not path.startswith("/") or path.startswith("//"):
        raise argparse.ArgumentTypeError("endpoint name or path is invalid")
    if any(_is_sensitive_query_name(key) for key, _ in parse_qsl(urlsplit(path).query)):
        raise argparse.ArgumentTypeError("endpoint query contains a sensitive parameter name")
    return name, path


def _is_sensitive_query_name(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return normalized == "key" or any(
        normalized.startswith(marker) or normalized.endswith(marker)
        for marker in _SENSITIVE_QUERY_MARKERS
    )


def validated_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise argparse.ArgumentTypeError("base URL must be HTTP(S) without embedded credentials")
    return value.rstrip("/") + "/"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a redacted WOMAP HTTP latency benchmark.")
    parser.add_argument("--base-url", type=validated_base_url, default="http://127.0.0.1:8000/")
    parser.add_argument(
        "--endpoint",
        action="append",
        type=parse_endpoint,
        default=None,
        help="Repeatable NAME=/relative/path target; defaults to live and ready.",
    )
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--profile", choices=("ci-small", "workstation-medium"), default="ci-small")
    parser.add_argument("--cookie-env", default="WOMAP_BENCH_COOKIE")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".womap-data/perf/reports/api-benchmark.json"),
    )
    arguments = parser.parse_args()
    if not 1 <= arguments.samples <= 100000:
        parser.error("samples must be between 1 and 100000")
    if not 0 <= arguments.warmups <= 1000:
        parser.error("warmups must be between 0 and 1000")
    if not 1 <= arguments.concurrency <= 256:
        parser.error("concurrency must be between 1 and 256")
    if not 0.1 <= arguments.timeout_seconds <= 120:
        parser.error("timeout must be between 0.1 and 120 seconds")

    endpoints = arguments.endpoint or [("live", "/health/live"), ("ready", "/health/ready")]
    cookie = os.environ.get(arguments.cookie_env) if arguments.cookie_env else None
    metrics = {
        name: benchmark_endpoint(
            urljoin(arguments.base_url, path.lstrip("/")),
            samples=arguments.samples,
            warmups=arguments.warmups,
            concurrency=arguments.concurrency,
            timeout_seconds=arguments.timeout_seconds,
            cookie=cookie,
        )
        for name, path in endpoints
    }
    report = build_report(
        kind="api-benchmark",
        profile=arguments.profile,
        dataset_tier=arguments.profile,
        workload={
            "endpoints": [{"name": name, "path": path} for name, path in endpoints],
            "samples": arguments.samples,
            "warmups": arguments.warmups,
            "concurrency": arguments.concurrency,
            "warmup_requests_excluded_from_metrics": True,
            "cold_and_warm_separated": False,
        },
        metrics={"endpoints": metrics},
    )
    write_report(arguments.output, report)
    print(f"API benchmark completed: {len(endpoints)} endpoint(s), {arguments.samples} samples each.")
    return 1 if any(int(metric["failed_requests"]) > 0 for metric in metrics.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
