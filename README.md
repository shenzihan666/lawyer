# Lawyer

This repository is a small monorepo with:

- `frontend/`: Nuxt 4 + Vue 3
- `backend/`: FastAPI managed with `uv`

## Tooling

- Frontend language: TypeScript / Vue
- Backend language: Python 3.13
- Frontend formatter: Prettier
- Backend lint/format: Ruff
- Backend tests: Pytest
- Frontend type checking: `nuxi typecheck`
- Git hooks: `pre-commit`

## Install

Install project dependencies:

```bash
pnpm install --dir frontend
uv sync --directory backend --group dev
```

Install Git hooks with one command:

```bash
./scripts/install-hooks.sh
```

## Git Hooks

The repository uses `pre-commit` with three local hook stages:

- `pre-commit`: fast staged-file checks only
  - generic file hygiene checks
  - `ruff format` and `ruff check --fix` for Python files
  - `prettier --write` for staged frontend files
- `pre-push`: full project verification
  - backend tests with `pytest`
  - frontend type checking with `nuxi typecheck`
  - frontend production build
- `commit-msg`: Conventional Commits enforcement
  - format: `type(scope): description`
  - allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`, `revert`

Hooks are meant for local development and are not part of CI by default. If you need to bypass them for an exceptional case, use Git's `--no-verify` escape hatch.

## Manual Commands

Run the same checks manually without Git hooks:

```bash
pnpm --dir frontend exec nuxi typecheck
pnpm --dir frontend run build
uv run --directory backend pytest
uv run --directory backend ruff check backend/tests backend/src
uv run --directory backend ruff format --check backend/tests backend/src
```
