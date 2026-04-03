#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    frontend_root = repo_root / "frontend"
    files = [path.removeprefix("frontend/") for path in sys.argv[1:]]
    command = [
        "pnpm",
        "exec",
        "prettier",
        "--write",
        "--ignore-unknown",
        *files,
    ]
    return subprocess.run(command, cwd=frontend_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
