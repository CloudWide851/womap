from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_root() -> None:
    repo_root = str(Path(__file__).resolve().parents[2])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
