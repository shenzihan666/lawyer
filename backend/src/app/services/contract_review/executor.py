from concurrent.futures import Future, ThreadPoolExecutor
import logging

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.contract_review.processor import ContractReviewProcessor

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None
_futures: set[Future] = set()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="contract-review"
        )
    return _executor


def _track_future(future: Future) -> None:
    _futures.add(future)
    future.add_done_callback(lambda item: _futures.discard(item))


def run_review_job(job_id: str) -> None:
    session = get_session_factory()()
    try:
        processor = ContractReviewProcessor(session, get_settings())
        processor.run(job_id)
    finally:
        session.close()


def submit_review_job(job_id: str) -> None:
    logger.info(
        "Queueing contract review job",
        extra={"event": "contract_review_job_queued", "job_id": job_id},
    )
    future = _get_executor().submit(run_review_job, job_id)
    _track_future(future)


def shutdown_contract_review_executor() -> None:
    global _executor
    if _executor is None:
        return
    _executor.shutdown(wait=False, cancel_futures=False)
    _executor = None
    _futures.clear()
