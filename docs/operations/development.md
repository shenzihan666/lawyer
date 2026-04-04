# Development Guide

## Install

Frontend:

```bash
pnpm install --dir frontend
```

Backend:

```bash
uv sync --directory backend --group dev
```

## Run Locally

Backend:

```bash
uv run --directory backend backend
```

Backend with reload:

```bash
UVICORN_RELOAD=true uv run --directory backend backend
```

Frontend:

```bash
pnpm --dir frontend dev
```

## Verification Commands

Backend tests:

```bash
uv run --directory backend pytest
```

Frontend typecheck:

```bash
pnpm --dir frontend exec nuxi typecheck
```

Frontend build:

```bash
pnpm --dir frontend run build
```

Repository hooks:

```bash
./scripts/install-hooks.sh
backend/.venv/bin/pre-commit run --all-files -c .pre-commit-config.yaml
backend/.venv/bin/pre-commit run --hook-stage pre-push --all-files -c .pre-commit-config.yaml
```

## Local Defaults

- backend will use local SQLite if `DATABASE_URL` is unset
- uploads default to `backend/uploads/`
- API default expected by frontend is `http://127.0.0.1:8000/api/v1`
