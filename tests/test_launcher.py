import base64
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "launcher.ps1"


def test_launcher_dev_contract_is_independent_and_cleans_captured_process() -> None:
    launcher = LAUNCHER.read_text(encoding="utf-8-sig")

    assert "function Start-DevelopmentServices" in launcher
    assert '"dev" { return (Start-DevelopmentServices) }' in launcher
    assert "Stop-CapturedProcessTree -CapturedProcess $launchedProcess" in launcher
    assert 'if ($MyInvocation.InvocationName -ne ".")' in launcher

    cleanup_index = launcher.index("Stop-CapturedProcessTree -CapturedProcess $launchedProcess")
    record_index = launcher.index("Remove-ServiceRecord $Name", cleanup_index)
    assert cleanup_index < record_index


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher test")
def test_dev_orchestration_attempts_web_after_api_failure() -> None:
    launcher_literal = str(LAUNCHER).replace("'", "''")
    script = f"""
$ErrorActionPreference = "Stop"
. '{launcher_literal}'
$script:Calls = [System.Collections.Generic.List[string]]::new()
$result = Start-DevelopmentServices `
    -ApiStartAction {{ [void]$script:Calls.Add("api"); throw "forced api failure" }} `
    -WebStartAction {{ [void]$script:Calls.Add("web") }}
if ($result -ne 1) {{ throw "expected aggregated failure code 1, got $result" }}
if (($script:Calls -join ",") -ne "api,web") {{
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
