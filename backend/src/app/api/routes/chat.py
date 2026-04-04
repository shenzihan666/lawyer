from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.answer import AnswerRequest, AnswerResponse
from app.services.answers import DocumentAnswerService

router = APIRouter(prefix="/chat", tags=["chat"])


def get_answer_service(
    db=Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentAnswerService:
    return DocumentAnswerService(db=db, settings=settings)


@router.post("/answer", response_model=AnswerResponse)
def answer_question(
    request: AnswerRequest,
    service: DocumentAnswerService = Depends(get_answer_service),
) -> AnswerResponse:
    return service.answer(
        query=request.query,
        top_k=request.top_k,
        document_ids=request.document_ids,
    )
