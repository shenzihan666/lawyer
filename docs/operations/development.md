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

Backend env file:

```bash
cd backend
cp .env.example .env
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

Infrastructure stack:

```bash
docker compose up -d postgres redis etcd minio standalone attu
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

Targeted opponent analysis tests:

```bash
uv run --directory backend pytest tests/test_opponent_analysis_api.py
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

- backend expects PostgreSQL in `DATABASE_URL`
- uploads default to `backend/uploads/`
- structured logs default to `backend/logs/`
- API default expected by frontend is `http://127.0.0.1:8000/api/v1`
- vector retrieval defaults expect Redis on `6379` and Milvus on `19530`
- Attu UI is exposed at `http://127.0.0.1:8080`
