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

## RAG Document Ingestion

Current scope:

- upload single or multiple documents
- keep a document list with batch select, batch delete, and batch vectorization queueing
- store source files in `backend/uploads/`
- persist document metadata and raw extracted text in the relational database
- reserve Milvus connection settings for the later vector stage

Supported formats:

- `PDF`: `PyPDFLoader`, split into one raw document per page
- `Word`: `Docx2txtLoader`, full text as one raw document with `page_number = 0`
- `Excel`: `UnstructuredExcelLoader`, normalized to `page_number = 0`

Recommended backend environment variables:

```bash
export DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/lawyer"
export MILVUS_URI="http://127.0.0.1:19530"
```

The backend expects PostgreSQL to be available through `DATABASE_URL`.

Run the app locally:

```bash
uv run --directory backend backend
pnpm --dir frontend dev
```

Install project dependencies and Git hooks with one command:

```bash
python scripts/install-hooks.py
```

## Git Hooks

The repository uses `pre-commit` with three local hook stages:

- `pre-commit`: fast staged-file checks only
  - generic file hygiene checks
  - `ruff format` and `ruff check --fix` for Python files
  - `prettier --write` for staged frontend files
  - block staged frontend `console.log` and `debugger` statements
  - run frontend type checking when staged `ts` or `vue` files change
- `pre-push`: full project verification
  - backend tests with `pytest`
  - frontend type checking with `nuxi typecheck`
  - frontend production build
- `commit-msg`: Conventional Commits enforcement
  - format: `type(scope): description`
  - allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`, `revert`

Hooks are meant for local development. `scripts/install-hooks.py` skips Git hook installation when `CI` is set, and the local hook wrappers also no-op in CI if they are invoked there. If you need to bypass hooks for an exceptional case, use Git's `--no-verify` escape hatch.

## Manual Commands

Run the same checks manually without Git hooks:

```bash
uv run --directory backend pre-commit run --all-files --config ../.pre-commit-config.yaml
uv run --directory backend pre-commit run --hook-stage pre-push --all-files --config ../.pre-commit-config.yaml
pnpm --dir frontend exec nuxi typecheck
pnpm --dir frontend run build
uv run --directory backend pytest
uv run --directory backend ruff check backend/tests backend/src
uv run --directory backend ruff format --check backend/tests backend/src
```
