from __future__ import annotations

from email.message import Message
from pathlib import Path

from scripts.audit_pnpm import advisory_findings, production_packages
from scripts.generate_sbom import build_bom, pnpm_components, python_components
from scripts.security_scan import is_local_only_path, scan_files


class FakeDistribution:
    def __init__(self, name: str, version: str) -> None:
        self.metadata = Message()
        self.metadata["Name"] = name
        self.version = version


def test_tracked_secret_scan_reports_location_without_secret_value(tmp_path: Path) -> None:
    secret = "AKIA" + "A" * 16
    (tmp_path / "safe.txt").write_text("ordinary configuration", encoding="utf-8")
    (tmp_path / "unsafe.txt").write_text(f"header\n{secret}\n", encoding="utf-8")

    findings = scan_files(tmp_path, ["safe.txt", "unsafe.txt"])

    assert [(finding.rule, finding.path, finding.line) for finding in findings] == [
        ("aws-access-key", "unsafe.txt", 2)
    ]
    assert secret not in repr(findings)


def test_local_only_paths_are_rejected_but_examples_are_allowed() -> None:
    assert is_local_only_path("config/settings.local.yaml")
    assert is_local_only_path(".womap-data/cache.bin")
    assert is_local_only_path(".env.production")
    assert not is_local_only_path(".env.example")
    assert not is_local_only_path("config/settings.example.yaml")


def test_sbom_combines_python_and_pnpm_components(tmp_path: Path) -> None:
    lock_path = tmp_path / "pnpm-lock.yaml"
    lock_path.write_text(
        "lockfileVersion: '9.0'\npackages:\n  '@scope/widget@2.1.0': {}\n  react@19.2.0: {}\n",
        encoding="utf-8",
    )
    components = [
        *python_components([FakeDistribution("FastAPI", "1.2.3")]),
        *pnpm_components(lock_path),
    ]

    bom = build_bom("womap", "0.1.0", components)

    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] == "1.5"
    assert len(bom["components"]) == 3
    purls = {component["purl"] for component in bom["components"]}
    assert "pkg:pypi/fastapi@1.2.3" in purls
    assert "pkg:npm/%40scope/widget@2.1.0" in purls


def test_pnpm_audit_walks_only_the_production_dependency_graph() -> None:
    lock = {
        "importers": {
            ".": {
                "dependencies": {"web": {"version": "1.0.0(peer@2.0.0)"}},
                "devDependencies": {"dev-only": {"version": "9.0.0"}},
            }
        },
        "snapshots": {
            "web@1.0.0(peer@2.0.0)": {"dependencies": {"nested": "3.0.0"}},
            "nested@3.0.0": {},
            "peer@2.0.0": {},
            "dev-only@9.0.0": {},
        },
    }

    assert production_packages(lock) == {"web": {"1.0.0"}, "nested": {"3.0.0"}}


def test_pnpm_audit_enforces_the_selected_severity_without_echoing_payloads() -> None:
    packages = {"web": {"1.0.0"}}
    response = {
        "web": [
            {"id": 10, "severity": "moderate"},
            {"id": 11, "severity": "high"},
        ]
    }

    findings = advisory_findings(response, packages, "high")

    assert [(item.package, item.severity, item.advisory_id) for item in findings] == [
        ("web", "high", "11")
    ]
