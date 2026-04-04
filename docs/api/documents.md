# Documents API

## Base Prefix

- `/api/v1/documents`

## Endpoints

### `GET /api/v1/documents`

Returns:

- active document list
- aggregated summary counts

### `POST /api/v1/documents/upload`

Content type:

- `multipart/form-data`

Field:

- `files`: repeated file field for single or batch upload

Behavior:

- stores file under `backend/uploads/`
- runs file-type-specific loader
- persists document and fragment metadata

### `POST /api/v1/documents/vectorize`

Request body:

```json
{
  "document_ids": ["uuid-1", "uuid-2"]
}
```

Behavior:

- marks ready documents as `queued`
- generates hierarchical chunks from normalized fragments
- writes chunk metadata to PostgreSQL
- rebuilds BM25 corpus stats for sparse retrieval
- writes leaf vectors to Milvus
- updates document `vector_status` to `indexed` or `failed`

### `POST /api/v1/search`

Request body:

```json
{
  "query": "违约责任怎么认定",
  "top_k": 5,
  "document_ids": ["uuid-1"]
}
```

Behavior:

- executes hybrid retrieval in Milvus using external dense embeddings plus local sparse vectors
- can filter by selected document IDs
- auto-merges child hits to parent chunks when enough siblings are recalled
- serves hot results through Redis cache when available

### `POST /api/v1/documents/delete`

Request body:

```json
{
  "document_ids": ["uuid-1", "uuid-2"]
}
```

Behavior:

- soft deletes documents
- preserves traceability in the database

### `DELETE /api/v1/documents/{document_id}`

Behavior:

- soft deletes a single document

## Response Shape

Most document endpoints return:

```json
{
  "items": [],
  "summary": {
    "total": 0,
    "ready": 0,
    "failed": 0,
    "vector_queued": 0,
    "vector_indexed": 0,
    "vector_failed": 0,
    "deleted": 0
  },
  "affected_ids": []
}
```

## Error Notes

- unsupported file types should return a `400`
- loader failures are preserved on the document record as `failure_reason`
