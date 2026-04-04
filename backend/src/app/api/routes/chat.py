import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

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


@router.post("/stream")
def answer_question_stream(
    request: AnswerRequest,
    service: DocumentAnswerService = Depends(get_answer_service),
) -> StreamingResponse:
    def event_generator():
        try:
            for event in service.stream_answer(
                query=request.query,
                top_k=request.top_k,
                document_ids=request.document_ids,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            error_event = {"type": "error", "content": str(exc)}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
