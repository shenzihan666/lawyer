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
- does not yet generate embeddings

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
    "deleted": 0
  },
  "affected_ids": []
}
```

## Error Notes

- unsupported file types should return a `400`
- loader failures are preserved on the document record as `failure_reason`
