from collections.abc import Sequence
from datetime import datetime, timezone
import logging
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    DocumentAsset,
    DocumentFragment,
    DocumentIngestionStatus,
    DocumentVectorStatus,
)
from app.schemas.document import (
    DocumentItem,
    DocumentListResponse,
    DocumentOperationResponse,
    DocumentPreviewResponse,
    DocumentSummary,
)
from app.services.case_search.preview import DocumentPreviewService
from app.services.documents.storage import UploadStorage
from app.services.loaders import registry
from app.services.loaders.base import DocumentLoadError, UnsupportedDocumentTypeError
from app.services.vectors import DocumentVectorService

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.storage = UploadStorage(settings)
        self.preview_service = DocumentPreviewService(db=db, settings=settings)
        self.vector_service = DocumentVectorService(db=db, settings=settings)

    def list_documents(self) -> DocumentListResponse:
        documents = self._fetch_documents(include_deleted=True)
        active_items = [
            self._to_item(document)
            for document in documents
            if document.deleted_at is None
        ]
        return DocumentListResponse(
            items=active_items,
            summary=self._build_summary(documents),
        )

    def upload_documents(
        self, files: Sequence[UploadFile]
    ) -> DocumentOperationResponse:
        if not files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No files were provided.",
            )

        affected_ids: list[str] = []

        for upload in files:
            if not upload.filename:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One of the uploaded files is missing a filename.",
                )

            try:
                loader_name = registry.get_loader_name_for_suffix(
                    Path(upload.filename).suffix.lower()
                )
            except UnsupportedDocumentTypeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc

            stored_file = self.storage.save(upload)
            logger.info(
                "Stored upload",
                extra={
                    "event": "document_upload_stored",
                    "document_id": stored_file.document_id,
                    "original_filename": stored_file.original_filename,
                    "file_extension": stored_file.file_extension,
                    "loader_name": loader_name,
                    "file_size": stored_file.file_size,
                },
            )
            document = DocumentAsset(
                id=stored_file.document_id,
                original_filename=stored_file.original_filename,
                stored_filename=stored_file.stored_filename,
                storage_path=stored_file.relative_path,
                file_extension=stored_file.file_extension,
                mime_type=stored_file.mime_type,
                loader_name=loader_name,
                sha256=stored_file.sha256_digest,
                file_size=stored_file.file_size,
                ingestion_status=DocumentIngestionStatus.processing.value,
                vector_status=DocumentVectorStatus.not_requested.value,
                trace_metadata={
                    "milvus_collection": self.settings.milvus_collection,
                    "milvus_database": self.settings.milvus_database,
                    "relative_path": stored_file.relative_path,
                },
            )
            self.db.add(document)
            self.db.flush()

            try:
                load_result = registry.load_document(stored_file.absolute_path)
            except (DocumentLoadError, UnsupportedDocumentTypeError) as exc:
                document.ingestion_status = DocumentIngestionStatus.failed.value
                document.failure_reason = str(exc)
                document.updated_at = utcnow()
                logger.warning(
                    "Document ingestion failed",
                    extra={
                        "event": "document_ingestion_failed",
                        "document_id": document.id,
                        "original_filename": document.original_filename,
                        "reason": str(exc),
                    },
                )
            except Exception as exc:
                document.ingestion_status = DocumentIngestionStatus.failed.value
                document.failure_reason = f"Unexpected loader failure: {exc}"
                document.updated_at = utcnow()
                logger.exception(
                    "Unexpected document loader failure",
                    extra={
                        "event": "document_ingestion_failed",
                        "document_id": document.id,
                        "original_filename": document.original_filename,
                    },
                )
            else:
                document.loader_name = load_result.loader_name
                document.raw_doc_count = len(load_result.fragments)
                document.page_count = max(
                    (fragment.page_number for fragment in load_result.fragments),
                    default=0,
                )
                document.preview_excerpt = load_result.fragments[0].content[:280]
                document.ingestion_status = DocumentIngestionStatus.ready.value
                document.trace_metadata = {
                    **document.trace_metadata,
                    "raw_doc_count": document.raw_doc_count,
                }

                for fragment in load_result.fragments:
                    document.fragments.append(
                        DocumentFragment(
                            fragment_index=fragment.fragment_index,
                            page_number=fragment.page_number,
                            content=fragment.content,
                            fragment_metadata=fragment.metadata,
                        )
                    )
                logger.info(
                    "Document ingested",
                    extra={
                        "event": "document_ingested",
                        "document_id": document.id,
                        "original_filename": document.original_filename,
                        "raw_doc_count": document.raw_doc_count,
                        "page_count": document.page_count,
                    },
                )

            self.db.commit()
            self.db.refresh(document)
            affected_ids.append(document.id)

        documents = self._fetch_documents(include_deleted=True)
        active_items = [
            self._to_item(document)
            for document in documents
            if document.deleted_at is None
        ]
        return DocumentOperationResponse(
            items=active_items,
            summary=self._build_summary(documents),
            affected_ids=affected_ids,
        )

    def queue_vectorization(
        self, document_ids: Sequence[str]
    ) -> DocumentOperationResponse:
        logger.info(
            "Vectorization requested",
            extra={
                "event": "document_vectorization_requested",
                "requested_count": len(document_ids),
            },
        )
        documents = self._fetch_documents(include_deleted=True)
        selected = {document.id: document for document in documents}
        affected_ids: list[str] = []

        for document_id in document_ids:
            document = selected.get(document_id)
            if document is None or document.deleted_at is not None:
                continue
            if document.ingestion_status != DocumentIngestionStatus.ready.value:
                continue

            document.vector_status = DocumentVectorStatus.queued.value
            document.updated_at = utcnow()
            affected_ids.append(document.id)

        self.db.commit()
        indexed_ids = self.vector_service.index_documents(affected_ids)
        logger.info(
            "Vectorization completed",
            extra={
                "event": "document_vectorization_completed",
                "queued_count": len(affected_ids),
                "indexed_count": len(indexed_ids),
            },
        )
        documents = self._fetch_documents(include_deleted=True)
        active_items = [
            self._to_item(document)
            for document in documents
            if document.deleted_at is None
        ]
        return DocumentOperationResponse(
            items=active_items,
            summary=self._build_summary(documents),
            affected_ids=indexed_ids or affected_ids,
        )

    def soft_delete_documents(
        self, document_ids: Sequence[str]
    ) -> DocumentOperationResponse:
        logger.info(
            "Document deletion requested",
            extra={
                "event": "document_delete_requested",
                "requested_count": len(document_ids),
            },
        )
        documents = self._fetch_documents(include_deleted=True)
        selected = {document.id: document for document in documents}
        affected_ids: list[str] = []

        for document_id in document_ids:
            document = selected.get(document_id)
            if document is None or document.deleted_at is not None:
                continue

            preview_storage_path = None
            if isinstance(document.trace_metadata, dict):
                preview_storage_path = document.trace_metadata.get("preview_storage_path")
            self.preview_service.delete_preview_artifact(preview_storage_path)
            document.deleted_at = utcnow()
            document.ingestion_status = DocumentIngestionStatus.deleted.value
            document.updated_at = utcnow()
            affected_ids.append(document.id)

        self.db.commit()
        self.vector_service.delete_document_vectors(affected_ids)
        self.db.commit()
        logger.info(
            "Documents soft deleted",
            extra={
                "event": "document_deleted",
                "deleted_count": len(affected_ids),
            },
        )
        documents = self._fetch_documents(include_deleted=True)
        active_items = [
            self._to_item(document)
            for document in documents
            if document.deleted_at is None
        ]
        return DocumentOperationResponse(
            items=active_items,
            summary=self._build_summary(documents),
            affected_ids=affected_ids,
        )

    def get_document_preview(self, document_id: str) -> DocumentPreviewResponse:
        return self.preview_service.get_document_preview(document_id)

    def resolve_document_file_path(
        self,
        document_id: str,
        *,
        preview: bool = False,
    ):
        return self.preview_service.resolve_document_file_path(
            document_id,
            preview=preview,
        )

    def _fetch_documents(self, include_deleted: bool) -> list[DocumentAsset]:
        query = select(DocumentAsset).order_by(DocumentAsset.uploaded_at.desc())
        documents = list(self.db.scalars(query))
        if include_deleted:
            return documents
        return [document for document in documents if document.deleted_at is None]

    def _build_summary(self, documents: Sequence[DocumentAsset]) -> DocumentSummary:
        active = [document for document in documents if document.deleted_at is None]
        return DocumentSummary(
            total=len(active),
            ready=sum(
                document.ingestion_status == DocumentIngestionStatus.ready.value
                for document in active
            ),
            failed=sum(
                document.ingestion_status == DocumentIngestionStatus.failed.value
                for document in active
            ),
            vector_queued=sum(
                document.vector_status == DocumentVectorStatus.queued.value
                for document in active
            ),
            vector_indexed=sum(
                document.vector_status == DocumentVectorStatus.indexed.value
                for document in active
            ),
            vector_failed=sum(
                document.vector_status == DocumentVectorStatus.failed.value
                for document in active
            ),
            deleted=sum(document.deleted_at is not None for document in documents),
        )

    def _to_item(self, document: DocumentAsset) -> DocumentItem:
        return DocumentItem.model_validate(document)
