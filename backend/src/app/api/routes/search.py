from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.search import SearchRequest, SearchResponse
from app.services.vectors import DocumentVectorService

router = APIRouter(prefix="/search", tags=["search"])


def get_vector_service(
    db=Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentVectorService:
    return DocumentVectorService(db=db, settings=settings)


@router.post("", response_model=SearchResponse)
def search_documents(
    request: SearchRequest,
    service: DocumentVectorService = Depends(get_vector_service),
) -> SearchResponse:
    return service.search(
        query=request.query,
        top_k=request.top_k,
        document_ids=request.document_ids,
    )
