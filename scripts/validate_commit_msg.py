#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from pathlib import Path


ALLOWED_TYPES = {
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "test",
    "chore",
    "perf",
    "ci",
    "build",
    "revert",
}

COMMIT_RE = re.compile(
    r"^(?P<type>[a-z]+)(\([a-z0-9._/-]+\))?!?: [^ ].+",
)


def main() -> int:
    if len(sys.argv) != 2:
        print("expected commit message file path", file=sys.stderr)
        return 1

    message = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
    subject = next(
        (
            line.strip()
            for line in message
            if line.strip() and not line.lstrip().startswith("#")
        ),
        "",
    )

    if not subject:
        print("commit message subject is empty", file=sys.stderr)
        return 1

    if subject.startswith(("Merge ", "Revert ", "fixup! ", "squash! ")):
        return 0

    match = COMMIT_RE.match(subject)
    if not match or match.group("type") not in ALLOWED_TYPES:
        print(
            "commit message must follow Conventional Commits: type(scope): description",
            file=sys.stderr,
        )
        print(
            "allowed types: " + ", ".join(sorted(ALLOWED_TYPES)),
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
