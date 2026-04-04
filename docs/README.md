# Docs Portal

This folder is the project knowledge map for the `lawyer` repository.

## Purpose

- give engineers and AI agents a stable starting point
- describe the current monorepo architecture
- point to the right code areas before implementation work starts
- reduce open-ended searching across the repository

## Quick Start

Read in this order:

1. `maps/repository-map.md`
2. `architecture/overview.md`
3. `architecture/document-ingestion.md`
4. `api/documents.md`
5. `operations/development.md`
6. `operations/environment.md`

## Current Stack

- Frontend: `Nuxt 4`, `Vue 3`, `TypeScript`, `pnpm`
- Backend: `FastAPI`, `Python 3.13`, `uv`
- Persistence: `SQLAlchemy`, local `SQLite` fallback, production `PostgreSQL`
- Vector target: `Milvus`
- Loaders: `PyPDFLoader`, `Docx2txtLoader`, `UnstructuredExcelLoader`

## Documents Index

- `maps/repository-map.md`: repository-level navigation map
- `architecture/overview.md`: system-level architecture summary
- `architecture/backend.md`: backend module design and file ownership
- `architecture/frontend.md`: frontend structure and UI integration notes
- `architecture/document-ingestion.md`: document loading semantics and storage flow
- `api/documents.md`: document API contract summary
- `operations/development.md`: install, run, test, and verification commands
- `operations/environment.md`: environment variables and deployment-oriented settings

## Source Of Truth Order

Use this precedence when working:

1. Runtime code
2. Tests
3. Documentation in this folder

The docs are intentionally written as a navigation map, so agents should use them to find code faster, then confirm behavior in source.
