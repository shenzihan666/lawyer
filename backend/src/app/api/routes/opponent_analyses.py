from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.opponent_analysis import (
    OpponentAnalysisDetailResponse,
    OpponentAnalysisListResponse,
    OpponentAnalysisRunCreateRequest,
)
from app.services.opponent_analysis.service import OpponentAnalysisService

router = APIRouter(prefix="/opponent-analyses", tags=["opponent-analyses"])


def get_opponent_analysis_service(
    db=Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> OpponentAnalysisService:
    return OpponentAnalysisService(db=db, settings=settings)


@router.get("", response_model=OpponentAnalysisListResponse)
def list_opponent_analyses(
    service: OpponentAnalysisService = Depends(get_opponent_analysis_service),
) -> OpponentAnalysisListResponse:
    return service.list_runs()


@router.post(
    "",
    response_model=OpponentAnalysisDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_opponent_analysis(
    body: OpponentAnalysisRunCreateRequest,
    service: OpponentAnalysisService = Depends(get_opponent_analysis_service),
) -> OpponentAnalysisDetailResponse:
    return service.create_run(
        case_facts=body.case_facts,
        top_k=body.top_k,
        document_ids=body.document_ids,
    )


@router.get("/{run_id}", response_model=OpponentAnalysisDetailResponse)
def get_opponent_analysis(
    run_id: str,
    service: OpponentAnalysisService = Depends(get_opponent_analysis_service),
) -> OpponentAnalysisDetailResponse:
    return service.get_run(run_id)


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opponent_analysis(
    run_id: str,
    service: OpponentAnalysisService = Depends(get_opponent_analysis_service),
) -> Response:
    service.delete_run(run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{run_id}/stream")
async def stream_opponent_analysis(
    run_id: str,
    after_seq: int = Query(default=0, ge=0),
    service: OpponentAnalysisService = Depends(get_opponent_analysis_service),
):
    terminal_statuses = {"completed", "failed"}

    async def event_generator():
        latest_emitted_seq = after_seq
        snapshot = service.get_stream_snapshot(run_id)
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "snapshot",
                    "run": snapshot.run.model_dump(mode="json"),
                    "summary": snapshot.summary.model_dump(mode="json"),
                    "latest_seq": snapshot.latest_seq,
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )

        while True:
            events = service.get_events_after(run_id, latest_emitted_seq)
            for event in events:
                latest_emitted_seq = max(latest_emitted_seq, event.seq)
                yield (
                    "data: "
                    + json.dumps(
                        {"type": "event", "event": event.model_dump(mode="json")},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )

            snapshot = service.get_stream_snapshot(run_id)
            if (
                snapshot.run.status in terminal_statuses
                and latest_emitted_seq >= snapshot.latest_seq
            ):
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "done",
                            "run": snapshot.run.model_dump(mode="json"),
                            "summary": snapshot.summary.model_dump(mode="json"),
                            "latest_seq": snapshot.latest_seq,
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                yield "data: [DONE]\n\n"
                break

            await asyncio.sleep(0.45)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
