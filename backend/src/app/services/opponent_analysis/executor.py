from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import logging

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.opponent_analysis.processor import OpponentAnalysisProcessor

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None
_futures: set[Future] = set()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="opponent-analysis"
        )
    return _executor


def _track_future(future: Future) -> None:
    _futures.add(future)
    future.add_done_callback(lambda item: _futures.discard(item))


def run_opponent_analysis_job(run_id: str) -> None:
    session = get_session_factory()()
    try:
        OpponentAnalysisProcessor(session, get_settings()).run(run_id)
    finally:
        session.close()


def submit_opponent_analysis_job(run_id: str) -> None:
    logger.info(
        "Queueing opponent analysis job",
        extra={"event": "opponent_analysis_queued", "run_id": run_id},
    )
    future = _get_executor().submit(run_opponent_analysis_job, run_id)
    _track_future(future)


def shutdown_opponent_analysis_executor() -> None:
    global _executor
    if _executor is None:
        return
    _executor.shutdown(wait=False, cancel_futures=False)
    _executor = None
    _futures.clear()
