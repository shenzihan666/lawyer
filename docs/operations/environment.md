# Environment Reference

## Backend Variables

### `DATABASE_URL`

- Purpose: metadata database connection string
- Required runtime target: PostgreSQL via `psycopg`

Example:

```bash
export DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5433/lawyer"
```

### `DATABASE_CONNECT_TIMEOUT_SECONDS`

- Purpose: single database connect timeout used during startup checks
- Default: `5`

### `DATABASE_STARTUP_MAX_ATTEMPTS`

- Purpose: number of startup retries before backend exits when database is unavailable
- Default: `3`

### `DATABASE_STARTUP_RETRY_DELAY_SECONDS`

- Purpose: delay between startup retry attempts
- Default: `2`

### `UPLOAD_ROOT_PATH`

- Purpose: upload file root
- Default: `uploads`
- Effective path: relative to `backend/` unless absolute path is provided

### `LOG_LEVEL`

- Purpose: backend root log level
- Default: `INFO`

### `LOG_ROOT_PATH`

- Purpose: structured log output directory
- Default: `logs`
- Effective path: relative to `backend/` unless absolute path is provided

### `LOG_RETENTION_DAYS`

- Purpose: number of daily rotated log files to retain
- Default: `30`

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

### `EMBEDDING_BASE_URL`

- Purpose: external embedding API base URL
- Google Gemini OpenAI-compatible example: `https://generativelanguage.googleapis.com/v1beta/openai`

Legacy alias:

- `BASE_URL`

### `EMBEDDING_MODEL`

- Purpose: embedding model name sent to the external embedding API
- Google Gemini example: `gemini-embedding-001`

Legacy alias:

- `EMBEDDER`

### `EMBEDDING_API_KEY`

- Purpose: bearer token for the external embedding API

Legacy alias:

- `ARK_API_KEY`

### `EMBEDDING_TIMEOUT_SECONDS`

- Purpose: timeout for the external embedding request
- Default: `30`

### `QUERY_REWRITE_ENABLED`

- Purpose: enable relevance grading and second-stage retrieval on top of vector search
- Default: `true`

### `QUERY_REWRITE_BASE_URL`

- Purpose: OpenAI-compatible chat completion base URL used for query rewriting
- Fallbacks: `LLM_BASE_URL`, `BASE_URL`, `EMBEDDING_BASE_URL`

### `QUERY_REWRITE_MODEL`

- Purpose: chat model used for relevance grading, step-back rewrite, and HyDE generation
- Fallbacks: `QUERY_MODEL`, `MODEL`

### `QUERY_REWRITE_API_KEY`

- Purpose: bearer token for the query rewrite model
- Fallbacks: `LLM_API_KEY`, `ARK_API_KEY`, `EMBEDDING_API_KEY`

### `QUERY_REWRITE_TIMEOUT_SECONDS`

- Purpose: timeout for the query rewrite API request
- Default: `30`

### `QUERY_REWRITE_MAX_CONTEXT_ITEMS`

- Purpose: number of first-pass retrieved chunks sent to the rewrite/grading model
- Default: `3`

### `QUERY_REWRITE_MAX_CONTENT_CHARS`

- Purpose: max characters kept per retrieved chunk when building rewrite context
- Default: `480`

### `ANSWER_GENERATION_ENABLED`

- Purpose: enable grounded answer generation on top of retrieved evidence
- Default: `true`

### `ANSWER_GENERATION_BASE_URL`

- Purpose: OpenAI-compatible chat completion base URL used for cited answer generation
- Fallbacks: `ANSWER_BASE_URL`, `CHAT_BASE_URL`, `QUERY_REWRITE_BASE_URL`, `LLM_BASE_URL`, `BASE_URL`, `EMBEDDING_BASE_URL`

### `ANSWER_GENERATION_MODEL`

- Purpose: chat model used for grounded legal answer generation
- Fallbacks: `ANSWER_MODEL`, `CHAT_MODEL`, `QUERY_REWRITE_MODEL`, `QUERY_MODEL`, `MODEL`

### `ANSWER_GENERATION_API_KEY`

- Purpose: bearer token for the answer generation model
- Fallbacks: `ANSWER_API_KEY`, `CHAT_API_KEY`, `QUERY_REWRITE_API_KEY`, `LLM_API_KEY`, `ARK_API_KEY`, `EMBEDDING_API_KEY`

### `ANSWER_GENERATION_TIMEOUT_SECONDS`

- Purpose: timeout for the answer generation API request
- Default: `45`

### `ANSWER_GENERATION_MAX_CONTEXT_ITEMS`

- Purpose: number of retrieved chunks forwarded to the answer model
- Default: `5`

### `ANSWER_GENERATION_MAX_CONTENT_CHARS`

- Purpose: max characters kept per retrieved chunk when building answer context
- Default: `700`

### `REDIS_URL`

- Purpose: Redis cache connection for chunk/search caching
- Default: `redis://127.0.0.1:6379/0`

### `REDIS_KEY_PREFIX`

- Purpose: namespace prefix for Redis keys
- Default: `lawyer`

### `VECTOR_DENSE_DIMENSION`

- Purpose: dense embedding dimension written to Milvus
- Default: `3072`

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

- backend reads local settings from `backend/.env`
- start from `backend/.env.example` and copy it to `backend/.env`
- backend writes structured JSON logs to `backend/logs/application.log` and `backend/logs/error.log`
- file logs rotate daily and retain the most recent `LOG_RETENTION_DAYS` archives
- local development can run without PostgreSQL or Milvus
- local vector search needs PostgreSQL, Redis, and Milvus available together
- second-stage retrieval needs a chat-capable model configured through `QUERY_REWRITE_*` or compatible fallback variables
- grounded answer generation needs an answer model configured through `ANSWER_GENERATION_*` or compatible fallback variables
- production should run PostgreSQL for metadata and chunk storage
- Redis should be treated as a cache layer, not the source of truth
