from __future__ import annotations

from celery import shared_task
from loguru import logger

from .services import (
    RunCanceledError,
    RunPausedError,
    execute_pipeline_run,
    mark_run_canceled,
    mark_run_error,
    mark_run_paused,
    mark_run_retrying,
)
from .tab_services import run_anki_background_job, run_word_extractor_background_job


RETRYABLE_EXCEPTIONS = (TimeoutError, ConnectionError)


@shared_task(bind=True, max_retries=2, default_retry_delay=5)
def run_pipeline_task(self, run_id: str) -> None:
    try:
        execute_pipeline_run(run_id)
    except RunPausedError as exc:
        logger.info("Pipeline run {} paused: {}", run_id, exc)
        mark_run_paused(run_id, str(exc), record_event=False)
        return
    except RunCanceledError as exc:
        logger.info("Pipeline run {} canceled: {}", run_id, exc)
        mark_run_canceled(run_id, str(exc), record_event=False)
        return
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


@shared_task(bind=True, max_retries=1, default_retry_delay=5)
def run_anki_background_job_task(self, job_id: str) -> None:
    try:
        run_anki_background_job(job_id)
    except RETRYABLE_EXCEPTIONS as exc:
        if self.request.retries < self.max_retries:
            logger.warning("Retrying anki background job {} after transient error: {}", job_id, exc)
            raise self.retry(exc=exc, countdown=5 * (2 ** self.request.retries))
        raise
    except Exception as exc:
        logger.exception("Anki background job {} failed: {}", job_id, exc)
        raise


@shared_task(bind=True, max_retries=1, default_retry_delay=5)
def run_word_extractor_background_job_task(self, job_id: str) -> None:
    try:
        run_word_extractor_background_job(job_id)
    except RETRYABLE_EXCEPTIONS as exc:
        if self.request.retries < self.max_retries:
            logger.warning(
                "Retrying word extractor background job {} after transient error: {}",
                job_id,
                exc,
            )
            raise self.retry(exc=exc, countdown=5 * (2 ** self.request.retries))
        raise
    except Exception as exc:
        logger.exception("Word extractor background job {} failed: {}", job_id, exc)
        raise
