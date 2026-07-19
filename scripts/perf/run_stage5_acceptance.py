from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    from _bootstrap import ensure_repo_root
else:
    from scripts.perf._bootstrap import ensure_repo_root

ensure_repo_root()

from scripts.perf.reporting import build_report, write_report  # noqa: E402
from scripts.perf.system_state_audit import (  # noqa: E402
    capture_system_state,
    compare_system_state,
)


ROOT = Path(__file__).resolve().parents[2]
PERF_ROOT = (ROOT / ".womap-data" / "perf").resolve()
DEFAULT_BASELINE_REF = "fbcc598"
EXPECTED_RASTER_BYTES = 10_909_510_093


@dataclass(frozen=True)
class AcceptanceCheck:
    code: str
    passed: bool
    measured: float | int | str | bool | None
    threshold: str

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "passed": self.passed,
            "measured": self.measured,
            "threshold": self.threshold,
        }


def require_perf_descendant(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == PERF_ROOT or PERF_ROOT not in resolved.parents:
        raise ValueError("stage 5 artifacts must stay below .womap-data/perf")
    return resolved


def evaluate_workstation_evidence(evidence: dict[str, Any]) -> list[AcceptanceCheck]:
    normal_api = _number(evidence, "normal_api_p95_ms")
    bbox = _number(evidence, "bbox_p95_ms")
    bbox_samples = _integer(evidence, "bbox_samples")
    inp = _number(evidence, "inp_p75_ms")
    fps = _number(evidence, "pan_fps_p50")
    rss_one = _integer(evidence, "worker_run_1_peak_rss_bytes")
    rss_two = _integer(evidence, "worker_run_2_peak_rss_bytes")
    handle_growth = _integer(evidence, "worker_handle_growth")
    pool_peak = _integer(evidence, "connection_pool_peak")
    pool_budget = _integer(evidence, "connection_pool_budget")
    checks = [
        _maximum("normal_api_p95", normal_api, 200.0, "<= 200 ms"),
        AcceptanceCheck(
            code="bbox_sample_count",
            passed=bbox_samples is not None and bbox_samples >= 100,
            measured=bbox_samples,
            threshold=">= 100",
        ),
        _maximum("bbox_p95", bbox, 500.0, "<= 500 ms"),
        _maximum("inp_p75", inp, 200.0, "<= 200 ms at p75"),
        _minimum("pan_fps_p50", fps, 45.0, ">= 45 FPS"),
        AcceptanceCheck(
            code="worker_heartbeat_and_lease",
            passed=_integer(evidence, "worker_heartbeat_errors") == 0
            and _integer(evidence, "worker_lease_errors") == 0,
            measured=(
                f"heartbeat={_integer(evidence, 'worker_heartbeat_errors')};"
                f"lease={_integer(evidence, 'worker_lease_errors')}"
            ),
            threshold="both 0",
        ),
        AcceptanceCheck(
            code="worker_rss_plateau",
            passed=(
                rss_one is not None
                and rss_two is not None
                and rss_two <= rss_one * 1.15 + 64 * 1024**2
            ),
            measured=rss_two,
            threshold="run 2 <= run 1 * 1.15 + 64 MiB",
        ),
        AcceptanceCheck(
            code="worker_handle_plateau",
            passed=handle_growth is not None and handle_growth <= 32,
            measured=handle_growth,
            threshold="growth <= 32",
        ),
        AcceptanceCheck(
            code="connection_pool_budget",
            passed=(
                pool_peak is not None
                and pool_budget is not None
                and 0 <= pool_peak <= pool_budget
            ),
            measured=pool_peak,
            threshold=f"<= {pool_budget if pool_budget is not None else 'known budget'}",
        ),
        AcceptanceCheck(
            code="cog_two_zoom_range_reuse",
            passed=(
                _integer(evidence, "cog_zoom_levels") is not None
                and _integer(evidence, "cog_zoom_levels") >= 2
                and _integer(evidence, "cog_range_requests") is not None
                and _integer(evidence, "cog_range_requests") > 0
                and _integer(evidence, "cog_cache_reuses") is not None
                and _integer(evidence, "cog_cache_reuses") > 0
            ),
            measured=_integer(evidence, "cog_cache_reuses"),
            threshold="two zoom levels, Range > 0, cache reuse > 0",
        ),
        _native_smoke(
            "windows_production_smoke",
            evidence.get("windows_production_smoke"),
            evidence.get("windows_environment_kind"),
        ),
        _native_smoke(
            "linux_api_worker_smoke",
            evidence.get("linux_api_worker_smoke"),
            evidence.get("linux_environment_kind"),
        ),
        _boolean("systemd_resource_values_verified", evidence.get("systemd_resource_values_verified")),
        _boolean("system_state_unchanged", evidence.get("system_state_unchanged")),
        _boolean("baseline_candidate_comparable", evidence.get("baseline_candidate_comparable")),
        _boolean("large_dataset_cleanup", evidence.get("large_dataset_cleanup")),
    ]
    return checks


def dataset_preflight(profile: str) -> dict[str, object]:
    if profile == "ci-small":
        root = PERF_ROOT / "ci-small"
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            return {"ready": False, "feature_count": None, "raster_bytes": None}
    else:
        root = PERF_ROOT / "datasets" / "workstation-medium"
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            return {"ready": False, "feature_count": None, "raster_bytes": None}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        workload = manifest.get("workload") or {}
        files = {
            item.get("name"): item for item in (manifest.get("metrics") or {}).get("files") or []
        }
        raster_name = "raster-source.tif" if profile == "workstation-medium" else "raster.tif"
        raster_path = root / raster_name
        vector_path = root / "vectors.geojson"
        feature_count = int(workload.get("feature_count") or 0)
        analysis_candidate_count = int(workload.get("analysis_candidate_count") or 0)
        raster_bytes = raster_path.stat().st_size
        vector_bytes = vector_path.stat().st_size
        expected_bytes = int((files.get(raster_name) or {}).get("bytes") or 0)
        expected_vector_bytes = int((files.get("vectors.geojson") or {}).get("bytes") or 0)
        ready = (
            vector_path.is_file()
            and raster_path.is_file()
            and raster_bytes == expected_bytes
            and vector_bytes == expected_vector_bytes
        )
        if profile == "workstation-medium":
            ready = (
                ready
                and feature_count == 1_000_000
                and analysis_candidate_count == 1_000_000
                and raster_bytes == EXPECTED_RASTER_BYTES
            )
        return {
            "ready": ready,
            "feature_count": feature_count,
            "analysis_candidate_count": analysis_candidate_count,
            "raster_bytes": raster_bytes,
            "vector_bytes": vector_bytes,
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"ready": False, "feature_count": None, "raster_bytes": None}


def verify_git_ref(reference: str) -> bool:
    if not reference or any(character not in "0123456789abcdefABCDEF" for character in reference):
        return False
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", f"{reference}^{{commit}}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and len(completed.stdout.strip()) == 40


def load_evidence(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict) or value.get("schema_version") != "womap.stage5-evidence/v1":
        return {}
    metrics = value.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def run_acceptance(
    *,
    profile: str,
    baseline_ref: str,
    evidence_path: Path,
    output_path: Path,
) -> tuple[dict[str, Any], bool]:
    before = capture_system_state()
    dataset = dataset_preflight(profile)
    baseline_valid = verify_git_ref(baseline_ref)
    evidence = load_evidence(evidence_path)
    workstation_checks = evaluate_workstation_evidence(evidence)
    after = capture_system_state()
    state_comparison = compare_system_state(before, after)
    dataset_check = AcceptanceCheck(
        code="dataset_preflight",
        passed=dataset["ready"] is True,
        measured=(
            f"features={dataset.get('feature_count')};"
            f"analysis={dataset.get('analysis_candidate_count')};"
            f"raster={dataset.get('raster_bytes')}"
            if profile == "workstation-medium"
            else dataset["raster_bytes"]
        ),
        threshold=(
            f"{EXPECTED_RASTER_BYTES} bytes, 1,000,000 features and 1,000,000 candidates"
            if profile == "workstation-medium"
            else "manifest sizes match generated CI data"
        ),
    )
    baseline_check = AcceptanceCheck(
        code="fixed_baseline_ref",
        passed=baseline_valid and baseline_ref.casefold() == DEFAULT_BASELINE_REF,
        measured=baseline_ref if baseline_valid else "invalid",
        threshold=DEFAULT_BASELINE_REF,
    )
    audit_check = AcceptanceCheck(
        code="acceptance_runner_system_state_unchanged",
        passed=state_comparison["all_unchanged"] is True,
        measured=state_comparison["all_unchanged"],
        threshold="true",
    )
    all_checks = [dataset_check, baseline_check, audit_check]
    if profile == "workstation-medium":
        all_checks.extend(workstation_checks)
    passed = all(check.passed for check in all_checks)
    report = build_report(
        kind="stage5-acceptance",
        profile=profile,
        dataset_tier=profile,
        workload={
            "baseline_ref": baseline_ref,
            "mechanism_only": profile == "ci-small",
            "evidence_contract": "womap.stage5-evidence/v1",
        },
        metrics={
            "accepted": passed if profile == "workstation-medium" else False,
            "suite_completed": True,
            "checks": [check.as_dict() for check in all_checks],
            "system_state": state_comparison,
        },
    )
    write_report(require_perf_descendant(output_path), report)
    return report, passed


def _number(evidence: dict[str, Any], key: str) -> float | None:
    value = evidence.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _integer(evidence: dict[str, Any], key: str) -> int | None:
    value = evidence.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _maximum(code: str, measured: float | None, maximum: float, threshold: str) -> AcceptanceCheck:
    return AcceptanceCheck(code, measured is not None and measured <= maximum, measured, threshold)


def _minimum(code: str, measured: float | None, minimum: float, threshold: str) -> AcceptanceCheck:
    return AcceptanceCheck(code, measured is not None and measured >= minimum, measured, threshold)


def _boolean(code: str, measured: object) -> AcceptanceCheck:
    return AcceptanceCheck(code, measured is True, measured if isinstance(measured, bool) else None, "true")


def _native_smoke(code: str, measured: object, environment_kind: object) -> AcceptanceCheck:
    kind = environment_kind if isinstance(environment_kind, str) else None
    return AcceptanceCheck(
        code=code,
        passed=measured is True and kind == "native",
        measured=f"smoke={measured};environment={kind}",
        threshold="smoke=true on native OS",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fail-closed WOMAP stage 5 acceptance checks.")
    parser.add_argument("--profile", choices=("ci-small", "workstation-medium"), required=True)
    parser.add_argument("--baseline-ref", default=DEFAULT_BASELINE_REF)
    parser.add_argument("--confirm-large", action="store_true")
    parser.add_argument(
        "--evidence",
        type=Path,
        default=PERF_ROOT / "stage5" / "evidence-workstation-medium.json",
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.profile == "workstation-medium" and not arguments.confirm_large:
        parser.error("workstation-medium requires --confirm-large")
    output = arguments.output or (
        PERF_ROOT
        / "reports"
        / f"stage5-{arguments.profile}-{uuid.uuid4().hex[:12]}.json"
    )
    try:
        report, passed = run_acceptance(
            profile=arguments.profile,
            baseline_ref=arguments.baseline_ref,
            evidence_path=require_perf_descendant(arguments.evidence),
            output_path=output,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if arguments.profile == "ci-small":
        print("Stage 5 CI-small mechanism report completed; it does not grant release acceptance.")
        return 0
    print(f"Stage 5 workstation acceptance: {'passed' if passed else 'rejected'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
