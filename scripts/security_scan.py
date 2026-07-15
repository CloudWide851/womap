from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


MAX_SCAN_BYTES = 5 * 1024 * 1024

SECRET_PATTERNS = {
    "private-key": re.compile(
        rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
    ),
    "aws-access-key": re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github-token": re.compile(
        rb"\bgh[pousr]_[A-Za-z0-9]{36,255}\b|\bgithub_pat_[A-Za-z0-9_]{40,255}\b"
    ),
    "google-api-key": re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"),
    "slack-token": re.compile(rb"\bxox[baprs]-[0-9A-Za-z-]{20,}\b"),
    "stripe-live-key": re.compile(rb"\b(?:sk|rk)_live_[0-9A-Za-z]{20,}\b"),
}

LOCAL_ONLY_PATHS = {
    "AGENTS.md",
    "AGENTS_LOG.md",
    "MEMORY.md",
    "config/settings.local.yaml",
}
LOCAL_ONLY_PREFIXES = (
    ".pytest-tmp/",
    ".trellis/",
    ".womap-data/",
    ".womap-launcher/",
)


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int | None = None


def _git_paths(repo_root: Path, *arguments: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", *arguments],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return [item.decode("utf-8", errors="surrogateescape") for item in result.stdout.split(b"\0") if item]


def is_local_only_path(path: str) -> bool:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    if normalized in LOCAL_ONLY_PATHS:
        return True
    if normalized == ".env" or (normalized.startswith(".env.") and normalized != ".env.example"):
        return True
    return normalized.startswith(LOCAL_ONLY_PREFIXES)


def scan_files(repo_root: Path, tracked_paths: Iterable[str]) -> list[Finding]:
    findings: list[Finding] = []
    for tracked_path in tracked_paths:
        normalized = PurePosixPath(tracked_path.replace("\\", "/")).as_posix()
        if is_local_only_path(normalized):
            findings.append(Finding("local-only-path", normalized))
        candidate = repo_root / Path(*PurePosixPath(normalized).parts)
        if candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            if candidate.stat().st_size > MAX_SCAN_BYTES:
                continue
            content = candidate.read_bytes()
        except OSError:
            findings.append(Finding("unreadable-tracked-file", normalized))
            continue
        for rule, pattern in SECRET_PATTERNS.items():
            match = pattern.search(content)
            if match:
                findings.append(Finding(rule, normalized, content.count(b"\n", 0, match.start()) + 1))
    return findings


def scan_repository(repo_root: Path) -> list[Finding]:
    tracked_paths = _git_paths(repo_root)
    findings = scan_files(repo_root, tracked_paths)
    ignored_but_tracked = _git_paths(repo_root, "-ci", "--exclude-standard")
    findings.extend(Finding("tracked-ignored-path", path) for path in ignored_but_tracked)
    return sorted(set(findings), key=lambda item: (item.path, item.rule, item.line or 0))


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan tracked files without echoing secret values.")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    repo_root = args.repo.resolve()
    findings = scan_repository(repo_root)
    if findings:
        print(f"Tracked-file security scan failed with {len(findings)} finding(s):")
        for finding in findings:
            location = f":{finding.line}" if finding.line is not None else ""
            print(f"- [{finding.rule}] {finding.path}{location}")
        return 1
    print("Tracked-file security scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
