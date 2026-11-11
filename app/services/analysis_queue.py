from __future__ import annotations

import datetime as dt
import logging
import os
import socket
import threading
import uuid

from sqlalchemy import func

from app import models
from app.config import settings
from app.database import SessionLocal
from app.services.analyze_pipeline import run_pipeline
from app.services.file_storage import download_pdf

logger = logging.getLogger(__name__)

_WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
_wake_event = threading.Event()
_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None
_start_lock = threading.Lock()


def wake_worker() -> None:
    if getattr(settings, "ANALYSIS_QUEUE_ENABLED", True):
        _wake_event.set()


def start_worker() -> None:
    global _worker_thread
    if not getattr(settings, "ANALYSIS_QUEUE_ENABLED", True):
        logger.info("analysis worker disabled by configuration")
        return
    with _start_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _stop_event.clear()
        _recover_interrupted_jobs()
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="analysis-worker",
            daemon=True,
        )
        _worker_thread.start()
        logger.info("analysis worker started (%s)", _WORKER_ID)


def stop_worker(timeout: float = 5.0) -> None:
    _stop_event.set()
    _wake_event.set()
    thread = _worker_thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
    logger.info("analysis worker stopped")


def _worker_loop() -> None:
    while not _stop_event.is_set():
        try:
            job_id = _claim_next_job()
            if job_id is None:
                _wake_event.wait(max(0.5, float(settings.ANALYSIS_WORKER_POLL_SECONDS)))
                _wake_event.clear()
                continue
            _process_job(job_id)
        except Exception:
            logger.exception("analysis worker loop error")
            _wake_event.wait(max(0.5, float(settings.ANALYSIS_WORKER_POLL_SECONDS)))
            _wake_event.clear()


def _claim_next_job() -> uuid.UUID | None:
    db = SessionLocal()
    try:
        job = (
            db.query(models.AnalysisJob)
            .filter(
                models.AnalysisJob.status == "queued",
                models.AnalysisJob.run_after <= func.now(),
            )
            .order_by(models.AnalysisJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        if job is None:
            db.rollback()
            return None

        now = dt.datetime.now(dt.timezone.utc)
        job.status = "running"
        job.attempts = int(job.attempts or 0) + 1
        job.started_at = now
        job.locked_until = now + dt.timedelta(minutes=30)
        job.worker_id = _WORKER_ID
        db.commit()
        return job.id
    except Exception:
        db.rollback()
        logger.exception("failed to claim an analysis job")
        return None
    finally:
        db.close()


def _process_job(job_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        job = db.get(models.AnalysisJob, job_id)
        if job is None:
            return
        analysis = db.get(models.Analyses, job.analysis_id)
        document = db.get(models.Documents, job.document_id)
        if analysis is None or document is None:
            raise RuntimeError("analysis or document record is missing")

        analysis.status = "processing"
        document.status = "processing"
        db.commit()

        pdf_bytes = download_pdf(document.file)
        run_pipeline(db, analysis, document, pdf_bytes)

        db.refresh(analysis)
        if analysis.status != "completed":
            raise RuntimeError("pipeline stopped before completing the analysis")

        job.status = "completed"
        job.finished_at = dt.datetime.now(dt.timezone.utc)
        job.locked_until = None
        job.last_error = None
        db.commit()
        logger.info("analysis job completed: %s", job.id)
    except Exception as exc:
        db.rollback()
        logger.exception("analysis job failed: %s", job_id)
        _mark_job_failed(db, job_id, exc)
    finally:
        db.close()


def _mark_job_failed(db, job_id: uuid.UUID, exc: Exception) -> None:
    try:
        job = db.get(models.AnalysisJob, job_id)
        if job is None:
            return
        analysis = db.get(models.Analyses, job.analysis_id)
        document = db.get(models.Documents, job.document_id)
        if analysis is not None:
            analysis.status = "failed"
        if document is not None:
            document.status = "failed"
        job.status = "failed"
        job.last_error = (str(exc) or exc.__class__.__name__)[:2000]
        job.finished_at = dt.datetime.now(dt.timezone.utc)
        job.locked_until = None
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("failed to persist failure for job %s", job_id)


def _recover_interrupted_jobs() -> None:
    """Requeue jobs left running by a previous process, cleaning partial output."""
    db = SessionLocal()
    try:
        running_jobs = (
            db.query(models.AnalysisJob)
            .filter(models.AnalysisJob.status == "running")
            .all()
        )
        for job in running_jobs:
            analysis = db.get(models.Analyses, job.analysis_id)
            if analysis is not None and analysis.status == "completed":
                job.status = "completed"
                job.finished_at = dt.datetime.now(dt.timezone.utc)
                job.locked_until = None
                continue

            if int(job.attempts or 0) >= int(job.max_attempts or 1):
                analysis = db.get(models.Analyses, job.analysis_id)
                document = db.get(models.Documents, job.document_id)
                if analysis is not None:
                    analysis.status = "failed"
                if document is not None:
                    document.status = "failed"
                job.status = "failed"
                job.last_error = "Worker stopped before the job could be retried"
                job.finished_at = dt.datetime.now(dt.timezone.utc)
                job.locked_until = None
                continue

            _cleanup_partial_work(db, job.analysis_id, job.document_id)
            analysis = db.get(models.Analyses, job.analysis_id)
            document = db.get(models.Documents, job.document_id)
            if analysis is not None:
                analysis.status = "queued"
            if document is not None:
                document.status = "pending"
            job.status = "queued"
            job.started_at = None
            job.locked_until = None
            job.worker_id = None
            logger.warning("requeued interrupted analysis job: %s", job.id)

        if running_jobs:
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("failed to recover interrupted analysis jobs")
    finally:
        db.close()


def _cleanup_partial_work(db, analysis_id, document_id) -> None:
    claim_ids = [
        row[0]
        for row in db.query(models.Claims.id)
        .filter(models.Claims.analysis_id == analysis_id)
        .all()
    ]
    if claim_ids:
        db.query(models.Evaluations).filter(
            models.Evaluations.claim_id.in_(claim_ids)
        ).delete(synchronize_session=False)
        db.query(models.Claims).filter(
            models.Claims.analysis_id == analysis_id
        ).delete(synchronize_session=False)
    db.query(models.Evidence).filter(
        models.Evidence.document_id == document_id
    ).delete(synchronize_session=False)