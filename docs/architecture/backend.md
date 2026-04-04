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

### `schemas/`

- API payloads and response models
- request validation for batch operations

### `services/documents/`

- upload orchestration
- file storage
- persistence write flow
- vector queue status updates
- soft delete behavior

### `services/loaders/`

- file extension to loader mapping
- loader-specific normalization rules
- common fragment result format

## Storage Model

### Relational metadata

- document-level record in `document_assets`
- fragment-level record in `document_fragments`

### File storage

- stored under `backend/uploads/`
- partitioned by `year/month/document_id`
- original source file retained for traceability

## Production Direction

- use `PostgreSQL` for metadata persistence
- use `Milvus` for vector storage after embeddings are added
- keep the current local SQLite fallback for bootstrap and testing only
