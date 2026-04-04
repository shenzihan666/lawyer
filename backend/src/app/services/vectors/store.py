import json
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DocumentChunk
from app.services.cache import RedisCache
from app.services.vectors.chunking import ChunkRecord


class DocumentChunkStore:
    def __init__(self, db: Session, cache: RedisCache) -> None:
        self.db = db
        self.cache = cache

    @staticmethod
    def _cache_key(chunk_id: str) -> str:
        return f"document_chunk:{chunk_id}"

    @staticmethod
    def _search_cache_key(payload: dict) -> str:
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return f"search:{serialized}"

    @staticmethod
    def _bm25_stats_key() -> str:
        return "bm25:stats"

    def replace_document_chunks(
        self, document_id: str, chunks: Sequence[ChunkRecord]
    ) -> None:
        existing_ids = list(
            self.db.scalars(
                select(DocumentChunk.chunk_id).where(
                    DocumentChunk.document_id == document_id
                )
            )
        )
        self.db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        for chunk_id in existing_ids:
            self.cache.delete(self._cache_key(chunk_id))

        self.db.add_all(
            [
                DocumentChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    root_chunk_id=chunk.root_chunk_id,
                    parent_chunk_id=chunk.parent_chunk_id,
                    chunk_level=chunk.chunk_level,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    content=chunk.content,
                    chunk_metadata={
                        **chunk.metadata,
                        "original_filename": chunk.original_filename,
                    },
                )
                for chunk in chunks
            ]
        )

    def attach_dense_embeddings(
        self,
        document_id: str,
        embeddings_by_chunk_id: dict[str, list[float]],
    ) -> None:
        if not embeddings_by_chunk_id:
            return

        rows = list(
            self.db.scalars(
                select(DocumentChunk).where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.chunk_id.in_(list(embeddings_by_chunk_id.keys())),
                )
            )
        )
        for row in rows:
            row.chunk_metadata = {
                **row.chunk_metadata,
                "dense_embedding": embeddings_by_chunk_id[row.chunk_id],
            }
            self.cache.delete(self._cache_key(row.chunk_id))

    def get_chunks_by_ids(self, chunk_ids: Sequence[str]) -> list[dict]:
        if not chunk_ids:
            return []

        ordered: dict[str, dict] = {}
        missing_ids: list[str] = []
        for chunk_id in chunk_ids:
            cached = self.cache.get_json(self._cache_key(chunk_id))
            if cached:
                ordered[chunk_id] = cached
            else:
                missing_ids.append(chunk_id)

        if missing_ids:
            rows = list(
                self.db.scalars(
                    select(DocumentChunk).where(DocumentChunk.chunk_id.in_(missing_ids))
                )
            )
            for row in rows:
                payload = {
                    "chunk_id": row.chunk_id,
                    "document_id": row.document_id,
                    "root_chunk_id": row.root_chunk_id,
                    "parent_chunk_id": row.parent_chunk_id,
                    "chunk_level": row.chunk_level,
                    "chunk_index": row.chunk_index,
                    "page_number": row.page_number,
                    "content": row.content,
                    "original_filename": row.chunk_metadata.get(
                        "original_filename", ""
                    ),
                    "metadata": row.chunk_metadata,
                }
                ordered[row.chunk_id] = payload
                self.cache.set_json(self._cache_key(row.chunk_id), payload)

        return [ordered[chunk_id] for chunk_id in chunk_ids if chunk_id in ordered]

    def delete_document_chunks(self, document_ids: Sequence[str]) -> None:
        if not document_ids:
            return
        chunk_ids = list(
            self.db.scalars(
                select(DocumentChunk.chunk_id).where(
                    DocumentChunk.document_id.in_(document_ids)
                )
            )
        )
        self.db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id.in_(document_ids))
        )
        for chunk_id in chunk_ids:
            self.cache.delete(self._cache_key(chunk_id))

    def get_leaf_chunks_for_vector_index(self) -> list[dict]:
        rows = list(
            self.db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.chunk_level == 3)
                .order_by(
                    DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc()
                )
            )
        )
        items: list[dict] = []
        for row in rows:
            dense_embedding = row.chunk_metadata.get("dense_embedding")
            if not dense_embedding:
                continue
            items.append(
                {
                    "chunk_id": row.chunk_id,
                    "document_id": row.document_id,
                    "root_chunk_id": row.root_chunk_id,
                    "parent_chunk_id": row.parent_chunk_id,
                    "chunk_level": row.chunk_level,
                    "chunk_index": row.chunk_index,
                    "page_number": row.page_number,
                    "content": row.content,
                    "original_filename": row.chunk_metadata.get(
                        "original_filename", ""
                    ),
                    "dense_embedding": dense_embedding,
                    "metadata": row.chunk_metadata,
                }
            )
        return items

    def get_bm25_stats(self) -> dict | None:
        return self.cache.get_json(self._bm25_stats_key())

    def set_bm25_stats(self, stats: dict) -> None:
        self.cache.set_json(self._bm25_stats_key(), stats)

    def invalidate_bm25_stats(self) -> None:
        self.cache.delete(self._bm25_stats_key())

    def get_cached_search(self, payload: dict) -> dict | None:
        return self.cache.get_json(self._search_cache_key(payload))

    def set_cached_search(self, payload: dict, value: dict) -> None:
        self.cache.set_json(self._search_cache_key(payload), value)

    def invalidate_search_cache(self) -> None:
        self.cache.delete_pattern("search:*")
