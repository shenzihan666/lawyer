# Environment Reference

## Backend Variables

### `DATABASE_URL`

- Purpose: metadata database connection string
- Local default: `sqlite+pysqlite:///./data/lawyer.db`
- Production target: PostgreSQL via `psycopg`

Example:

```bash
export DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/lawyer"
```

### `UPLOAD_ROOT_PATH`

- Purpose: upload file root
- Default: `uploads`
- Effective path: relative to `backend/` unless absolute path is provided

### `FRONTEND_ORIGINS`

- Purpose: CORS allowlist
- Format: comma-separated string

Example:

```bash
export FRONTEND_ORIGINS="http://127.0.0.1:3000,http://localhost:3000"
```

### `MILVUS_URI`

- Purpose: future vector database endpoint
- Current status: reserved, not actively used for embedding writes yet

### `MILVUS_TOKEN`

- Purpose: future Milvus auth token

### `MILVUS_DATABASE`

- Purpose: future logical Milvus database name

### `MILVUS_COLLECTION`

- Purpose: future collection target for document vectors

## Frontend Variables

### `NUXT_PUBLIC_API_BASE`

- Purpose: public backend API base URL
- Default runtime config value: `http://127.0.0.1:8000/api/v1`

Example:

```bash
export NUXT_PUBLIC_API_BASE="http://127.0.0.1:8000/api/v1"
```

## Operational Guidance

- local development can run without PostgreSQL or Milvus
- production should move metadata to PostgreSQL
- Milvus settings should be treated as reserved integration points for the next phase
