from __future__ import annotations

import pytest

from app.shared.config import ROOT_DIR
from scripts.perf.benchmark_gpu_formula import (
    FormulaSample,
    require_perf_path,
    summarize_samples,
)


def test_gpu_benchmark_paths_are_confined_to_ignored_perf_root() -> None:
    accepted = require_perf_path(
        ROOT_DIR / ".womap-data" / "perf" / "reports" / "gpu.json"
    )
    assert accepted.name == "gpu.json"

    with pytest.raises(ValueError, match="must stay below"):
        require_perf_path(ROOT_DIR / "README.md")


def test_gpu_benchmark_summary_uses_only_warm_samples_for_gate_speedup() -> None:
    samples: list[FormulaSample] = []
    for formula in ("simple", "complex"):
        samples.extend(
            [
                FormulaSample("cpu", formula, 0, True, 99.0, {}, 1),
                FormulaSample("cupy", formula, 0, True, 199.0, {}, 8),
            ]
        )
        for round_index in range(1, 4):
            samples.extend(
                [
                    FormulaSample("cpu", formula, round_index, False, 3.0, {}, 1),
                    FormulaSample("cupy", formula, round_index, False, 2.0, {}, 8),
                ]
            )

    summary = summarize_samples(samples, initialization_ms=1000)

    assert summary["aggregate_speedup"] == pytest.approx(1.5)
    formulas = summary["formulas"]
    assert formulas["simple"]["cold_gpu_seconds_including_initialization"] == 200.0
    assert formulas["complex"]["speedup"] == pytest.approx(1.5)
