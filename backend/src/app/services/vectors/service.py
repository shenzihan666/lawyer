from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Generator

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
from app.services.vectors.query_rewrite import QueryRewriteService
from app.services.vectors.rerank import DocumentRerankService
from app.services.vectors.store import DocumentChunkStore

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class SearchAttempt:
    stage: str
    query: str
    items: list[dict[str, Any]]
    meta: dict[str, Any]


class DocumentVectorService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.cache = RedisCache(settings)
        self.chunk_store = DocumentChunkStore(db=db, cache=self.cache)
        self.dense_embedding_service = ExternalEmbeddingService(settings)
        self.sparse_embedding_service = BM25SparseEmbeddingService(settings)
        self.query_rewrite_service = QueryRewriteService(settings)
        self.rerank_service = DocumentRerankService(settings)
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
        return self.search_chunks(
            query=query,
            top_k=top_k,
            document_ids=document_ids,
        )

    def search_chunks(
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
        query_rewrite_enabled = self.query_rewrite_service.is_enabled()
        cache_payload = {
            "query": normalized_query,
            "top_k": effective_top_k,
            "document_ids": selected_document_ids,
            "query_rewrite_enabled": query_rewrite_enabled,
            "query_rewrite_model": self.settings.query_rewrite_model or "",
            "rerank_enabled": self.rerank_service.is_enabled(),
            "rerank_model": self.settings.rerank_model
            or self.settings.answer_generation_model
            or self.settings.query_rewrite_model
            or "",
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
                    "query_rewrite_enabled": query_rewrite_enabled,
                    "rerank_enabled": self.rerank_service.is_enabled(),
                },
            )
            return SearchResponse.model_validate(cached)

        initial_attempt = self._execute_search_attempt(
            stage="initial",
            search_query=normalized_query,
            top_k=effective_top_k,
            document_ids=selected_document_ids,
        )
        attempts = [initial_attempt]
        rewrite_meta = self._build_default_query_rewrite_meta(normalized_query)

        if self.query_rewrite_service.is_enabled():
            try:
                rewrite_meta, expanded_attempts = self._run_query_rewrite_pipeline(
                    original_query=normalized_query,
                    initial_attempt=initial_attempt,
                    top_k=effective_top_k,
                    document_ids=selected_document_ids,
                )
                attempts.extend(expanded_attempts)
            except Exception as exc:
                logger.warning(
                    "Query rewrite pipeline failed; returning initial retrieval results",
                    extra={
                        "event": "vector_query_rewrite_failed",
                        "query_length": len(normalized_query),
                        "top_k": effective_top_k,
                        "document_filter_count": len(selected_document_ids),
                        "error": str(exc),
                    },
                )
                rewrite_meta["query_rewrite_error"] = str(exc)
                rewrite_meta["query_rewrite_skipped_reason"] = "rewrite_pipeline_failed"
        elif self.settings.query_rewrite_enabled:
            rewrite_meta["query_rewrite_skipped_reason"] = (
                "query_rewrite_not_configured"
            )

        final_items = (
            self._merge_search_attempts(attempts, effective_top_k)
            if len(attempts) > 1
            else initial_attempt.items
        )
        response = self._build_search_response(
            items=final_items,
            meta=self._build_search_meta(
                original_query=normalized_query,
                attempts=attempts,
                rewrite_meta=rewrite_meta,
                top_k=effective_top_k,
            ),
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
                "retrieval_mode": response.meta.get("retrieval_mode"),
                "query_rewrite_applied": response.meta.get("query_rewrite_applied"),
                "query_rewrite_strategy": response.meta.get("query_rewrite_strategy"),
                "rerank_applied": response.meta.get("rerank_applied"),
                "rerank_provider": response.meta.get("rerank_provider"),
            },
        )
        return response

    def search_stream(
        self,
        query: str,
        top_k: int | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> Generator[dict[str, Any], None, SearchResponse]:
        normalized_query = query.strip()
        if not normalized_query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query must not be empty.",
            )

        effective_top_k = top_k or self.settings.vector_search_top_k
        selected_document_ids = sorted({item for item in (document_ids or []) if item})
        query_rewrite_enabled = self.query_rewrite_service.is_enabled()

        yield self._progress_event(
            key="search-start",
            label="开始检索证据",
            detail=(
                f"top_k={effective_top_k}，文档范围 "
                f"{len(selected_document_ids) if selected_document_ids else '全部'}。"
            ),
        )

        cache_payload = {
            "query": normalized_query,
            "top_k": effective_top_k,
            "document_ids": selected_document_ids,
            "query_rewrite_enabled": query_rewrite_enabled,
            "query_rewrite_model": self.settings.query_rewrite_model or "",
            "rerank_enabled": self.rerank_service.is_enabled(),
            "rerank_model": self.settings.rerank_model
            or self.settings.answer_generation_model
            or self.settings.query_rewrite_model
            or "",
        }
        cached = self.chunk_store.get_cached_search(cache_payload)
        if cached is not None:
            response = SearchResponse.model_validate(cached)
            yield self._progress_event(
                key="search-cache",
                label="命中检索缓存",
                detail=f"直接返回 {len(response.items)} 条结果。",
                status="done",
            )
            return response

        initial_attempt = yield from self._execute_search_attempt_stream(
            stage="initial",
            search_query=normalized_query,
            top_k=effective_top_k,
            document_ids=selected_document_ids,
        )
        attempts = [initial_attempt]
        rewrite_meta = self._build_default_query_rewrite_meta(normalized_query)

        if self.query_rewrite_service.is_enabled():
            try:
                (
                    rewrite_meta,
                    expanded_attempts,
                ) = yield from self._run_query_rewrite_pipeline_stream(
                    original_query=normalized_query,
                    initial_attempt=initial_attempt,
                    top_k=effective_top_k,
                    document_ids=selected_document_ids,
                )
                attempts.extend(expanded_attempts)
            except Exception as exc:
                logger.warning(
                    "Query rewrite pipeline failed; returning initial retrieval results",
                    extra={
                        "event": "vector_query_rewrite_failed",
                        "query_length": len(normalized_query),
                        "top_k": effective_top_k,
                        "document_filter_count": len(selected_document_ids),
                        "error": str(exc),
                    },
                )
                rewrite_meta["query_rewrite_error"] = str(exc)
                rewrite_meta["query_rewrite_skipped_reason"] = "rewrite_pipeline_failed"
                yield self._progress_event(
                    key="query-rewrite-error",
                    label="扩展检索失败，回退初始结果",
                    detail=str(exc),
                    status="error",
                )
        elif self.settings.query_rewrite_enabled:
            rewrite_meta["query_rewrite_skipped_reason"] = (
                "query_rewrite_not_configured"
            )
            yield self._progress_event(
                key="query-rewrite-skipped",
                label="扩展检索未配置",
                detail="已跳过 query rewrite。",
                status="done",
            )

        final_items = (
            self._merge_search_attempts(attempts, effective_top_k)
            if len(attempts) > 1
            else initial_attempt.items
        )
        response = self._build_search_response(
            items=final_items,
            meta=self._build_search_meta(
                original_query=normalized_query,
                attempts=attempts,
                rewrite_meta=rewrite_meta,
                top_k=effective_top_k,
            ),
        )
        self.chunk_store.set_cached_search(cache_payload, response.model_dump())
        yield self._progress_event(
            key="search-complete",
            label="检索完成",
            detail=f"最终命中 {len(response.items)} 条结果。",
            status="done",
        )
        return response

    def _run_query_rewrite_pipeline_stream(
        self,
        original_query: str,
        initial_attempt: SearchAttempt,
        top_k: int,
        document_ids: list[str],
    ) -> Generator[dict[str, Any], None, tuple[dict[str, Any], list[SearchAttempt]]]:
        rewrite_meta = self._build_default_query_rewrite_meta(original_query)

        yield self._progress_event(
            key="query-grade-start",
            label="评估首轮召回质量",
            detail="判断是否需要扩展查询。",
        )
        grade = self.query_rewrite_service.grade_retrieval(
            original_query,
            initial_attempt.items,
        )
        rewrite_meta["relevance_grade_score"] = grade.binary_score
        rewrite_meta["relevance_grade_reason"] = grade.reason
        rewrite_meta["rewrite_needed"] = grade.rewrite_needed
        yield self._progress_event(
            key="query-grade-result",
            label="召回质量评估完成",
            detail=f"grade={grade.binary_score}，{grade.reason}",
            status="done",
        )

        if not grade.rewrite_needed:
            rewrite_meta["query_rewrite_skipped_reason"] = "relevance_grade_passed"
            yield self._progress_event(
                key="query-rewrite-skip",
                label="首轮召回已足够，跳过扩展检索",
                detail="保留原问题继续回答。",
                status="done",
            )
            return rewrite_meta, []

        yield self._progress_event(
            key="query-plan-start",
            label="生成扩展查询",
            detail="准备 step-back / HyDE 扩展策略。",
        )
        plan = self.query_rewrite_service.plan_rewrite(
            original_query,
            initial_attempt.items,
        )
        expanded_queries = plan.expanded_queries()
        rewrite_meta.update(
            {
                "query_rewrite_strategy": plan.strategy,
                "query_rewrite_reason": plan.reason,
                "step_back_question": plan.step_back_question,
                "expanded_queries": [query for _, query in expanded_queries],
                "primary_expanded_query": expanded_queries[0][1]
                if expanded_queries
                else None,
                "hypothetical_answer": plan.hypothetical_answer,
            }
        )
        yield self._progress_event(
            key="query-plan-result",
            label="扩展查询已生成",
            detail=plan.reason or plan.strategy,
            status="done",
        )

        if not expanded_queries:
            rewrite_meta["query_rewrite_skipped_reason"] = "planner_returned_no_query"
            yield self._progress_event(
                key="query-rewrite-empty",
                label="扩展查询为空",
                detail="保持初始检索结果。",
                status="done",
            )
            return rewrite_meta, []

        expanded_attempts: list[SearchAttempt] = []
        for stage, expanded_query in expanded_queries:
            yield self._progress_event(
                key=f"{stage}-prepare",
                label=f"启动 {self._search_stage_label(stage)}",
                detail=expanded_query,
            )
            attempt = yield from self._execute_search_attempt_stream(
                stage=stage,
                search_query=expanded_query,
                top_k=top_k,
                document_ids=document_ids,
            )
            expanded_attempts.append(attempt)

        rewrite_meta["query_rewrite_applied"] = any(
            attempt.items for attempt in expanded_attempts
        )
        rewrite_meta["query_rewrite_stage"] = (
            "expanded" if rewrite_meta["query_rewrite_applied"] else "initial"
        )
        if not rewrite_meta["query_rewrite_applied"]:
            rewrite_meta["query_rewrite_skipped_reason"] = (
                "expanded_retrieval_returned_no_results"
            )
            yield self._progress_event(
                key="query-rewrite-no-hit",
                label="扩展检索未带来新增结果",
                detail="保留初始结果。",
                status="done",
            )

        return rewrite_meta, expanded_attempts

    def _execute_search_attempt_stream(
        self,
        stage: str,
        search_query: str,
        top_k: int,
        document_ids: list[str],
    ) -> Generator[dict[str, Any], None, SearchAttempt]:
        stage_label = self._search_stage_label(stage)
        yield self._progress_event(
            key=f"{stage}-embed",
            label=f"{stage_label}生成检索向量",
            detail="准备 dense + sparse 查询表示。",
        )
        corpus_stats = self.chunk_store.get_bm25_stats()
        if corpus_stats is None:
            corpus_stats = self._build_and_cache_bm25_stats()

        dense_embedding = self.dense_embedding_service.embed_text(search_query)
        sparse_embedding = self.sparse_embedding_service.sparse_embed_text(
            search_query,
            corpus_stats,
        )

        candidate_k = max(top_k * 3, top_k)
        yield self._progress_event(
            key=f"{stage}-retrieve",
            label=f"{stage_label}执行向量检索",
            detail=f"候选上限 {candidate_k} 条。",
        )
        try:
            retrieved, retrieval_mode = self.milvus.search(
                dense_embedding=dense_embedding,
                sparse_embedding=sparse_embedding,
                top_k=candidate_k,
                document_ids=document_ids,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Vector search is unavailable: {exc}",
            ) from exc

        yield self._progress_event(
            key=f"{stage}-retrieve-done",
            label=f"{stage_label}完成向量召回",
            detail=f"模式 {retrieval_mode}，命中 {len(retrieved)} 条候选。",
            status="done",
        )

        yield self._progress_event(
            key=f"{stage}-rerank",
            label=f"{stage_label}重排候选结果",
            detail="按相关性重新排序。",
        )
        reranked, rerank_meta = self.rerank_service.rerank(
            query=search_query,
            docs=retrieved,
            top_k=top_k,
        )
        if rerank_meta.get("rerank_applied"):
            rerank_detail = (
                f"provider={rerank_meta.get('rerank_provider') or 'unknown'}，"
                f"候选 {int(rerank_meta.get('rerank_candidate_count') or 0)} 条。"
            )
        else:
            rerank_detail = str(
                rerank_meta.get("rerank_skipped_reason") or "未执行 rerank。"
            )
        yield self._progress_event(
            key=f"{stage}-rerank-done",
            label=f"{stage_label}重排结束",
            detail=rerank_detail,
            status="done",
        )

        yield self._progress_event(
            key=f"{stage}-merge",
            label=f"{stage_label}合并父块结果",
            detail="检查是否需要把命中的子块上卷到父块。",
        )
        merged, merge_meta = self._auto_merge_documents(reranked, top_k)
        merge_detail = (
            f"替换 {int(merge_meta.get('auto_merge_replaced_chunks') or 0)} 个 chunk。"
            if merge_meta.get("auto_merge_applied")
            else "未触发父块合并。"
        )
        yield self._progress_event(
            key=f"{stage}-merge-done",
            label=f"{stage_label}整理完成",
            detail=merge_detail,
            status="done",
        )

        return SearchAttempt(
            stage=stage,
            query=search_query,
            items=merged,
            meta={
                "retrieval_mode": retrieval_mode,
                "candidate_k": candidate_k,
                **rerank_meta,
                **merge_meta,
            },
        )

    def _run_query_rewrite_pipeline(
        self,
        original_query: str,
        initial_attempt: SearchAttempt,
        top_k: int,
        document_ids: list[str],
    ) -> tuple[dict[str, Any], list[SearchAttempt]]:
        rewrite_meta = self._build_default_query_rewrite_meta(original_query)
        grade = self.query_rewrite_service.grade_retrieval(
            original_query,
            initial_attempt.items,
        )
        rewrite_meta["relevance_grade_score"] = grade.binary_score
        rewrite_meta["relevance_grade_reason"] = grade.reason
        rewrite_meta["rewrite_needed"] = grade.rewrite_needed

        if not grade.rewrite_needed:
            rewrite_meta["query_rewrite_skipped_reason"] = "relevance_grade_passed"
            return rewrite_meta, []

        plan = self.query_rewrite_service.plan_rewrite(
            original_query,
            initial_attempt.items,
        )
        expanded_queries = plan.expanded_queries()
        rewrite_meta.update(
            {
                "query_rewrite_strategy": plan.strategy,
                "query_rewrite_reason": plan.reason,
                "step_back_question": plan.step_back_question,
                "expanded_queries": [query for _, query in expanded_queries],
                "primary_expanded_query": expanded_queries[0][1]
                if expanded_queries
                else None,
                "hypothetical_answer": plan.hypothetical_answer,
            }
        )
        if not expanded_queries:
            rewrite_meta["query_rewrite_skipped_reason"] = "planner_returned_no_query"
            return rewrite_meta, []

        expanded_attempts = [
            self._execute_search_attempt(
                stage=stage,
                search_query=expanded_query,
                top_k=top_k,
                document_ids=document_ids,
            )
            for stage, expanded_query in expanded_queries
        ]
        rewrite_meta["query_rewrite_applied"] = any(
            attempt.items for attempt in expanded_attempts
        )
        rewrite_meta["query_rewrite_stage"] = (
            "expanded" if rewrite_meta["query_rewrite_applied"] else "initial"
        )
        if not rewrite_meta["query_rewrite_applied"]:
            rewrite_meta["query_rewrite_skipped_reason"] = (
                "expanded_retrieval_returned_no_results"
            )

        return rewrite_meta, expanded_attempts

    def _execute_search_attempt(
        self,
        stage: str,
        search_query: str,
        top_k: int,
        document_ids: list[str],
    ) -> SearchAttempt:
        corpus_stats = self.chunk_store.get_bm25_stats()
        if corpus_stats is None:
            corpus_stats = self._build_and_cache_bm25_stats()

        dense_embedding = self.dense_embedding_service.embed_text(search_query)
        sparse_embedding = self.sparse_embedding_service.sparse_embed_text(
            search_query,
            corpus_stats,
        )
        candidate_k = max(top_k * 3, top_k)
        try:
            retrieved, retrieval_mode = self.milvus.search(
                dense_embedding=dense_embedding,
                sparse_embedding=sparse_embedding,
                top_k=candidate_k,
                document_ids=document_ids,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Vector search is unavailable: {exc}",
            ) from exc

        reranked, rerank_meta = self.rerank_service.rerank(
            query=search_query,
            docs=retrieved,
            top_k=top_k,
        )
        merged, merge_meta = self._auto_merge_documents(reranked, top_k)
        return SearchAttempt(
            stage=stage,
            query=search_query,
            items=merged,
            meta={
                "retrieval_mode": retrieval_mode,
                "candidate_k": candidate_k,
                **rerank_meta,
                **merge_meta,
            },
        )

    def _build_default_query_rewrite_meta(
        self,
        original_query: str,
    ) -> dict[str, Any]:
        return {
            "query_rewrite_enabled": self.settings.query_rewrite_enabled,
            "query_rewrite_configured": self.query_rewrite_service.is_configured(),
            "query_rewrite_applied": False,
            "query_rewrite_stage": "initial",
            "query_rewrite_strategy": None,
            "query_rewrite_reason": None,
            "query_rewrite_error": None,
            "query_rewrite_skipped_reason": None,
            "relevance_grade_score": "skipped",
            "relevance_grade_reason": None,
            "rewrite_needed": False,
            "original_query": original_query,
            "final_query": original_query,
            "expanded_queries": [],
            "primary_expanded_query": None,
            "step_back_question": "",
            "hypothetical_answer": "",
        }

    def _build_search_meta(
        self,
        original_query: str,
        attempts: list[SearchAttempt],
        rewrite_meta: dict[str, Any],
        top_k: int,
    ) -> dict[str, Any]:
        initial_attempt = attempts[0]
        combined_meta = {
            **initial_attempt.meta,
            **rewrite_meta,
            "original_query": original_query,
            "final_query": rewrite_meta.get("primary_expanded_query") or original_query,
            "initial_result_count": len(initial_attempt.items),
            "expanded_result_count": sum(
                len(attempt.items) for attempt in attempts[1:]
            ),
            "final_result_count": min(
                top_k,
                len(self._merge_search_attempts(attempts, top_k))
                if len(attempts) > 1
                else len(initial_attempt.items),
            ),
            "search_attempts": [
                {
                    "stage": attempt.stage,
                    "query": attempt.query,
                    "result_count": len(attempt.items),
                    "retrieval_mode": attempt.meta.get("retrieval_mode"),
                    "candidate_k": attempt.meta.get("candidate_k"),
                    "rerank_applied": attempt.meta.get("rerank_applied"),
                    "rerank_provider": attempt.meta.get("rerank_provider"),
                    "rerank_model": attempt.meta.get("rerank_model"),
                    "rerank_candidate_count": attempt.meta.get(
                        "rerank_candidate_count"
                    ),
                    "rerank_error": attempt.meta.get("rerank_error"),
                    "rerank_skipped_reason": attempt.meta.get("rerank_skipped_reason"),
                    "auto_merge_applied": attempt.meta.get("auto_merge_applied"),
                    "auto_merge_replaced_chunks": attempt.meta.get(
                        "auto_merge_replaced_chunks"
                    ),
                }
                for attempt in attempts
            ],
        }
        if len(attempts) == 1:
            return combined_meta

        combined_meta.update(
            {
                "retrieval_mode": "multi_stage",
                "candidate_k": max(
                    int(attempt.meta.get("candidate_k", top_k)) for attempt in attempts
                ),
                "initial_retrieval_mode": initial_attempt.meta.get("retrieval_mode"),
                "expanded_retrieval_modes": [
                    attempt.meta.get("retrieval_mode") for attempt in attempts[1:]
                ],
                "rerank_enabled": any(
                    bool(attempt.meta.get("rerank_enabled")) for attempt in attempts
                ),
                "rerank_configured": any(
                    bool(attempt.meta.get("rerank_configured")) for attempt in attempts
                ),
                "rerank_applied": any(
                    bool(attempt.meta.get("rerank_applied")) for attempt in attempts
                ),
                "rerank_provider": next(
                    (
                        attempt.meta.get("rerank_provider")
                        for attempt in attempts
                        if attempt.meta.get("rerank_provider")
                    ),
                    None,
                ),
                "rerank_model": next(
                    (
                        attempt.meta.get("rerank_model")
                        for attempt in attempts
                        if attempt.meta.get("rerank_model")
                    ),
                    None,
                ),
                "rerank_endpoint": next(
                    (
                        attempt.meta.get("rerank_endpoint")
                        for attempt in attempts
                        if attempt.meta.get("rerank_endpoint")
                    ),
                    None,
                ),
                "rerank_error": "; ".join(
                    [
                        str(attempt.meta.get("rerank_error"))
                        for attempt in attempts
                        if attempt.meta.get("rerank_error")
                    ]
                )
                or None,
                "rerank_skipped_reason": next(
                    (
                        attempt.meta.get("rerank_skipped_reason")
                        for attempt in attempts
                        if attempt.meta.get("rerank_skipped_reason")
                    ),
                    None,
                ),
                "rerank_candidate_count": max(
                    int(attempt.meta.get("rerank_candidate_count") or 0)
                    for attempt in attempts
                ),
                "auto_merge_enabled": True,
                "auto_merge_applied": any(
                    bool(attempt.meta.get("auto_merge_applied")) for attempt in attempts
                ),
                "auto_merge_replaced_chunks": sum(
                    int(attempt.meta.get("auto_merge_replaced_chunks") or 0)
                    for attempt in attempts
                ),
                "auto_merge_steps": sum(
                    int(attempt.meta.get("auto_merge_steps") or 0)
                    for attempt in attempts
                ),
                "auto_merge_threshold": self.settings.vector_auto_merge_threshold,
            }
        )
        return combined_meta

    def _merge_search_attempts(
        self,
        attempts: Sequence[SearchAttempt],
        top_k: int,
    ) -> list[dict[str, Any]]:
        merged_map: dict[str, dict[str, Any]] = {}

        for attempt in attempts:
            for rank, item in enumerate(attempt.items, start=1):
                chunk_id = item["chunk_id"]
                existing = merged_map.get(chunk_id)

                if existing is None:
                    merged_item = dict(item)
                    metadata = dict(merged_item.get("metadata", {}))
                    metadata["matched_stages"] = [attempt.stage]
                    metadata["matched_queries"] = [attempt.query]
                    metadata["stage_ranks"] = {attempt.stage: rank}
                    metadata["matched_stage_count"] = 1
                    merged_item["metadata"] = metadata
                    merged_item["_stage_hit_count"] = 1
                    merged_map[chunk_id] = merged_item
                    continue

                metadata = dict(existing.get("metadata", {}))
                matched_stages = list(metadata.get("matched_stages", []))
                matched_queries = list(metadata.get("matched_queries", []))
                stage_ranks = dict(metadata.get("stage_ranks", {}))

                if attempt.stage not in matched_stages:
                    matched_stages.append(attempt.stage)
                if attempt.query not in matched_queries:
                    matched_queries.append(attempt.query)
                stage_ranks[attempt.stage] = rank

                metadata["matched_stages"] = matched_stages
                metadata["matched_queries"] = matched_queries
                metadata["stage_ranks"] = stage_ranks
                metadata["matched_stage_count"] = len(matched_stages)
                existing["metadata"] = metadata
                existing["_stage_hit_count"] = len(matched_stages)
                existing["score"] = max(
                    float(existing.get("score", 0.0)),
                    float(item.get("score", 0.0)),
                )

        merged_items = list(merged_map.values())
        merged_items.sort(
            key=lambda item: (
                int(item.get("_stage_hit_count", 1)),
                float(item.get("score", 0.0)),
            ),
            reverse=True,
        )
        for item in merged_items:
            item.pop("_stage_hit_count", None)

        return merged_items[:top_k]

    def _build_search_response(
        self,
        items: Sequence[dict[str, Any]],
        meta: dict[str, Any],
    ) -> SearchResponse:
        return SearchResponse(
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
                for item in items
            ],
            meta=meta,
        )

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

    @staticmethod
    def _progress_event(
        *,
        key: str,
        label: str,
        detail: str | None = None,
        status: str = "running",
    ) -> dict[str, Any]:
        return {
            "type": "rag_step",
            "step": {
                "key": key,
                "label": label,
                "detail": detail or "",
                "status": status,
            },
        }

    @staticmethod
    def _search_stage_label(stage: str) -> str:
        mapping = {
            "initial": "首轮检索",
            "step_back": "Step-back 扩展检索",
            "hyde": "HyDE 扩展检索",
        }
        return mapping.get(stage, f"{stage} 检索")

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
