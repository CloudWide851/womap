from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    from _bootstrap import ensure_repo_root

    ensure_repo_root()

from scripts.perf.reporting import build_report, read_report, write_report


def compare_api_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    max_latency_regression_percent: float,
) -> dict[str, Any]:
    baseline_endpoints = baseline.get("metrics", {}).get("endpoints", {})
    candidate_endpoints = candidate.get("metrics", {}).get("endpoints", {})
    if not isinstance(baseline_endpoints, dict) or not isinstance(candidate_endpoints, dict):
        raise ValueError("reports do not contain endpoint metrics")
    if set(baseline_endpoints) != set(candidate_endpoints):
        raise ValueError("reports must contain the same endpoint metrics")
    comparisons: list[dict[str, Any]] = []
    for name in sorted(baseline_endpoints):
        before = baseline_endpoints[name]
        after = candidate_endpoints[name]
        before_p95 = float(before["p95_ms"])
        after_p95 = float(after["p95_ms"])
        change = ((after_p95 - before_p95) / before_p95 * 100) if before_p95 > 0 else 0.0
        baseline_failures = int(before.get("failed_requests", 0))
        candidate_failures = int(after.get("failed_requests", 0))
        comparisons.append(
            {
                "name": name,
                "baseline_p95_ms": before_p95,
                "candidate_p95_ms": after_p95,
                "p95_change_percent": round(change, 3),
                "baseline_throughput_rps": float(before["throughput_rps"]),
                "candidate_throughput_rps": float(after["throughput_rps"]),
                "baseline_failed_requests": baseline_failures,
                "candidate_failed_requests": candidate_failures,
                "passed": candidate_failures == 0 and change <= max_latency_regression_percent,
            }
        )
    if not comparisons:
        raise ValueError("reports have no common endpoint metrics")
    return {
        "max_latency_regression_percent": max_latency_regression_percent,
        "comparisons": comparisons,
        "passed": all(item["passed"] for item in comparisons),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two WOMAP performance reports.")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--max-latency-regression-percent", type=float, default=5.0)
    parser.add_argument("--output", type=Path, default=None)
    arguments = parser.parse_args()
    baseline = read_report(arguments.baseline)
    candidate = read_report(arguments.candidate)
    if baseline["kind"] != "api-benchmark" or candidate["kind"] != "api-benchmark":
        parser.error("Gate 1 comparison currently supports api-benchmark reports")
    comparison = compare_api_reports(
        baseline,
        candidate,
        max_latency_regression_percent=arguments.max_latency_regression_percent,
    )
    if arguments.output:
        write_report(
            arguments.output,
            build_report(
                kind="report-comparison",
                profile=str(candidate["environment"].get("profile", "unknown")),
                dataset_tier=str(candidate["environment"].get("dataset_tier", "unknown")),
                workload={"baseline_kind": baseline["kind"], "candidate_kind": candidate["kind"]},
                metrics=comparison,
            ),
        )
    for item in comparison["comparisons"]:
        state = "PASS" if item["passed"] else "FAIL"
        print(
            f"{state} {item['name']}: p95 {item['baseline_p95_ms']:.3f} -> "
            f"{item['candidate_p95_ms']:.3f} ms ({item['p95_change_percent']:+.2f}%)"
        )
    return 0 if comparison["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
