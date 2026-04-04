# Repository Map

## Top-Level Layout

```text
lawyer/
|- AGENTS.md
|- docs/
|- docker-compose.yml
|- frontend/
|- backend/
|- scripts/
|- Resource/
|- README.md
```

## Directory Guide

- `docs/`: project knowledge map and agent navigation entrypoint
- `frontend/`: Nuxt frontend for document upload and list management UI
- `backend/`: FastAPI backend for ingestion, metadata persistence, and loader orchestration
- `docker-compose.yml`: local PostgreSQL, Redis, and Milvus stack
- `scripts/`: repository automation, including hook installation and helper scripts
- `Resource/`: local sample/reference materials, not part of runtime ingestion flow

## Backend Map

```text
backend/
|- pyproject.toml
|- README.md
|- src/app/
|  |- api/
|  |- core/
|  |- db/
|  |- models/
|  |- schemas/
|  |- services/
|  |- main.py
|- tests/
|- uploads/
|- data/
```

### Backend Ownership

- `src/app/main.py`: app bootstrap, CORS, router mounting, DB initialization
- `src/app/api/routes/chat.py`: grounded answer generation API
- `src/app/api/routes/documents.py`: upload, list, delete, vectorize APIs
- `src/app/core/config.py`: environment-driven settings
- `src/app/db/`: engine, session, and declarative base
- `src/app/models/document.py`: relational persistence model for documents and fragments
- `src/app/schemas/document.py`: request/response contracts
- `src/app/schemas/answer.py`: chat answer request/response contracts
- `src/app/services/answers/`: answer generation and citation assembly
- `src/app/services/documents/`: document orchestration and upload storage
- `src/app/services/loaders/`: file-type-specific loader registry and normalization rules
- `src/app/services/vectors/`: chunking, embeddings, Milvus indexing, and retrieval
- `src/app/services/cache/`: Redis cache adapter used by vector retrieval
- `tests/`: API and health verification

## Frontend Map

```text
frontend/
|- package.json
|- nuxt.config.ts
|- app/
|  |- app.vue
|- public/
```

### Frontend Ownership

- `app/app.vue`: global shell, mobile top bar, and sidebar layout
- `app/pages/index.vue`: redirect entrypoint to the chat workspace
- `app/pages/chat.vue`: grounded Q&A page with citations
- `app/pages/documents.vue`: document upload and management page
- `app/stores/chat.ts`: answer request state and citation payload handling
- `app/components/AppSidebar.vue`: left navigation sidebar
- `nuxt.config.ts`: runtime config, including public API base
- `package.json`: `pnpm` scripts and frontend dependencies

## Where To Change Things

- Add a new document loader:
  - `backend/src/app/services/loaders/`
  - `docs/architecture/document-ingestion.md`
- Change upload/list/delete/vectorization behavior:
  - `backend/src/app/services/documents/service.py`
  - `backend/src/app/api/routes/documents.py`
- Change vector indexing or retrieval behavior:
  - `backend/src/app/services/vectors/`
  - `backend/src/app/api/routes/search.py`
- Change answer generation or citation behavior:
  - `backend/src/app/services/answers/`
  - `backend/src/app/api/routes/chat.py`
- Change metadata schema:
  - `backend/src/app/models/document.py`
  - `backend/src/app/schemas/document.py`
- Change upload page layout:
  - `frontend/app/pages/documents.vue`
- Change chat workspace layout:
  - `frontend/app/pages/chat.vue`
- Change sidebar layout:
  - `frontend/app/components/AppSidebar.vue`
- Change API base or client runtime behavior:
  - `frontend/nuxt.config.ts`

## Agent Note

If you are an AI agent, this file is your repo entry map. Use it to locate the subsystem first, then drill into the linked docs and source.
