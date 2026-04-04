# Environment Reference

## Backend Variables

### `DATABASE_URL`

- Purpose: metadata database connection string
- Required runtime target: PostgreSQL via `psycopg`

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

- Purpose: Milvus vector database endpoint used by indexing and retrieval

### `MILVUS_TOKEN`

- Purpose: future Milvus auth token

### `MILVUS_DATABASE`

- Purpose: future logical Milvus database name

### `MILVUS_COLLECTION`

- Purpose: collection target for document vectors

### `BASE_URL`

- Purpose: external embedding API base URL
- Example: `https://your-llm-endpoint/v1`

### `EMBEDDER`

- Purpose: embedding model name sent to the external embedding API

### `ARK_API_KEY`

- Purpose: bearer token for the external embedding API

### `EMBEDDING_TIMEOUT_SECONDS`

- Purpose: timeout for the external embedding request
- Default: `30`

### `REDIS_URL`

- Purpose: Redis cache connection for chunk/search caching
- Default: `redis://127.0.0.1:6379/0`

### `REDIS_KEY_PREFIX`

- Purpose: namespace prefix for Redis keys
- Default: `lawyer`

### `VECTOR_DENSE_DIMENSION`

- Purpose: dense embedding dimension written to Milvus
- Default: `2560`

### `VECTOR_SPARSE_DIMENSION`

- Purpose: local sparse vector space size for hybrid retrieval
- Default: `262144`

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
- local vector search needs PostgreSQL, Redis, and Milvus available together
- production should run PostgreSQL for metadata and chunk storage
- Redis should be treated as a cache layer, not the source of truth
