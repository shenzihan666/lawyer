#!/usr/bin/env sh
set -eu

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD=python
else
  echo "Python 3 is required to install hooks." >&2
  exit 1
fi

exec "$PYTHON_CMD" scripts/install-hooks.py
