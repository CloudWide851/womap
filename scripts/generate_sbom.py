from __future__ import annotations

import argparse
import json
import re
import tomllib
import uuid
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

import yaml


def _component(name: str, version: str, ecosystem: str) -> dict[str, object]:
    if ecosystem == "pypi":
        normalized_name = re.sub(r"[-_.]+", "-", name).lower()
        purl = f"pkg:pypi/{quote(normalized_name, safe='')}@{quote(version, safe='')}"
    else:
        purl = f"pkg:npm/{quote(name, safe='/')}@{quote(version, safe='')}"
    return {
        "type": "library",
        "name": name,
        "version": version,
        "purl": purl,
        "bom-ref": purl,
        "properties": [{"name": "womap:ecosystem", "value": ecosystem}],
    }


def python_components(distributions: Iterable[metadata.Distribution] | None = None) -> list[dict[str, object]]:
    installed = distributions if distributions is not None else metadata.distributions()
    components: dict[str, dict[str, object]] = {}
    for distribution in installed:
        name = distribution.metadata.get("Name")
        version = distribution.version
        if not name or not version:
            continue
        component = _component(name, version, "pypi")
        components[str(component["bom-ref"])] = component
    return [components[key] for key in sorted(components)]


def _parse_pnpm_package_key(value: str) -> tuple[str, str] | None:
    package_key = value.lstrip("/").split("(", 1)[0]
    separator = package_key.rfind("@")
    if separator <= 0:
        return None
    name, version = package_key[:separator], package_key[separator + 1 :]
    if not name or not version or version.startswith(("file:", "link:", "workspace:")):
        return None
    return name, version


def pnpm_components(lock_path: Path) -> list[dict[str, object]]:
    lock = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
    packages = lock.get("packages", {})
    if not isinstance(packages, dict):
        raise ValueError("pnpm lockfile does not contain a packages mapping")
    components: dict[str, dict[str, object]] = {}
    for package_key in packages:
        parsed = _parse_pnpm_package_key(str(package_key))
        if parsed is None:
            continue
        component = _component(*parsed, "npm")
        components[str(component["bom-ref"])] = component
    return [components[key] for key in sorted(components)]


def build_bom(
    project_name: str,
    project_version: str,
    components: Iterable[dict[str, object]],
) -> dict[str, object]:
    unique = {str(component["bom-ref"]): component for component in components}
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "womap-sbom-generator",
                        "version": "1",
                    }
                ]
            },
            "component": {
                "type": "application",
                "name": project_name,
                "version": project_version,
                "bom-ref": f"pkg:generic/{quote(project_name, safe='')}@{quote(project_version, safe='')}",
            },
        },
        "components": [unique[key] for key in sorted(unique)],
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Generate a CycloneDX SBOM for WOMAP.")
    parser.add_argument("--output", type=Path, default=repo_root / "artifacts" / "womap.cdx.json")
    parser.add_argument("--pnpm-lock", type=Path, default=repo_root / "frontend" / "pnpm-lock.yaml")
    args = parser.parse_args()

    project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    components = [*python_components(), *pnpm_components(args.pnpm_lock)]
    bom = build_bom(str(project["name"]), str(project["version"]), components)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CycloneDX SBOM written with {len(bom['components'])} components: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
