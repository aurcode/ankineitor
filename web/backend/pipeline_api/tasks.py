from __future__ import annotations

from celery import shared_task
from loguru import logger

from .services import execute_pipeline_run, mark_run_error, mark_run_retrying


RETRYABLE_EXCEPTIONS = (TimeoutError, ConnectionError)


@shared_task(bind=True, max_retries=2, default_retry_delay=5)
def run_pipeline_task(self, run_id: str) -> None:
    try:
        execute_pipeline_run(run_id)
    except RETRYABLE_EXCEPTIONS as exc:
        if self.request.retries < self.max_retries:
            message = f"Transient failure on attempt {self.request.retries + 1}: {exc}"
            logger.warning("Retrying pipeline run {} due to transient error: {}", run_id, exc)
            mark_run_retrying(run_id, message)
            raise self.retry(exc=exc, countdown=5 * (2 ** self.request.retries))

        mark_run_error(run_id, f"Transient failure after retries: {exc}")
        raise
    except Exception as exc:
        logger.exception("Pipeline run {} failed: {}", run_id, exc)
        mark_run_error(run_id, str(exc))
        raise
