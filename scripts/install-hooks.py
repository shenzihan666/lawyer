#!/usr/bin/env python3

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def platform_command(name: str) -> str:
    if os.name == "nt" and name == "pnpm":
        return "pnpm.cmd"
    return name


def run(command: list[str], *, cwd: Path) -> int:
    command = [platform_command(command[0]), *command[1:]]
    print("+", " ".join(command))
    return subprocess.run(command, cwd=cwd, check=False).returncode


def ensure_command(name: str) -> bool:
    if shutil.which(platform_command(name)):
        return True

    print(f"Required command not found on PATH: {name}", file=sys.stderr)
    return False


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    if not all(ensure_command(command) for command in ("uv", "pnpm")):
        return 1

    setup_commands = (
        ["uv", "sync", "--directory", "backend", "--group", "dev"],
        ["pnpm", "install", "--dir", "frontend"],
    )

    for command in setup_commands:
        if run(command, cwd=repo_root) != 0:
            return 1

    if os.environ.get("CI"):
        print("CI detected; skipping Git hook installation.")
        return 0

    install_command = [
        "uv",
        "run",
        "--directory",
        "backend",
        "pre-commit",
        "install",
        "--config",
        "../.pre-commit-config.yaml",
        "--install-hooks",
        "--overwrite",
        "--hook-type",
        "pre-commit",
        "--hook-type",
        "pre-push",
        "--hook-type",
        "commit-msg",
    ]
    return run(install_command, cwd=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
