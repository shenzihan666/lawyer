from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.opponent_analysis.processor import OpponentAnalysisProcessor

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="opponent-analysis")


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
    _executor.submit(run_opponent_analysis_job, run_id)
