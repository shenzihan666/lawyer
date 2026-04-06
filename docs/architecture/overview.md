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
- Vector store target: `Milvus`

## Current Product Scope

Implemented now:

- single and batch document upload
- document list view
- single and batch soft delete
- single and batch document vectorization
- traceable file storage under `backend/uploads/`
- raw document extraction into structured fragments
- hierarchical chunk persistence in PostgreSQL
- Milvus-based hybrid retrieval with Redis cache support
- post-retrieval rerank with dedicated endpoint or chat-model fallback
- single-turn grounded answer generation with inline citations
- persisted multi-agent opponent prediction runs with event replay and SSE updates

## System Flow

```text
Frontend upload UI
    -> FastAPI document API
    -> upload storage writes source file
    -> loader registry selects loader by extension
    -> extracted raw fragments stored in relational DB
    -> vectorization expands fragments into retrieval chunks
    -> parent/root chunks stored in PostgreSQL and cached in Redis
    -> leaf chunks embedded through external API and written to Milvus
    -> search retrieves grounded evidence
    -> chat answer endpoint generates cited answer from retrieved chunks
    -> opponent analysis orchestrator builds shared context, agent handoff events, and board summary
    -> document status and answer payload returned to frontend
```

## Design Principles

- modular backend packages instead of a single flat file
- traceable ingestion with file path, hash, timestamps, and soft delete state
- local development should work without production infra
- production direction should align with PostgreSQL + Milvus
- docs should help AI agents discover the right code area quickly
