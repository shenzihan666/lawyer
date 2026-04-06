# Backend Architecture

## Entry Point

- Main bootstrap: `backend/src/app/main.py`

Responsibilities:

- create FastAPI application
- initialize upload and data directories
- create DB tables at startup
- attach CORS middleware
- register versioned API router

## Module Layout

```text
src/app/
|- api/
|- core/
|- db/
|- models/
|- schemas/
|- services/
|- main.py
```

## Layer Responsibilities

### `api/`

- HTTP route definitions
- request binding
- dependency injection for services

### `core/`

- runtime settings
- environment variable parsing
- backend root, data root, upload root helpers

### `db/`

- SQLAlchemy base
- engine construction
- session factory

### `models/`

- `DocumentAsset`: source file metadata and ingestion state
- `DocumentFragment`: extracted raw document fragments
- `OpponentAnalysisRun`: persisted multi-agent prediction run metadata
- `OpponentAnalysisEvent`: structured per-step event log for replay and SSE

### `schemas/`

- API payloads and response models
- request validation for batch operations

### `services/documents/`

- upload orchestration
- file storage
- persistence write flow
- vector indexing trigger and cleanup coordination
- soft delete behavior

### `services/loaders/`

- file extension to loader mapping
- loader-specific normalization rules
- common fragment result format

### `services/vectors/`

- hierarchical chunk generation from normalized fragments
- external dense embedding generation plus BM25-style sparse vector generation
- Milvus collection lifecycle and hybrid search
- PostgreSQL chunk store for parent-context recall
- Redis-backed cache for search responses and chunk lookups

### `services/opponent_analysis/`

- fixed-phase workflow orchestration for courtroom rehearsal
- shared context brief built from vector retrieval
- multi-agent handoff between opponent party, opponent counsel, bench observer, and strategy advisor
- structured event persistence for board playback
- background execution plus SSE stream snapshots

## Storage Model

### Relational metadata

- document-level record in `document_assets`
- fragment-level record in `document_fragments`
- hierarchical retrieval chunks in `document_chunks`

### File storage

- stored under `backend/uploads/`
- partitioned by `year/month/document_id`
- original source file retained for traceability

## Production Direction

- use `PostgreSQL` for metadata persistence and chunk storage
- use `Redis` for hot chunk and search cache
- use `Milvus` for leaf-chunk vector storage and retrieval
