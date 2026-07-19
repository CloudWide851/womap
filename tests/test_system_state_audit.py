from __future__ import annotations

import json
from pathlib import Path

from scripts.perf.system_state_audit import capture_system_state, compare_system_state


def test_windows_system_state_report_only_exposes_change_booleans() -> None:
    private_value = r"C:\private\application.exe"

    def runner(arguments, _timeout):
        return f"{' '.join(arguments[:2])}:{private_value}"

    before = capture_system_state(platform_name="windows", command_runner=runner)
    after = capture_system_state(platform_name="windows", command_runner=runner)
    comparison = compare_system_state(before, after)
    serialized = json.dumps(comparison)

    assert comparison["all_unchanged"] is True
    assert all(comparison["unchanged"].values())
    assert private_value not in serialized
    assert not any(fingerprint in serialized for fingerprint in before.fingerprints.values())


def test_linux_system_state_detects_one_changed_setting(tmp_path: Path) -> None:
    scheduler = tmp_path / "sda" / "queue" / "scheduler"
    scheduler.parent.mkdir(parents=True)
    scheduler.write_text("[none] mq-deadline\n", encoding="ascii")
    power = "balanced"

    def runner(arguments, _timeout):
        return power if arguments[0] == "powerprofilesctl" else "60\n20\n10"

    before = capture_system_state(
        platform_name="linux",
        command_runner=runner,
        sys_block_root=tmp_path,
    )
    scheduler.write_text("none [mq-deadline]\n", encoding="ascii")
    after = capture_system_state(
        platform_name="linux",
        command_runner=runner,
        sys_block_root=tmp_path,
    )

    comparison = compare_system_state(before, after)

    assert comparison["all_unchanged"] is False
    assert comparison["unchanged"] == {
        "io_scheduler": False,
        "power": True,
        "sysctl": True,
    }


def test_system_state_fails_closed_when_a_probe_is_unavailable() -> None:
    def runner(arguments, _timeout):
        return None if arguments[0] == "reg.exe" else "stable"

    before = capture_system_state(platform_name="windows", command_runner=runner)
    after = capture_system_state(platform_name="windows", command_runner=runner)

    comparison = compare_system_state(before, after)

    assert comparison["all_unchanged"] is False
    assert comparison["unchanged"]["application_gpu_preference"] is False
    assert "observed" not in comparison
