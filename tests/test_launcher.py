import base64
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "launcher.ps1"
WINDOWS_ENTRYPOINT = ROOT / "start-womap.bat"


def test_launcher_dev_contract_is_independent_and_cleans_captured_process() -> None:
    launcher = LAUNCHER.read_text(encoding="utf-8-sig")

    assert "function Start-DevelopmentServices" in launcher
    assert '"dev" { return (Start-DevelopmentServices) }' in launcher
    assert 'Name = "dev-api"' in launcher
    assert 'Name = "dev-worker"' in launcher
    assert 'Name = "dev-web"' in launcher
    assert "Stop-CapturedProcessTree -CapturedProcess $launchedProcess" in launcher
    assert 'if ($MyInvocation.InvocationName -ne ".")' in launcher

    cleanup_index = launcher.index("Stop-CapturedProcessTree -CapturedProcess $launchedProcess")
    record_index = launcher.index("Remove-ServiceRecord $Name", cleanup_index)
    assert cleanup_index < record_index


def test_api_start_runs_migrations_before_starting_uvicorn() -> None:
    launcher = LAUNCHER.read_text(encoding="utf-8-sig")

    assert "function Invoke-ApiMigrations" in launcher
    assert "& uv run alembic upgrade head" in launcher
    start_api = launcher.index("function Start-Api")
    migration = launcher.index("Invoke-ApiMigrations", start_api)
    managed_process = launcher.index("Start-ManagedProcess", start_api)
    assert migration < managed_process


def test_production_runtime_uses_distinct_services_without_reload() -> None:
    launcher = LAUNCHER.read_text(encoding="utf-8-sig")

    production_api = launcher[
        launcher.index("function Start-ProductionApi") : launcher.index(
            "function Start-ProductionWorker"
        )
    ]
    assert '-Name "run-api"' in production_api
    assert '--reload' not in production_api
    assert '-RuntimeMode "production"' in production_api
    assert '-PriorityClass "Normal"' in production_api

    production_worker = launcher[
        launcher.index("function Start-ProductionWorker") : launcher.index(
            "function Start-Worker"
        )
    ]
    assert '-Name "run-worker"' in production_worker
    assert "app.features.jobs.worker" in production_worker
    assert '-PriorityClass "BelowNormal"' in production_worker
    assert "--ready-file" in production_worker
    assert "--stop-file" in production_worker
    assert "$launcherProcess.PriorityClass" in launcher
    assert "(?:LISTENING|BOUND)" in launcher
    assert "netstat.exe -anoq -p tcp" in launcher

    entrypoint = WINDOWS_ENTRYPOINT.read_text(encoding="utf-8")
    assert '-File "%LAUNCHER%" run' in entrypoint


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher test")
def test_api_start_stops_when_migration_fails() -> None:
    launcher_literal = str(LAUNCHER).replace("'", "''")
    script = f"""
$ErrorActionPreference = "Stop"
. '{launcher_literal}'
$script:ManagedStarted = $false
function Start-ManagedProcess {{ $script:ManagedStarted = $true }}
try {{
    Start-Api -MigrationAction {{ throw "forced migration failure" }}
    throw "Start-Api unexpectedly succeeded"
}}
catch {{
    if ($_.Exception.Message -ne "forced migration failure") {{ throw }}
}}
if ($script:ManagedStarted) {{ throw "API process started after migration failure" }}
exit 0
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher test")
def test_dev_orchestration_attempts_web_after_api_failure() -> None:
    launcher_literal = str(LAUNCHER).replace("'", "''")
    script = f"""
$ErrorActionPreference = "Stop"
. '{launcher_literal}'
$script:Calls = [System.Collections.Generic.List[string]]::new()
$result = Start-DevelopmentServices `
    -ApiStartAction {{ [void]$script:Calls.Add("api"); throw "forced api failure" }} `
    -WorkerStartAction {{ [void]$script:Calls.Add("worker") }} `
    -WebStartAction {{ [void]$script:Calls.Add("web") }}
if ($result -ne 1) {{ throw "expected aggregated failure code 1, got $result" }}
if (($script:Calls -join ",") -ne "api,worker,web") {{
    throw ("unexpected call order: " + ($script:Calls -join ","))
}}
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher test")
def test_production_worker_failure_rolls_back_only_new_api() -> None:
    launcher_literal = str(LAUNCHER).replace("'", "''")
    script = f"""
$ErrorActionPreference = "Stop"
. '{launcher_literal}'
$script:Calls = [System.Collections.Generic.List[string]]::new()
function Stop-ManagedProcess {{
    param([string]$Name)
    [void]$script:Calls.Add("stop:" + $Name)
}}
$result = Start-ProductionServices `
    -BuildAction {{ [void]$script:Calls.Add("build"); Write-Output "build output" }} `
    -MigrationAction {{ [void]$script:Calls.Add("migrate"); Write-Output "migration output" }} `
    -ApiStartAction {{ [void]$script:Calls.Add("api"); return "started" }} `
    -WorkerStartAction {{ [void]$script:Calls.Add("worker"); throw "forced worker failure" }} `
    -BrowserAction {{ [void]$script:Calls.Add("browser") }}
if ($result -ne 1) {{ throw "expected production failure" }}
if ($result -is [array]) {{ throw "production result was polluted by action output" }}
if (($script:Calls -join ",") -ne "build,migrate,api,worker,stop:run-api") {{
    throw ("unexpected call order: " + ($script:Calls -join ","))
}}
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher test")
def test_production_refuses_external_api_listener_without_stopping_it() -> None:
    launcher_literal = str(LAUNCHER).replace("'", "''")
    script = f"""
$ErrorActionPreference = "Stop"
. '{launcher_literal}'
$script:Calls = [System.Collections.Generic.List[string]]::new()
function Stop-ManagedProcess {{
    param([string]$Name)
    [void]$script:Calls.Add("stop:" + $Name)
}}
$result = Start-ProductionServices `
    -BuildAction {{ [void]$script:Calls.Add("build") }} `
    -MigrationAction {{ [void]$script:Calls.Add("migrate") }} `
    -ApiStartAction {{ [void]$script:Calls.Add("api"); return "listening" }} `
    -WorkerStartAction {{ [void]$script:Calls.Add("worker") }} `
    -BrowserAction {{ [void]$script:Calls.Add("browser") }}
if ($result -ne 1) {{ throw "expected external-listener failure" }}
if (($script:Calls -join ",") -ne "build,migrate,api") {{
    throw ("unexpected call order: " + ($script:Calls -join ","))
}}
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher test")
def test_stop_order_is_worker_then_web_then_api() -> None:
    launcher_literal = str(LAUNCHER).replace("'", "''")
    script = f"""
$ErrorActionPreference = "Stop"
. '{launcher_literal}'
$script:Calls = [System.Collections.Generic.List[string]]::new()
function Stop-ManagedProcess {{
    param([string]$Name)
    [void]$script:Calls.Add($Name)
}}
Stop-AllManagedServices
$expected = "run-worker,dev-worker,dev-web,web,run-api,dev-api,api"
if (($script:Calls -join ",") -ne $expected) {{
    throw ("unexpected stop order: " + ($script:Calls -join ","))
}}
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
