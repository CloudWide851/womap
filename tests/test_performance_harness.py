from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from scripts.perf.capture_postgis_plans import parse_bbox
from scripts.perf.compare_reports import compare_api_reports
from scripts.perf.generate_ci_data import generate_ci_dataset
from scripts.perf.generate_workstation_data import PERF_ROOT, require_managed_output
from scripts.perf.reporting import build_report, read_report, redact_report, write_report
from scripts.perf.run_api_benchmark import benchmark_endpoint, parse_endpoint


class DelayedHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        time.sleep(0.03)
        body = b'{"status":"delayed"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_arguments: object) -> None:
        return


def test_ci_generator_is_deterministic_and_reported(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_manifest = generate_ci_dataset(
        first,
        feature_count=16,
        raster_width=64,
        raster_height=64,
    )
    second_manifest = generate_ci_dataset(
        second,
        feature_count=16,
        raster_width=64,
        raster_height=64,
    )

    assert (first / "vectors.geojson").read_bytes() == (second / "vectors.geojson").read_bytes()
    assert (first / "raster.tif").read_bytes() == (second / "raster.tif").read_bytes()
    assert first_manifest["workload"] == second_manifest["workload"]
    assert first_manifest["metrics"] == second_manifest["metrics"]
    assert read_report(first / "manifest.json")["kind"] == "dataset-manifest"


def test_http_harness_observes_a_deliberately_delayed_endpoint() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), DelayedHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        metric = benchmark_endpoint(
            f"http://127.0.0.1:{server.server_port}/delayed",
            samples=8,
            warmups=1,
            concurrency=2,
            timeout_seconds=2,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert metric["failed_requests"] == 0
    assert metric["p50_ms"] >= 25
    assert metric["p95_ms"] >= metric["p50_ms"]


def test_report_comparison_flags_the_delayed_candidate() -> None:
    baseline = build_report(
        kind="api-benchmark",
        profile="ci-small",
        dataset_tier="ci-small",
        workload={},
        metrics={"endpoints": {"live": {"p95_ms": 5, "throughput_rps": 100}}},
    )
    candidate = build_report(
        kind="api-benchmark",
        profile="ci-small",
        dataset_tier="ci-small",
        workload={},
        metrics={"endpoints": {"live": {"p95_ms": 30, "throughput_rps": 20}}},
    )

    comparison = compare_api_reports(
        baseline,
        candidate,
        max_latency_regression_percent=5,
    )

    assert comparison["passed"] is False
    assert comparison["comparisons"][0]["p95_change_percent"] == 500


def test_report_comparison_rejects_fast_failures_and_endpoint_mismatch() -> None:
    baseline = build_report(
        kind="api-benchmark",
        profile="ci-small",
        dataset_tier="ci-small",
        workload={},
        metrics={
            "endpoints": {
                "live": {"p95_ms": 10, "throughput_rps": 100, "failed_requests": 0}
            }
        },
    )
    failed_candidate = build_report(
        kind="api-benchmark",
        profile="ci-small",
        dataset_tier="ci-small",
        workload={},
        metrics={
            "endpoints": {
                "live": {"p95_ms": 1, "throughput_rps": 1000, "failed_requests": 8}
            }
        },
    )

    comparison = compare_api_reports(
        baseline,
        failed_candidate,
        max_latency_regression_percent=5,
    )

    assert comparison["passed"] is False
    assert comparison["comparisons"][0]["candidate_failed_requests"] == 8

    mismatched = build_report(
        kind="api-benchmark",
        profile="ci-small",
        dataset_tier="ci-small",
        workload={},
        metrics={"endpoints": {"ready": {"p95_ms": 1, "throughput_rps": 1000}}},
    )
    with pytest.raises(ValueError, match="same endpoint"):
        compare_api_reports(baseline, mismatched, max_latency_regression_percent=5)


def test_report_writer_redacts_sensitive_keys_and_absolute_paths(tmp_path: Path) -> None:
    report = build_report(
        kind="redaction-test",
        profile="ci-small",
        dataset_tier="ci-small",
        workload={"password": "should-not-appear", "safe": "ok"},
        metrics={"source": r"C:\Users\private-user\fixture.tif"},
    )
    output = tmp_path / "report.json"
    write_report(output, report)
    text = output.read_text(encoding="utf-8")

    assert "should-not-appear" not in text
    assert "private-user" not in text
    assert json.loads(text)["workload"]["password"] == "[redacted]"


def test_benchmark_input_rejects_sensitive_query_names() -> None:
    assert parse_endpoint("live=/health/live") == ("live", "/health/live")
    with pytest.raises(Exception):
        parse_endpoint("session=/api/v1/layers?token=secret")
    with pytest.raises(Exception):
        parse_endpoint("session=/api/v1/layers?access_token=secret")
    with pytest.raises(Exception):
        parse_endpoint("session=/api/v1/layers?sessionId=secret")


def test_postgis_bbox_and_workstation_output_guards(tmp_path: Path) -> None:
    assert parse_bbox("0,1,2,3") == (0.0, 1.0, 2.0, 3.0)
    with pytest.raises(Exception):
        parse_bbox("2,1,0,3")
    assert require_managed_output(PERF_ROOT / "workstation-medium").name == "workstation-medium"
    with pytest.raises(ValueError):
        require_managed_output(tmp_path / "outside")


def test_redaction_keeps_non_sensitive_version_strings() -> None:
    assert redact_report({"version": "PostgreSQL 17.5"}) == {"version": "PostgreSQL 17.5"}


def test_redaction_keeps_safe_endpoint_names_but_removes_credentials() -> None:
    report = redact_report(
        {
            "endpoint": {"name": "auth-session", "path": "/api/v1/auth/session"},
            "diagnostic": "session support available",
            "command_output": "token=should-not-appear",
            "password": "should-not-appear",
        }
    )

    assert report["endpoint"] == {"name": "auth-session", "path": "/api/v1/auth/session"}
    assert report["diagnostic"] == "session support available"
    assert report["command_output"] == "[redacted]"
    assert report["password"] == "[redacted]"
