from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "start-womap.sh"
WORKER = ROOT / "app" / "features" / "jobs" / "worker.py"


def test_linux_launcher_exposes_production_lifecycle_and_safe_stop_contract() -> None:
    launcher = LAUNCHER.read_text(encoding="utf-8")

    for action in ("setup", "run", "worker", "status", "doctor", "upgrade", "stop"):
        assert f"{action})" in launcher
    assert "WOMAP_RUNTIME_MODE=production" in launcher
    assert "app.main:app" in launcher
    assert "app.features.jobs.worker" in launcher
    assert "nice -n 10" not in launcher
    worker = WORKER.read_text(encoding="utf-8")
    assert "current_nice = os.nice(0)" in worker
    assert "os.nice(settings.linux_nice - current_nice)" in worker
    assert "--reload" not in launcher
    assert "process_start_ticks" in launcher
    assert 'actual_ticks == "$RECORD_START_TICKS"' not in launcher
    assert '"$actual_ticks" == "$RECORD_START_TICKS"' in launcher
    assert 'command_line" == *"$RECORD_COMMAND_TOKEN"*' in launcher

    worker_stop = launcher.index("stop_service run-worker 1")
    api_stop = launcher.index("stop_service run-api 0", worker_stop)
    assert worker_stop < api_stop


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="Native Linux Bash is unavailable",
)
def test_linux_launcher_has_valid_bash_syntax() -> None:
    completed = subprocess.run(
        ["bash", "-n", str(LAUNCHER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
