# Backend

FastAPI backend for the Lawyer RAG project.

## Supported Loaders

- `PDF` / `.pdf`: `PyPDFLoader`, one raw document per page
- `Word` / `.docx`, `.doc`: `Docx2txtLoader`, one raw document for the full file
- `Excel` / `.xlsx`, `.xls`: `UnstructuredExcelLoader`, normalized to `page_number = 0`

The backend stores uploaded files under `backend/uploads/` and keeps traceable metadata in the relational database.

## Environment

Important variables:

- `DATABASE_URL`: metadata database, production should point to PostgreSQL
- `DATABASE_CONNECT_TIMEOUT_SECONDS`: single database connection timeout during startup, defaults to `5`
- `DATABASE_STARTUP_MAX_ATTEMPTS`: startup retry count for database readiness, defaults to `3`
- `DATABASE_STARTUP_RETRY_DELAY_SECONDS`: delay between database startup retries, defaults to `2`
- `UPLOAD_ROOT_PATH`: upload directory, defaults to `uploads`
- `FRONTEND_ORIGINS`: comma-separated allowed origins
- `LOG_LEVEL`: root log level, defaults to `INFO`
- `LOG_ROOT_PATH`: log directory, defaults to `logs`
- `LOG_RETENTION_DAYS`: daily log retention count, defaults to `30`
- `MILVUS_URI`: Milvus vector database endpoint
- `MILVUS_COLLECTION`: target collection name
- `EMBEDDING_BASE_URL`: embedding API base URL
- `EMBEDDING_MODEL`: embedding model name
- `EMBEDDING_API_KEY`: embedding API token
- `QUERY_REWRITE_ENABLED`: enable relevance grading and second-stage retrieval
- `QUERY_REWRITE_BASE_URL`: OpenAI-compatible chat API base URL for query rewriting
- `QUERY_REWRITE_MODEL`: chat model used for relevance grading, step-back rewriting, and HyDE
- `QUERY_REWRITE_API_KEY`: API token for the rewrite model
- `RERANK_BASE_URL`: dedicated rerank API base URL, if available
- `RERANK_MODEL`: rerank model name for the dedicated rerank API
- `RERANK_API_KEY`: API token for rerank requests
- `ANSWER_GENERATION_BASE_URL`: OpenAI-compatible chat API base URL for grounded answer generation
- `ANSWER_GENERATION_MODEL`: chat model used for cited answer generation
- `ANSWER_GENERATION_API_KEY`: API token for the answer model

Create a local env file before running the backend:

```bash
cp .env.example .env
```

Legacy aliases remain supported for compatibility:

- `BASE_URL` -> `EMBEDDING_BASE_URL`
- `EMBEDDER` -> `EMBEDDING_MODEL`
- `ARK_API_KEY` -> `EMBEDDING_API_KEY`
- `BASE_URL` / `ARK_API_KEY` / `MODEL` can also be reused by query rewrite if dedicated rewrite variables are not set
- answer/query rewrite model settings can be reused by rerank when no dedicated rerank endpoint is configured
- `QUERY_REWRITE_*` can also be reused by answer generation if dedicated answer variables are not set

The backend writes structured JSON logs to `backend/logs/` with daily rotation:

- `application.log`
- `error.log`

## Run

```bash
uv sync --group dev
uv run backend
```

For development with auto-reload:

```bash
UVICORN_RELOAD=true uv run backend
```

The default server address is `http://127.0.0.1:8000`, and the health check endpoint is `/health`.
