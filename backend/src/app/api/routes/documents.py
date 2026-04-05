from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.document import (
    BatchDeleteRequest,
    DocumentListResponse,
    DocumentOperationResponse,
    DocumentPreviewResponse,
    VectorizeRequest,
)
from app.services.documents.service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


def get_document_service(
    db=Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentService:
    return DocumentService(db=db, settings=settings)


@router.get("", response_model=DocumentListResponse)
def list_documents(
    service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    return service.list_documents()


@router.post("/upload", response_model=DocumentOperationResponse)
def upload_documents(
    files: list[UploadFile] = File(...),
    service: DocumentService = Depends(get_document_service),
) -> DocumentOperationResponse:
    return service.upload_documents(files)


@router.post("/vectorize", response_model=DocumentOperationResponse)
def queue_vectorization(
    request: VectorizeRequest,
    service: DocumentService = Depends(get_document_service),
) -> DocumentOperationResponse:
    return service.queue_vectorization(request.document_ids)


@router.post("/delete", response_model=DocumentOperationResponse)
def batch_delete_documents(
    request: BatchDeleteRequest,
    service: DocumentService = Depends(get_document_service),
) -> DocumentOperationResponse:
    return service.soft_delete_documents(request.document_ids)


@router.delete("/{document_id}", response_model=DocumentOperationResponse)
def delete_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> DocumentOperationResponse:
    return service.soft_delete_documents([document_id])


@router.get("/{document_id}/preview", response_model=DocumentPreviewResponse)
def get_document_preview(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> DocumentPreviewResponse:
    return service.get_document_preview(document_id)


@router.get("/{document_id}/file")
def get_document_file(
    document_id: str,
    preview: bool = Query(default=False),
    disposition: str = Query(default="attachment"),
    service: DocumentService = Depends(get_document_service),
) -> FileResponse:
    path, media_type, filename = service.resolve_document_file_path(
        document_id,
        preview=preview,
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline" if disposition == "inline" else "attachment",
    )
