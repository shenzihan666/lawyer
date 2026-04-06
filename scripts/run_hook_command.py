#!/usr/bin/env python3

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def platform_command(name: str) -> str:
    if os.name == "nt" and name == "pnpm":
        return "pnpm.cmd"
    return name


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "usage: run_hook_command.py <hook-id> <command> [args...]",
            file=sys.stderr,
        )
        return 1

    hook_id = sys.argv[1]
    command = sys.argv[2:]

    if os.environ.get("CI"):
        print(f"Skipping {hook_id} because CI is set.")
        return 0

    repo_root = Path(__file__).resolve().parent.parent
    command = [platform_command(command[0]), *command[1:]]
    environment = os.environ.copy()
    if command[0] == "uv":
        environment.pop("VIRTUAL_ENV", None)
    return subprocess.run(
        command,
        cwd=repo_root,
        env=environment,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
