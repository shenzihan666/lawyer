from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.document import DocumentPreviewResponse
from app.services.case_search import DocumentPreviewService

router = APIRouter(prefix="/case-search-assets", tags=["case-search-assets"])


def get_preview_service(
    db=Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentPreviewService:
    return DocumentPreviewService(db=db, settings=settings)


@router.get("/{asset_id}/preview", response_model=DocumentPreviewResponse)
def get_case_search_asset_preview(
    asset_id: str,
    preview_service: DocumentPreviewService = Depends(get_preview_service),
) -> DocumentPreviewResponse:
    return preview_service.get_case_search_asset_preview(asset_id)


@router.get("/{asset_id}/file")
def get_case_search_asset_file(
    asset_id: str,
    preview: bool = Query(default=False),
    disposition: str = Query(default="attachment"),
    preview_service: DocumentPreviewService = Depends(get_preview_service),
) -> FileResponse:
    path, media_type, filename = preview_service.resolve_case_search_asset_file_path(
        asset_id,
        preview=preview,
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline" if disposition == "inline" else "attachment",
    )
