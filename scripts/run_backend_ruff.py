#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    args = [
        path.removeprefix("backend/") if path.startswith("backend/") else path
        for path in sys.argv[1:]
    ]
    command = ["uv", "run", "--directory", "backend", "ruff", *args]
    return subprocess.run(command, cwd=repo_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
