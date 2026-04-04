from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models import DocumentAsset, DocumentIngestionStatus, DocumentVectorStatus
from app.schemas.search import SearchResponse, SearchResultItem
from app.services.cache import RedisCache
from app.services.vectors.chunking import ChunkRecord, build_document_chunks
from app.services.vectors.embeddings import (
    BM25SparseEmbeddingService,
    ExternalEmbeddingService,
)
from app.services.vectors.milvus import MilvusVectorIndex
from app.services.vectors.store import DocumentChunkStore

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentVectorService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.cache = RedisCache(settings)
        self.chunk_store = DocumentChunkStore(db=db, cache=self.cache)
        self.dense_embedding_service = ExternalEmbeddingService(settings)
        self.sparse_embedding_service = BM25SparseEmbeddingService(settings)
        self.milvus = MilvusVectorIndex(settings)

    def index_documents(self, document_ids: Sequence[str]) -> list[str]:
        logger.info(
            "Indexing documents",
            extra={
                "event": "vector_indexing_started",
                "requested_count": len(document_ids),
            },
        )
        documents = list(
            self.db.scalars(
                select(DocumentAsset)
                .options(selectinload(DocumentAsset.fragments))
                .where(DocumentAsset.id.in_(document_ids))
            )
        )
        affected_ids: list[str] = []

        for document in documents:
            if document.deleted_at is not None:
                continue
            if document.ingestion_status != DocumentIngestionStatus.ready.value:
                continue

            document.vector_status = DocumentVectorStatus.indexing.value
            document.updated_at = utcnow()
            self.db.commit()
            logger.info(
                "Document indexing started",
                extra={
                    "event": "document_indexing_started",
                    "document_id": document.id,
                    "original_filename": document.original_filename,
                },
            )

            try:
                chunks = build_document_chunks(document, self.settings)
                if not chunks:
                    raise RuntimeError("No chunks were generated for this document")

                self.chunk_store.replace_document_chunks(document.id, chunks)
                leaf_chunks = [chunk for chunk in chunks if chunk.chunk_level == 3]
                dense_embeddings = self.dense_embedding_service.embed_texts(
                    [chunk.content for chunk in leaf_chunks]
                )
                attached_count = self.chunk_store.attach_dense_embeddings(
                    document.id,
                    {
                        chunk.chunk_id: embedding
                        for chunk, embedding in zip(
                            leaf_chunks,
                            dense_embeddings,
                            strict=True,
                        )
                    },
                )
                if attached_count != len(leaf_chunks):
                    raise RuntimeError(
                        "Dense embeddings were not attached to all leaf chunks"
                    )

                cleaned_trace_metadata = {
                    key: value
                    for key, value in (document.trace_metadata or {}).items()
                    if key != "vector_error"
                }

                document.vector_status = DocumentVectorStatus.indexed.value
                document.trace_metadata = {
                    **cleaned_trace_metadata,
                    "vector_indexed_at": utcnow().isoformat(),
                    "vector_chunk_counts": {
                        "total": len(chunks),
                        "leaf": len(leaf_chunks),
                        "parent": len(chunks) - len(leaf_chunks),
                    },
                }
                affected_ids.append(document.id)
                logger.info(
                    "Document indexed",
                    extra={
                        "event": "document_indexed",
                        "document_id": document.id,
                        "original_filename": document.original_filename,
                        "chunk_count": len(chunks),
                        "leaf_chunk_count": len(leaf_chunks),
                    },
                )
            except Exception as exc:
                document.vector_status = DocumentVectorStatus.failed.value
                document.trace_metadata = {
                    **document.trace_metadata,
                    "vector_error": str(exc),
                }
                logger.exception(
                    "Document indexing failed",
                    extra={
                        "event": "document_indexing_failed",
                        "document_id": document.id,
                        "original_filename": document.original_filename,
                    },
                )

            document.updated_at = utcnow()
            self.chunk_store.invalidate_search_cache()
            self.db.commit()
            self.db.refresh(document)

        if affected_ids:
            try:
                self._rebuild_vector_index()
            except Exception as exc:
                logger.exception(
                    "Vector index rebuild failed",
                    extra={
                        "event": "vector_rebuild_failed",
                        "document_count": len(affected_ids),
                    },
                )
                failed_documents = list(
                    self.db.scalars(
                        select(DocumentAsset).where(DocumentAsset.id.in_(affected_ids))
                    )
                )
                for document in failed_documents:
                    document.vector_status = DocumentVectorStatus.failed.value
                    document.updated_at = utcnow()
                    document.trace_metadata = {
                        **document.trace_metadata,
                        "vector_error": str(exc),
                    }
                self.db.commit()
                return []

        logger.info(
            "Indexing finished",
            extra={
                "event": "vector_indexing_finished",
                "indexed_count": len(affected_ids),
            },
        )
        return affected_ids

    def delete_document_vectors(self, document_ids: Sequence[str]) -> None:
        document_id_list = [document_id for document_id in document_ids if document_id]
        if not document_id_list:
            return

        logger.info(
            "Deleting document vectors",
            extra={
                "event": "vector_delete_started",
                "document_count": len(document_id_list),
            },
        )
        self.chunk_store.delete_document_chunks(document_id_list)
        self.chunk_store.invalidate_search_cache()
        self.chunk_store.invalidate_bm25_stats()
        try:
            self._rebuild_vector_index()
        except Exception:
            logger.exception(
                "Vector index rebuild failed after delete",
                extra={
                    "event": "vector_delete_rebuild_failed",
                    "document_count": len(document_id_list),
                },
            )
            return
        logger.info(
            "Document vectors deleted",
            extra={
                "event": "vector_delete_finished",
                "document_count": len(document_id_list),
            },
        )

    def search(
        self,
        query: str,
        top_k: int | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> SearchResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query must not be empty.",
            )

        effective_top_k = top_k or self.settings.vector_search_top_k
        selected_document_ids = sorted({item for item in (document_ids or []) if item})
        cache_payload = {
            "query": normalized_query,
            "top_k": effective_top_k,
            "document_ids": selected_document_ids,
        }
        cached = self.chunk_store.get_cached_search(cache_payload)
        if cached is not None:
            logger.info(
                "Search served from cache",
                extra={
                    "event": "vector_search_cache_hit",
                    "query_length": len(normalized_query),
                    "top_k": effective_top_k,
                    "document_filter_count": len(selected_document_ids),
                },
            )
            return SearchResponse.model_validate(cached)

        corpus_stats = self.chunk_store.get_bm25_stats()
        if corpus_stats is None:
            corpus_stats = self._build_and_cache_bm25_stats()

        dense_embedding = self.dense_embedding_service.embed_text(normalized_query)
        sparse_embedding = self.sparse_embedding_service.sparse_embed_text(
            normalized_query,
            corpus_stats,
        )
        try:
            retrieved, retrieval_mode = self.milvus.search(
                dense_embedding=dense_embedding,
                sparse_embedding=sparse_embedding,
                top_k=max(effective_top_k * 3, effective_top_k),
                document_ids=selected_document_ids,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Vector search is unavailable: {exc}",
            ) from exc
        merged, merge_meta = self._auto_merge_documents(retrieved, effective_top_k)
        response = SearchResponse(
            items=[
                SearchResultItem(
                    chunk_id=item["chunk_id"],
                    document_id=item["document_id"],
                    root_chunk_id=item["root_chunk_id"],
                    parent_chunk_id=item.get("parent_chunk_id"),
                    chunk_level=item["chunk_level"],
                    chunk_index=item["chunk_index"],
                    page_number=item.get("page_number", 0),
                    content=item["content"],
                    original_filename=item.get("original_filename", ""),
                    score=float(item.get("score", 0.0)),
                    metadata=item.get("metadata", {}),
                )
                for item in merged
            ],
            meta={
                "retrieval_mode": retrieval_mode,
                "candidate_k": max(effective_top_k * 3, effective_top_k),
                **merge_meta,
            },
        )
        self.chunk_store.set_cached_search(cache_payload, response.model_dump())
        logger.info(
            "Search completed",
            extra={
                "event": "vector_search_completed",
                "query_length": len(normalized_query),
                "top_k": effective_top_k,
                "document_filter_count": len(selected_document_ids),
                "result_count": len(response.items),
                "retrieval_mode": retrieval_mode,
            },
        )
        return response

    def _auto_merge_documents(
        self,
        docs: list[dict[str, Any]],
        top_k: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not docs:
            return [], {
                "auto_merge_enabled": True,
                "auto_merge_applied": False,
                "auto_merge_replaced_chunks": 0,
                "auto_merge_steps": 0,
                "auto_merge_threshold": self.settings.vector_auto_merge_threshold,
            }

        merged_docs = docs
        replaced_total = 0
        steps = 0
        for _ in range(2):
            merged_docs, replaced = self._merge_to_parent_level(merged_docs)
            if replaced == 0:
                continue
            replaced_total += replaced
            steps += 1

        merged_docs.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in merged_docs:
            chunk_id = item["chunk_id"]
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            deduped.append(item)

        return deduped[:top_k], {
            "auto_merge_enabled": True,
            "auto_merge_applied": replaced_total > 0,
            "auto_merge_replaced_chunks": replaced_total,
            "auto_merge_steps": steps,
            "auto_merge_threshold": self.settings.vector_auto_merge_threshold,
        }

    def _merge_to_parent_level(
        self,
        docs: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for doc in docs:
            parent_chunk_id = (doc.get("parent_chunk_id") or "").strip()
            if parent_chunk_id:
                groups[parent_chunk_id].append(doc)

        merge_ids = [
            parent_chunk_id
            for parent_chunk_id, items in groups.items()
            if len(items) >= self.settings.vector_auto_merge_threshold
        ]
        if not merge_ids:
            return docs, 0

        parent_docs = self.chunk_store.get_chunks_by_ids(merge_ids)
        parent_map = {item["chunk_id"]: item for item in parent_docs}

        merged_docs: list[dict[str, Any]] = []
        replaced = 0
        for doc in docs:
            parent_chunk_id = (doc.get("parent_chunk_id") or "").strip()
            if not parent_chunk_id or parent_chunk_id not in parent_map:
                merged_docs.append(doc)
                continue

            parent_doc = dict(parent_map[parent_chunk_id])
            parent_doc["score"] = max(
                float(parent_doc.get("score", 0.0)),
                float(doc.get("score", 0.0)),
            )
            parent_doc["metadata"] = {
                **parent_doc.get("metadata", {}),
                "merged_child_count": len(groups[parent_chunk_id]),
            }
            merged_docs.append(parent_doc)
            replaced += 1

        return merged_docs, replaced

    def _build_and_cache_bm25_stats(self) -> dict:
        leaf_chunks = self.chunk_store.get_leaf_chunks_for_vector_index()
        stats = self.sparse_embedding_service.build_corpus_stats(
            [chunk["content"] for chunk in leaf_chunks]
        )
        self.chunk_store.set_bm25_stats(stats)
        return stats

    def _rebuild_vector_index(self) -> None:
        leaf_rows = self.chunk_store.get_leaf_chunks_for_vector_index()
        self.chunk_store.invalidate_bm25_stats()
        corpus_stats = self._build_and_cache_bm25_stats()

        leaf_chunks = [self._chunk_record_from_row(row) for row in leaf_rows]
        dense_embeddings = [row["dense_embedding"] for row in leaf_rows]
        sparse_embeddings = self.sparse_embedding_service.sparse_embed_texts(
            [row["content"] for row in leaf_rows],
            corpus_stats,
        )
        self.milvus.replace_leaf_chunks(
            chunks=leaf_chunks,
            dense_embeddings=dense_embeddings,
            sparse_embeddings=sparse_embeddings,
        )
        logger.info(
            "Vector index rebuilt",
            extra={
                "event": "vector_index_rebuilt",
                "leaf_chunk_count": len(leaf_chunks),
            },
        )

    @staticmethod
    def _chunk_record_from_row(row: dict[str, Any]) -> ChunkRecord:
        return ChunkRecord(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            root_chunk_id=row["root_chunk_id"],
            parent_chunk_id=row.get("parent_chunk_id"),
            chunk_level=row["chunk_level"],
            chunk_index=row["chunk_index"],
            page_number=row.get("page_number", 0),
            content=row["content"],
            metadata=row.get("metadata", {}),
            original_filename=row.get("original_filename", ""),
        )
