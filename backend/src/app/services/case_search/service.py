from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models import (
    CaseSearchHit,
    CaseSearchQueryAsset,
    CaseSearchRecord,
    DocumentAsset,
)
from app.schemas.case_search import (
    CaseSearchDetailResponse,
    CaseSearchHitItem,
    CaseSearchListItem,
    CaseSearchListResponse,
    CaseSearchMatchedChunk,
    CaseSearchQueryAssetSummary,
)
from app.schemas.search import SearchResultItem
from app.services.case_search.preview import DocumentPreviewService
from app.services.case_search.query_builder import CaseSearchQueryBuilder
from app.services.case_search.storage import CaseSearchStorage
from app.services.loaders import registry
from app.services.loaders.base import DocumentLoadError, UnsupportedDocumentTypeError
from app.services.vectors import DocumentVectorService


@dataclass(slots=True)
class AggregatedCaseHit:
    document_id: str
    original_filename: str
    preview_excerpt: str | None
    aggregated_score: float
    matched_pages: list[int]
    matched_chunk_ids: list[str]
    matched_snippets: list[str]
    top_chunks: list[CaseSearchMatchedChunk]
    meta: dict


class CaseSearchService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.vector_service = DocumentVectorService(db=db, settings=settings)
        self.query_builder = CaseSearchQueryBuilder(settings)
        self.storage = CaseSearchStorage(settings)
        self.preview_service = DocumentPreviewService(db=db, settings=settings)

    def list_searches(self) -> CaseSearchListResponse:
        rows = list(
            self.db.scalars(
                select(CaseSearchRecord)
                .options(selectinload(CaseSearchRecord.query_asset))
                .order_by(CaseSearchRecord.created_at.desc())
            )
        )
        return CaseSearchListResponse(items=[self._to_list_item(row) for row in rows])

    def get_search(self, search_id: str) -> CaseSearchDetailResponse:
        record = self.db.scalar(
            select(CaseSearchRecord)
            .options(
                selectinload(CaseSearchRecord.query_asset),
                selectinload(CaseSearchRecord.hits),
            )
            .where(CaseSearchRecord.id == search_id)
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case search not found",
            )

        return CaseSearchDetailResponse(
            item=self._to_list_item(record),
            hits=[
                self._to_hit_item(hit)
                for hit in sorted(record.hits, key=lambda item: item.rank)
            ],
        )

    def create_search(
        self,
        *,
        query_text: str | None,
        upload: UploadFile | None,
        top_k: int,
        document_ids: Sequence[str] | None,
    ) -> CaseSearchDetailResponse:
        normalized_query_text = (query_text or "").strip()
        has_upload = upload is not None and bool(upload.filename)
        if bool(normalized_query_text) == bool(has_upload):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide either query_text or file, but not both.",
            )

        selected_document_ids = sorted({item for item in (document_ids or []) if item})
        query_asset: CaseSearchQueryAsset | None = None
        prepared_query = ""

        if has_upload and upload is not None:
            query_asset, prepared_query = self._create_query_asset(upload)
            query_type = "upload"
        else:
            prepared_query = self.query_builder.build_from_text(normalized_query_text)
            query_type = "text"

        if not prepared_query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to prepare a valid case search query.",
            )

        record = CaseSearchRecord(
            id=str(uuid4()),
            query_type=query_type,
            query_text=normalized_query_text or None,
            prepared_query=prepared_query,
            top_k=top_k,
            scope_document_ids_json=selected_document_ids,
            query_asset_id=query_asset.id if query_asset else None,
            status="running",
            result_count=0,
        )
        self.db.add(record)
        self.db.flush()

        search_response = self.vector_service.search_chunks(
            query=prepared_query,
            top_k=max(top_k * 5, top_k),
            document_ids=selected_document_ids,
        )
        aggregated_hits = self._aggregate_hits(search_response.items, top_k)

        for rank, hit in enumerate(aggregated_hits, start=1):
            self.db.add(
                CaseSearchHit(
                    search_id=record.id,
                    document_id=hit.document_id,
                    rank=rank,
                    score=hit.aggregated_score,
                    matched_chunk_count=len(hit.matched_chunk_ids),
                    matched_pages_json=hit.matched_pages,
                    matched_chunk_ids_json=hit.matched_chunk_ids,
                    matched_snippets_json=hit.matched_snippets,
                    hit_summary_json={
                        "original_filename": hit.original_filename,
                        "preview_excerpt": hit.preview_excerpt,
                        "top_chunks": [chunk.model_dump() for chunk in hit.top_chunks],
                        "meta": hit.meta,
                    },
                )
            )

        record.status = "completed"
        record.result_count = len(aggregated_hits)
        self.db.commit()
        return self.get_search(record.id)

    def delete_search(self, search_id: str) -> None:
        record = self.db.scalar(
            select(CaseSearchRecord)
            .options(
                selectinload(CaseSearchRecord.query_asset),
                selectinload(CaseSearchRecord.hits),
            )
            .where(CaseSearchRecord.id == search_id)
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case search not found",
            )

        query_asset = record.query_asset
        self.db.delete(record)
        self.db.commit()

        if query_asset is not None:
            self.preview_service.delete_preview_artifact(
                query_asset.preview_storage_path
            )
            self.storage.delete_path(query_asset.storage_path)
            self.db.delete(query_asset)
            self.db.commit()

    def _create_query_asset(
        self, upload: UploadFile
    ) -> tuple[CaseSearchQueryAsset, str]:
        stored_file = self.storage.save_query_upload(upload)
        asset = CaseSearchQueryAsset(
            id=stored_file.document_id,
            original_filename=stored_file.original_filename,
            stored_filename=stored_file.stored_filename,
            storage_path=stored_file.relative_path,
            file_extension=stored_file.file_extension,
            mime_type=stored_file.mime_type,
            sha256=stored_file.sha256_digest,
            file_size=stored_file.file_size,
            extraction_status="processing",
            preview_status="not_requested",
        )
        self.db.add(asset)
        self.db.flush()

        try:
            load_result = registry.load_document(stored_file.absolute_path)
        except UnsupportedDocumentTypeError as exc:
            asset.extraction_status = "failed"
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except DocumentLoadError as exc:
            asset.extraction_status = "failed"
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            asset.extraction_status = "failed"
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to extract query asset: {exc}",
            ) from exc

        prepared_query, excerpt = self.query_builder.build_from_fragments(
            load_result.fragments
        )
        asset.preview_excerpt = excerpt or None
        asset.extracted_text = "\n".join(
            fragment.content.strip()
            for fragment in load_result.fragments
            if fragment.content.strip()
        )
        asset.extraction_status = "ready"
        self.db.flush()
        return asset, prepared_query

    def _aggregate_hits(
        self,
        items: Sequence[SearchResultItem],
        top_k: int,
    ) -> list[AggregatedCaseHit]:
        if not items:
            return []

        document_ids = {item.document_id for item in items}
        document_map = {
            row.id: row
            for row in self.db.scalars(
                select(DocumentAsset).where(DocumentAsset.id.in_(document_ids))
            )
        }
        grouped: dict[str, list[SearchResultItem]] = defaultdict(list)
        for item in items:
            grouped[item.document_id].append(item)

        aggregated: list[AggregatedCaseHit] = []
        for document_id, group_items in grouped.items():
            sorted_items = sorted(
                group_items, key=lambda item: item.score, reverse=True
            )
            max_score = sorted_items[0].score if sorted_items else 0.0
            chunk_bonus = min(0.2, max(0, len(sorted_items) - 1) * 0.05)
            document = document_map.get(document_id)
            aggregated.append(
                AggregatedCaseHit(
                    document_id=document_id,
                    original_filename=sorted_items[0].original_filename,
                    preview_excerpt=document.preview_excerpt if document else None,
                    aggregated_score=max_score + chunk_bonus,
                    matched_pages=sorted(
                        {
                            item.page_number
                            for item in sorted_items
                            if item.page_number > 0
                        }
                    ),
                    matched_chunk_ids=[item.chunk_id for item in sorted_items],
                    matched_snippets=[
                        self._clip_text(item.content, 200) for item in sorted_items[:3]
                    ],
                    top_chunks=[
                        CaseSearchMatchedChunk(
                            chunk_id=item.chunk_id,
                            page_number=item.page_number,
                            score=item.score,
                            content=self._clip_text(item.content, 280),
                            metadata=item.metadata,
                        )
                        for item in sorted_items[:3]
                    ],
                    meta={
                        "max_chunk_score": max_score,
                        "chunk_bonus": chunk_bonus,
                        "document_vector_status": document.vector_status
                        if document
                        else None,
                    },
                )
            )

        aggregated.sort(
            key=lambda item: (item.aggregated_score, len(item.matched_chunk_ids)),
            reverse=True,
        )
        return aggregated[:top_k]

    def _to_list_item(self, record: CaseSearchRecord) -> CaseSearchListItem:
        return CaseSearchListItem(
            id=record.id,
            query_type=record.query_type,
            query_text=record.query_text,
            prepared_query=record.prepared_query,
            top_k=record.top_k,
            scope_document_ids=list(record.scope_document_ids_json or []),
            status=record.status,
            result_count=record.result_count,
            query_asset=(
                CaseSearchQueryAssetSummary.model_validate(record.query_asset)
                if record.query_asset is not None
                else None
            ),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _to_hit_item(self, hit: CaseSearchHit) -> CaseSearchHitItem:
        summary = hit.hit_summary_json or {}
        return CaseSearchHitItem(
            id=hit.id,
            document_id=hit.document_id,
            original_filename=str(summary.get("original_filename", "")),
            preview_excerpt=summary.get("preview_excerpt"),
            rank=hit.rank,
            score=hit.score,
            matched_chunk_count=hit.matched_chunk_count,
            matched_pages=list(hit.matched_pages_json or []),
            matched_chunk_ids=list(hit.matched_chunk_ids_json or []),
            matched_snippets=list(hit.matched_snippets_json or []),
            top_chunks=[
                CaseSearchMatchedChunk.model_validate(item)
                for item in summary.get("top_chunks", [])
            ],
            meta=dict(summary.get("meta", {})),
        )

    @staticmethod
    def _clip_text(value: str, limit: int) -> str:
        normalized = " ".join((value or "").split())
        if len(normalized) <= limit:
            return normalized
        if limit <= 3:
            return normalized[:limit]
        return normalized[: limit - 3].rstrip() + "..."
