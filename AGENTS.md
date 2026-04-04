# Agent Guide

This repository includes a dedicated documentation map for both humans and AI agents.

## Docs Location

- Relative path: `docs/`
- Absolute path: `/Users/defender/Project/lawyer/docs`

## Project Stack

- Frontend package manager: `pnpm`
- Frontend framework: `Nuxt 4` + `Vue 3` + `TypeScript`
- Backend package/runtime manager: `uv`
- Backend framework: `FastAPI`
- Backend language: `Python 3.13`
- ORM / metadata persistence: `SQLAlchemy`
- Primary production metadata database target: `PostgreSQL`
- Vector database target: `Milvus`
- Document loading layer: `langchain-community` loaders

## Agent Reading Order

When you need project context, read in this order:

1. `docs/README.md`
2. `docs/maps/repository-map.md`
3. `docs/architecture/overview.md`
4. `docs/architecture/document-ingestion.md`
5. `docs/api/documents.md`
6. `docs/operations/development.md`
7. Source files referenced by those documents

## Navigation Rules

- Treat `docs/` as the repository map and discovery entrypoint.
- Use the docs to find the correct subsystem first, then verify details in code.
- Prefer the backend module root `backend/src/app/` for backend changes.
- Prefer `frontend/` for UI and client-side integration work.
- For document ingestion work, start with:
  - `docs/architecture/document-ingestion.md`
  - `backend/src/app/services/loaders/`
  - `backend/src/app/services/documents/service.py`
  - `backend/src/app/api/routes/documents.py`

## Notes

- `docs/` is intended to help AI agents find relevant content quickly.
- Documentation is a map, not a substitute for source verification.
- If docs and code diverge, treat code as the final runtime truth and update docs accordingly.
