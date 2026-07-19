from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_ROOT = ROOT / "deploy" / "systemd"


def _unit(name: str) -> str:
    return (SYSTEMD_ROOT / name).read_text(encoding="utf-8")


def test_linux_api_unit_uses_production_single_process_runtime() -> None:
    unit = _unit("womap-api.service.example")

    assert "Environment=WOMAP_RUNTIME_MODE=production" in unit
    assert "Environment=WOMAP_WORKER_ENABLED=true" in unit
    assert "ExecStartPre=/usr/bin/env uv run alembic upgrade head" in unit
    assert "ExecStart=/usr/bin/env uv run uvicorn app.main:app" in unit
    assert "--reload" not in unit
    assert "Nice=0" in unit
    assert "CPUWeight=100" in unit
    assert "IOWeight=100" in unit


def test_linux_worker_unit_has_lower_native_resource_priority() -> None:
    unit = _unit("womap-worker.service.example")

    assert "Environment=WOMAP_RUNTIME_MODE=production" in unit
    assert "Environment=WOMAP_WORKER_ENABLED=true" in unit
    assert "ExecStart=/usr/bin/env uv run python -m app.features.jobs.worker" in unit
    assert "KillSignal=SIGTERM" in unit
    assert "Nice=10" in unit
    assert "CPUWeight=40" in unit
    assert "IOWeight=40" in unit
    assert "MemoryHigh=50%" in unit
    assert "TasksMax=512" in unit
    assert "LimitNOFILE=8192" in unit


def test_linux_units_do_not_change_global_operating_system_settings() -> None:
    combined = "\n".join(
        _unit(name)
        for name in ("womap-api.service.example", "womap-worker.service.example")
    ).casefold()

    for forbidden in (
        "sysctl",
        "ioscheduler",
        "powerprofilesctl",
        "cpupower",
        "/sys/",
    ):
        assert forbidden not in combined
