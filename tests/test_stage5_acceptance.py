from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.perf import run_stage5_acceptance
from scripts.perf.run_stage5_acceptance import (
    evaluate_workstation_evidence,
    require_perf_descendant,
)


def passing_evidence() -> dict[str, object]:
    return {
        "normal_api_p95_ms": 180.0,
        "bbox_samples": 100,
        "bbox_p95_ms": 450.0,
        "inp_p75_ms": 190.0,
        "pan_fps_p50": 48.0,
        "worker_heartbeat_errors": 0,
        "worker_lease_errors": 0,
        "worker_run_1_peak_rss_bytes": 512 * 1024**2,
        "worker_run_2_peak_rss_bytes": 600 * 1024**2,
        "worker_handle_growth": 20,
        "connection_pool_peak": 8,
        "connection_pool_budget": 10,
        "cog_zoom_levels": 2,
        "cog_range_requests": 12,
        "cog_cache_reuses": 2,
        "windows_production_smoke": True,
        "windows_environment_kind": "native",
        "linux_api_worker_smoke": True,
        "linux_environment_kind": "native",
        "systemd_resource_values_verified": True,
        "system_state_unchanged": True,
        "baseline_candidate_comparable": True,
        "large_dataset_cleanup": True,
    }


def test_stage5_evaluator_accepts_complete_bounded_evidence() -> None:
    checks = evaluate_workstation_evidence(passing_evidence())

    assert checks
    assert all(check.passed for check in checks)


def test_stage5_evaluator_fails_closed_for_missing_or_over_budget_evidence() -> None:
    evidence = passing_evidence()
    evidence.pop("inp_p75_ms")
    evidence["worker_run_2_peak_rss_bytes"] = 2 * 1024**3
    evidence["worker_heartbeat_errors"] = 1
    evidence["connection_pool_peak"] = 11

    checks = {check.code: check for check in evaluate_workstation_evidence(evidence)}

    assert checks["inp_p75"].passed is False
    assert checks["worker_rss_plateau"].passed is False
    assert checks["worker_heartbeat_and_lease"].passed is False
    assert checks["connection_pool_budget"].passed is False


def test_stage5_evaluator_does_not_treat_wsl2_as_native_linux() -> None:
    evidence = passing_evidence()
    evidence["linux_environment_kind"] = "wsl2"

    checks = {check.code: check for check in evaluate_workstation_evidence(evidence)}

    assert checks["linux_api_worker_smoke"].passed is False
    assert checks["linux_api_worker_smoke"].measured == "smoke=True;environment=wsl2"


def test_stage5_artifacts_are_restricted_to_ignored_performance_storage(tmp_path: Path) -> None:
    allowed = run_stage5_acceptance.PERF_ROOT / "stage5" / "report.json"

    assert require_perf_descendant(allowed) == allowed.resolve()
    with pytest.raises(ValueError, match="below .womap-data/perf"):
        require_perf_descendant(tmp_path / "report.json")


def test_ci_dataset_preflight_checks_both_manifest_file_sizes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "perf"
    dataset = root / "ci-small"
    dataset.mkdir(parents=True)
    vector = dataset / "vectors.geojson"
    raster = dataset / "raster.tif"
    vector.write_bytes(b"vector")
    raster.write_bytes(b"raster")
    (dataset / "manifest.json").write_text(
        json.dumps(
            {
                "workload": {"feature_count": 1},
                "metrics": {
                    "files": [
                        {"name": vector.name, "bytes": vector.stat().st_size},
                        {"name": raster.name, "bytes": raster.stat().st_size},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(run_stage5_acceptance, "PERF_ROOT", root.resolve())

    assert run_stage5_acceptance.dataset_preflight("ci-small")["ready"] is True

    vector.write_bytes(b"changed-size")
    assert run_stage5_acceptance.dataset_preflight("ci-small")["ready"] is False
