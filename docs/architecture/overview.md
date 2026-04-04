# Architecture Overview

## Monorepo Shape

This project is a two-application monorepo:

- `frontend/`: user-facing document management interface
- `backend/`: ingestion and metadata service for the RAG workflow

## Core Technology Choices

- Frontend package manager: `pnpm`
- Frontend framework: `Nuxt 4`
- UI runtime: `Vue 3`
- Backend package/runtime manager: `uv`
- Backend framework: `FastAPI`
- ORM: `SQLAlchemy`
- Config management: `pydantic-settings`
- Production metadata store target: `PostgreSQL`
- Local bootstrap metadata store: `SQLite`
- Vector store target: `Milvus`

## Current Product Scope

Implemented now:

- single and batch document upload
- document list view
- single and batch soft delete
- single and batch vectorization queue marking
- traceable file storage under `backend/uploads/`
- raw document extraction into structured fragments

Reserved for later:

- actual vector embedding generation
- Milvus collection writes
- retrieval and answer generation pipeline

## System Flow

```text
Frontend upload UI
    -> FastAPI document API
    -> upload storage writes source file
    -> loader registry selects loader by extension
    -> extracted raw fragments stored in relational DB
    -> document status returned to frontend
    -> optional vectorization queue status set for later Milvus integration
```

## Design Principles

- modular backend packages instead of a single flat file
- traceable ingestion with file path, hash, timestamps, and soft delete state
- local development should work without production infra
- production direction should align with PostgreSQL + Milvus
- docs should help AI agents discover the right code area quickly
