#!/usr/bin/env python3

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def platform_command(name: str) -> str:
    if sys.platform == "win32" and name == "pnpm":
        return "pnpm.cmd"
    return name


def normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("frontend/"):
        return normalized.removeprefix("frontend/")
    return path


def resolve_pnpm() -> str:
    candidates = [
        platform_command("pnpm"),
        "pnpm",
    ]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    appdata = os.environ.get("APPDATA")
    if appdata:
        fallback = Path(appdata) / "npm" / "pnpm.cmd"
        if fallback.exists():
            return str(fallback)

    nvm_fallback = Path(r"C:\nvm4w\nodejs\pnpm.cmd")
    if nvm_fallback.exists():
        return str(nvm_fallback)

    return platform_command("pnpm")


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    frontend_root = repo_root / "frontend"
    files = [normalize_path(path) for path in sys.argv[1:]]
    if not files:
        return 0
    command = [resolve_pnpm(), "exec", "prettier", "--write", "--ignore-unknown", *files]
    return subprocess.run(command, cwd=frontend_root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
