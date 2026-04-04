# Chat API

## Base Prefix

- `/api/v1/chat`

## Endpoints

### `POST /api/v1/chat/answer`

Request body:

```json
{
  "query": "房屋被他人占有时，我应该如何主张返还原物？",
  "top_k": 5,
  "document_ids": ["uuid-1"]
}
```

Behavior:

- runs the vector retrieval pipeline first, including optional query rewrite and second-stage retrieval
- sends the top retrieved chunks to an OpenAI-compatible chat model when answer generation is configured
- requires the generated answer to cite sources inline with `[1][2]` style references
- returns citation cards that map those numbers back to concrete chunk ids, filenames, pages, and snippets
- falls back to an extractive evidence summary when no answer model is configured

Response shape:

```json
{
  "answer": "可以先主张返还原物，并重点核查对方是否具有合法占有依据。[1][2]",
  "citations": [
    {
      "citation_number": 1,
      "chunk_id": "doc-1:l3:0",
      "original_filename": "案例一.pdf",
      "page_number": 8,
      "snippet": "返还原物请求权可适用于无权占有人。"
    }
  ],
  "meta": {
    "generation_mode": "llm",
    "grounding_status": "grounded",
    "search_meta": {}
  }
}
```
