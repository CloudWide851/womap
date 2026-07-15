from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml


NPM_BULK_ADVISORY_URL = "https://registry.npmjs.org/-/npm/v1/security/advisories/bulk"
SEVERITY_ORDER = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class AdvisoryFinding:
    package: str
    version: str
    severity: str
    advisory_id: str


def parse_package_key(value: str) -> tuple[str, str] | None:
    package_key = value.lstrip("/").split("(", 1)[0]
    separator = package_key.rfind("@")
    if separator <= 0:
        return None
    name, version = package_key[:separator], package_key[separator + 1 :]
    return (name, version) if name and version else None


def _dependency_target(
    name: str,
    value: object,
    snapshots: dict[str, object],
) -> str | None:
    version = value.get("version") if isinstance(value, dict) else value
    if not isinstance(version, str) or version.startswith(("file:", "link:", "workspace:")):
        return None
    if version.startswith("npm:"):
        alias = parse_package_key(version.removeprefix("npm:"))
        if alias is None:
            return None
        name, version = alias
    exact = f"{name}@{version}"
    if exact in snapshots:
        return exact
    requested = parse_package_key(exact)
    if requested is None:
        return None
    for snapshot_key in snapshots:
        if parse_package_key(snapshot_key) == requested:
            return snapshot_key
    return None


def production_packages(lock: dict[str, Any], importer_name: str = ".") -> dict[str, set[str]]:
    importers = lock.get("importers", {})
    snapshots = lock.get("snapshots", {})
    if not isinstance(importers, dict) or not isinstance(snapshots, dict):
        raise ValueError("pnpm lockfile must contain importers and snapshots mappings")
    importer = importers.get(importer_name)
    if not isinstance(importer, dict):
        raise ValueError(f"pnpm importer is missing: {importer_name}")

    queue: deque[str] = deque()
    for group in ("dependencies", "optionalDependencies"):
        dependencies = importer.get(group, {})
        if not isinstance(dependencies, dict):
            continue
        for name, value in dependencies.items():
            target = _dependency_target(str(name), value, snapshots)
            if target is not None:
                queue.append(target)

    visited: set[str] = set()
    packages: dict[str, set[str]] = defaultdict(set)
    while queue:
        snapshot_key = queue.popleft()
        if snapshot_key in visited:
            continue
        visited.add(snapshot_key)
        parsed = parse_package_key(snapshot_key)
        if parsed is None:
            continue
        name, version = parsed
        packages[name].add(version)
        snapshot = snapshots.get(snapshot_key, {})
        if not isinstance(snapshot, dict):
            continue
        for group in ("dependencies", "optionalDependencies"):
            dependencies = snapshot.get(group, {})
            if not isinstance(dependencies, dict):
                continue
            for dependency_name, value in dependencies.items():
                target = _dependency_target(str(dependency_name), value, snapshots)
                if target is not None and target not in visited:
                    queue.append(target)
    return dict(packages)


def advisory_findings(
    response: dict[str, object],
    packages: dict[str, set[str]],
    minimum_severity: str,
) -> list[AdvisoryFinding]:
    threshold = SEVERITY_ORDER[minimum_severity]
    findings: list[AdvisoryFinding] = []
    for package, advisories in response.items():
        if package not in packages or not isinstance(advisories, list):
            continue
        for advisory in advisories:
            if not isinstance(advisory, dict):
                continue
            severity = str(advisory.get("severity", "info")).lower()
            if SEVERITY_ORDER.get(severity, 0) < threshold:
                continue
            advisory_id = str(advisory.get("id") or advisory.get("url") or "unknown")
            for version in sorted(packages[package]):
                findings.append(AdvisoryFinding(package, version, severity, advisory_id))
    return sorted(findings, key=lambda item: (item.package, item.version, item.advisory_id))


def query_bulk_advisories(
    packages: dict[str, set[str]],
    timeout: float = 30,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, object]:
    payload = json.dumps({name: sorted(versions) for name, versions in packages.items()}).encode()
    request = urllib.request.Request(
        NPM_BULK_ADVISORY_URL,
        data=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "womap-dependency-audit/1",
        },
        method="POST",
    )
    with opener(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict) or "error" in result:
        raise ValueError("npm advisory endpoint returned an invalid response")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit pnpm production dependencies via npm bulk advisories.")
    parser.add_argument("--lockfile", type=Path, default=Path("frontend/pnpm-lock.yaml"))
    parser.add_argument("--importer", default=".")
    parser.add_argument("--severity", choices=tuple(SEVERITY_ORDER), default="high")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    try:
        lock = yaml.safe_load(args.lockfile.read_text(encoding="utf-8")) or {}
        packages = production_packages(lock, args.importer)
        response = query_bulk_advisories(packages, args.timeout)
        findings = advisory_findings(response, packages, args.severity)
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        print(f"pnpm dependency audit failed: {type(exc).__name__}")
        return 2
    if findings:
        print(f"pnpm dependency audit found {len(findings)} advisory match(es):")
        for finding in findings:
            print(
                f"- {finding.package}@{finding.version} "
                f"[{finding.severity}] advisory {finding.advisory_id}"
            )
        return 1
    component_count = sum(len(versions) for versions in packages.values())
    print(f"pnpm dependency audit passed for {component_count} production package versions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
