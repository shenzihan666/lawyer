from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.case_search import CaseSearchDetailResponse, CaseSearchListResponse
from app.services.case_search import CaseSearchService

router = APIRouter(prefix="/case-searches", tags=["case-searches"])


def get_case_search_service(
    db=Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CaseSearchService:
    return CaseSearchService(db=db, settings=settings)


@router.get("", response_model=CaseSearchListResponse)
def list_case_searches(
    service: CaseSearchService = Depends(get_case_search_service),
) -> CaseSearchListResponse:
    return service.list_searches()


@router.post("", response_model=CaseSearchDetailResponse)
def create_case_search(
    query_text: str | None = Form(None),
    top_k: int = Form(5),
    document_ids: list[str] = Form([]),
    file: UploadFile | None = File(None),
    service: CaseSearchService = Depends(get_case_search_service),
) -> CaseSearchDetailResponse:
    return service.create_search(
        query_text=query_text,
        upload=file,
        top_k=top_k,
        document_ids=document_ids,
    )


@router.get("/{search_id}", response_model=CaseSearchDetailResponse)
def get_case_search(
    search_id: str,
    service: CaseSearchService = Depends(get_case_search_service),
) -> CaseSearchDetailResponse:
    return service.get_search(search_id)


@router.delete("/{search_id}", status_code=204)
def delete_case_search(
    search_id: str,
    service: CaseSearchService = Depends(get_case_search_service),
) -> Response:
    service.delete_search(search_id)
    return Response(status_code=204)
