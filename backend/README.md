# Backend

FastAPI backend managed with `uv`.

## Run

```bash
uv sync
uv run backend
```

For development with auto-reload:

```bash
UVICORN_RELOAD=true uv run backend
```

The default server address is `http://127.0.0.1:8000`, and the health check endpoint is `/health`.
