#!/usr/bin/env sh
set -eu

uv sync --directory backend --group dev
pnpm install --dir frontend
uv run --directory backend pre-commit install --config ../.pre-commit-config.yaml --install-hooks --hook-type pre-commit --hook-type pre-push --hook-type commit-msg
