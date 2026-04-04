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
- `MILVUS_URI`: reserved for later vectorization integration
- `MILVUS_COLLECTION`: reserved target collection name
- `EMBEDDING_BASE_URL`: embedding API base URL
- `EMBEDDING_MODEL`: embedding model name
- `EMBEDDING_API_KEY`: embedding API token

Create a local env file before running the backend:

```bash
cp .env.example .env
```

Legacy aliases remain supported for compatibility:

- `BASE_URL` -> `EMBEDDING_BASE_URL`
- `EMBEDDER` -> `EMBEDDING_MODEL`
- `ARK_API_KEY` -> `EMBEDDING_API_KEY`

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
