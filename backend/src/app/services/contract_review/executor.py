from concurrent.futures import ThreadPoolExecutor
import logging

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.contract_review.processor import ContractReviewProcessor

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="contract-review")


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
    _executor.submit(run_review_job, job_id)
