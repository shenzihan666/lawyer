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
- `UPLOAD_ROOT_PATH`: upload directory, defaults to `uploads`
- `FRONTEND_ORIGINS`: comma-separated allowed origins
- `MILVUS_URI`: reserved for later vectorization integration
- `MILVUS_COLLECTION`: reserved target collection name

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
