# Document Ingestion Architecture

## Goal

Normalize different office document formats into a common raw fragment model that can later feed chunking and vectorization.

## Supported Loaders

| Format | Extensions | Loader | Normalization Rule |
| --- | --- | --- | --- |
| PDF | `.pdf` | `PyPDFLoader` | one fragment per page, `page_number` is meaningful |
| Word | `.docx`, `.doc` | `Docx2txtLoader` | full document as one fragment, `page_number = 0` |
| Excel | `.xlsx`, `.xls` | `UnstructuredExcelLoader` | extracted cell/table text, normalized to `page_number = 0` |

## Normalized Output Model

Each extracted fragment is normalized into:

- `fragment_index`
- `page_number`
- `content`
- `metadata`

This lets later stages avoid loader-specific branches.

## Traceability Rules

For every uploaded file, the system stores:

- generated document ID
- original filename
- stored filename
- storage path
- extension and MIME type
- SHA256 digest
- file size
- loader name
- ingestion status
- vector status
- timestamps
- soft delete timestamp when removed

## File Storage Convention

Files are stored under:

```text
backend/uploads/<year>/<month>/<document_id>/source.<ext>
```

This structure is chosen so the original source file remains auditable and can be reprocessed later.

## Current Service Flow

1. Validate filename and supported extension.
2. Save source file to upload storage.
3. Create document metadata record.
4. Run loader selected by extension.
5. Normalize fragments.
6. Persist fragments to relational DB.
7. On vectorization, expand fragments into hierarchical retrieval chunks.
8. Store all chunk metadata in relational DB and cache hot entries in Redis.
9. Rebuild BM25 corpus statistics from leaf chunks for sparse retrieval.
10. Embed leaf chunks and write dense+sparse vectors to Milvus.
11. Return updated list and summary to frontend.

## Vectorization Status

Current statuses:

- `not_requested`
- `queued`
- `indexing`
- `indexed`
- `failed`

Leaf chunks are written to Milvus, while parent/root chunks remain in PostgreSQL for later auto-merge style recall.
