#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from pathlib import Path


DISALLOWED_PATTERNS = (
    (re.compile(r"\bconsole\.log\s*\("), "console.log"),
    (re.compile(r"\bdebugger\b"), "debugger"),
)


def normalize_repo_path(path: str) -> Path:
    normalized = path.replace("\\", "/")
    return Path(*normalized.split("/"))


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    failed = False

    for raw_path in sys.argv[1:]:
        relative_path = normalize_repo_path(raw_path)
        absolute_path = repo_root / relative_path
        try:
            lines = absolute_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            continue

        for line_number, line in enumerate(lines, start=1):
            for pattern, label in DISALLOWED_PATTERNS:
                if pattern.search(line):
                    print(
                        f"{relative_path.as_posix()}:{line_number}: remove {label} before committing",
                        file=sys.stderr,
                    )
                    failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
