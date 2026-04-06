#!/usr/bin/env python3

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def normalize_argument(argument: str) -> str:
    normalized = argument.replace("\\", "/")
    if normalized.startswith("backend/"):
        return normalized.removeprefix("backend/")
    return argument


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    args = [normalize_argument(argument) for argument in sys.argv[1:]]
    if len(args) <= 1:
        return 0
    command = ["uv", "run", "--directory", "backend", "ruff", *args]
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)
    return subprocess.run(
        command,
        cwd=repo_root,
        env=environment,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
