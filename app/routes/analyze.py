import datetime as dt
import logging
import secrets
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.schemas.analyze import (
    AnalysisListItem,
    AnalysisStatusResponse,
    AnalyzeQueuedResponse,
    AnalyzeResponse,
    ShareLinkResponse,
)
from app.services.analysis_queue import wake_worker
from app.services.analysis_results import (
    build_analysis_result,
    summary_for_analysis,
)
from app.services.document_extraction import validate_pdf_signature
from app.services.file_hash import sha256_bytes
from app.services.file_storage import upload_pdf
from app.utils.security import get_current_user

router = APIRouter(tags=["Analyze"])
logger = logging.getLogger(__name__)

MAX_UPLOAD = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

_EMPTY_SUMMARY = {
    "total_claims": 0,
    "valid": 0,
    "questionable": 0,
    "invalid": 0,
    "insufficient_evidence": 0,
}


def _get_owned_analysis(
    db: Session, analysis_id: str, user: models.Users
) -> models.Analyses:
    try:
        parsed_id = uuid.UUID(analysis_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="Analysis not found") from exc
    analysis = db.get(models.Analyses, parsed_id)
    if analysis is None or analysis.user_id != user.id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


def _find_completed_analysis(
    db: Session, user_id: uuid.UUID, file_hash: str
) -> models.Analyses | None:
    return (
        db.query(models.Analyses)
        .join(models.Documents, models.Documents.analysis_id == models.Analyses.id)
        .filter(
            models.Analyses.user_id == user_id,
            models.Analyses.status == "completed",
            models.Documents.file_hash == file_hash,
        )
        .order_by(models.Analyses.created_at.desc())
        .first()
    )


def _find_active_job(
    db: Session, user_id: uuid.UUID, file_hash: str
) -> models.AnalysisJob | None:
    return (
        db.query(models.AnalysisJob)
        .filter(
            models.AnalysisJob.user_id == user_id,
            models.AnalysisJob.file_hash == file_hash,
            models.AnalysisJob.status.in_(("queued", "running")),
        )
        .order_by(models.AnalysisJob.created_at.desc())
        .first()
    )


def _deduplicated_response(
    analysis_id: uuid.UUID, job: models.AnalysisJob | None, status: str
) -> AnalyzeQueuedResponse:
    return AnalyzeQueuedResponse(
        analysis_id=str(analysis_id),
        job_id=str(job.id) if job is not None else None,
        status=status,
        deduplicated=True,
    )


def _latest_job(db: Session, analysis_id: uuid.UUID) -> models.AnalysisJob | None:
    return (
        db.query(models.AnalysisJob)
        .filter(models.AnalysisJob.analysis_id == analysis_id)
        .order_by(models.AnalysisJob.created_at.desc())
        .first()
    )


def _status_response(
    db: Session, analysis: models.Analyses
) -> AnalysisStatusResponse:
    error = None
    if analysis.status == "failed":
        job = _latest_job(db, analysis.id)
        error = (job.last_error if job and job.last_error else "Analysis failed")[:500]
    return AnalysisStatusResponse(
        analysis_id=str(analysis.id),
        status=analysis.status,
        error=error,
    )


def _share_url(token: str) -> str | None:
    base = (settings.SHARE_BASE_URL or "").strip().rstrip("/")
    return f"{base}/share/{token}" if base else None


@router.post(
    "/analyze",
    response_model=AnalyzeQueuedResponse,
    status_code=202,
)
async def analyze_pdf(
    file: UploadFile = File(...),
    force: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(get_current_user),
):
    # Stage 1: validation
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit",
        )
    if not validate_pdf_signature(data):
        raise HTTPException(status_code=400, detail="Invalid PDF file signature")

    digest = sha256_bytes(data)

    # Never create a second active job for the same user + file.
    active_job = _find_active_job(db, current_user.id, digest)
    if active_job is not None:
        return _deduplicated_response(
            active_job.analysis_id,
            active_job,
            "processing" if active_job.status == "running" else "queued",
        )

    # Identical PDF that already finished: reuse the stored result.
    if not force:
        completed = _find_completed_analysis(db, current_user.id, digest)
        if completed is not None:
            return _deduplicated_response(completed.id, None, "completed")

    safe_name = f"{uuid.uuid4()}.pdf"
    try:
        storage_key = upload_pdf(data, safe_name)
    except Exception as exc:
        logger.exception("file upload failed")
        raise HTTPException(
            status_code=503, detail="Failed to store uploaded file"
        ) from exc

    analysis = models.Analyses(
        user_id=current_user.id,
        title=file.filename or "Uploaded Document",
        status="queued",
    )
    document = models.Documents(
        file=storage_key,
        filename=file.filename or safe_name,
        file_hash=digest,
        status="pending",
    )
    job = models.AnalysisJob(
        user_id=current_user.id,
        file_hash=digest,
        status="queued",
        max_attempts=max(1, int(settings.ANALYSIS_JOB_MAX_ATTEMPTS)),
    )

    try:
        db.add(analysis)
        db.flush()
        document.analysis_id = analysis.id
        db.add(document)
        db.flush()
        job.analysis_id = analysis.id
        job.document_id = document.id
        db.add(job)
        db.commit()
    except IntegrityError:
        db.rollback()
        active_job = _find_active_job(db, current_user.id, digest)
        if active_job is not None:
            return _deduplicated_response(
                active_job.analysis_id,
                active_job,
                "processing" if active_job.status == "running" else "queued",
            )
        raise HTTPException(
            status_code=409,
            detail="An identical upload is already being processed",
        )
    except Exception as exc:
        db.rollback()
        logger.exception("failed to enqueue analysis")
        raise HTTPException(status_code=500, detail="Failed to queue analysis") from exc

    wake_worker()
    logger.info(
        "analysis queued: analysis=%s document=%s hash=%s",
        analysis.id,
        document.id,
        digest[:12],
    )
    return AnalyzeQueuedResponse(
        analysis_id=str(analysis.id),
        job_id=str(job.id),
        status="queued",
        deduplicated=False,
    )


@router.get("/analyses", response_model=list[AnalysisListItem])
def list_analyses(
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(get_current_user),
):
    analyses = (
        db.query(models.Analyses)
        .filter(models.Analyses.user_id == current_user.id)
        .order_by(models.Analyses.created_at.desc())
        .limit(100)
        .all()
    )
    items: list[AnalysisListItem] = []
    for analysis in analyses:
        if analysis.status == "completed":
            try:
                summary = summary_for_analysis(db, analysis)
            except Exception:
                logger.exception("failed to summarize analysis %s", analysis.id)
                summary = dict(_EMPTY_SUMMARY)
        else:
            summary = dict(_EMPTY_SUMMARY)
        document = (
            db.query(models.Documents)
            .filter(models.Documents.analysis_id == analysis.id)
            .order_by(models.Documents.created_at.asc())
            .first()
        )
        items.append(
            AnalysisListItem(
                analysis_id=str(analysis.id),
                title=analysis.title,
                filename=document.filename if document else None,
                status=analysis.status,
                created_at=analysis.created_at,
                summary=summary,
            )
        )
    return items


@router.get(
    "/analyses/{analysis_id}/status",
    response_model=AnalysisStatusResponse,
)
def get_analysis_status(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(get_current_user),
):
    analysis = _get_owned_analysis(db, analysis_id, current_user)
    return _status_response(db, analysis)


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalyzeResponse,
    responses={202: {"model": AnalysisStatusResponse}},
)
def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(get_current_user),
):
    analysis = _get_owned_analysis(db, analysis_id, current_user)
    if analysis.status != "completed":
        # Keep the payload safe for older clients that still render the detail
        # response directly: include an empty result shape alongside the status.
        status_payload = _status_response(db, analysis).model_dump()
        status_payload.update(
            {
                "document": {
                    "title": analysis.title,
                    "publisher": None,
                    "publication_date": None,
                },
                "summary": dict(_EMPTY_SUMMARY),
                "claims": [],
                "visualizations": {
                    "verdict_distribution": [],
                    "statistical_comparisons": [],
                    "time_series": [],
                },
                "quality_control": {
                    "status": "pending",
                    "issues": [],
                    "corrections": [],
                    "needs_reevaluation": [],
                },
            }
        )
        return JSONResponse(status_code=202, content=status_payload)
    return build_analysis_result(db, analysis)


@router.post(
    "/analyses/{analysis_id}/share",
    response_model=ShareLinkResponse,
)
def create_share_link(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(get_current_user),
):
    analysis = _get_owned_analysis(db, analysis_id, current_user)
    if analysis.status != "completed":
        raise HTTPException(
            status_code=409,
            detail="Only completed analyses can be shared",
        )
    if not analysis.share_token:
        analysis.share_token = secrets.token_urlsafe(32)
        analysis.shared_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
        db.refresh(analysis)
    return ShareLinkResponse(
        analysis_id=str(analysis.id),
        share_token=analysis.share_token,
        share_url=_share_url(analysis.share_token),
        shared_at=analysis.shared_at,
    )


@router.delete("/analyses/{analysis_id}/share", status_code=204)
def revoke_share_link(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(get_current_user),
):
    analysis = _get_owned_analysis(db, analysis_id, current_user)
    if analysis.share_token:
        analysis.share_token = None
        analysis.shared_at = None
        db.commit()
    return Response(status_code=204)


@router.get(
    "/public/analyses/{share_token}",
    response_model=AnalyzeResponse,
)
def get_public_analysis(
    share_token: str,
    db: Session = Depends(get_db),
):
    if not share_token or len(share_token) > 64:
        raise HTTPException(status_code=404, detail="Shared analysis not found")
    analysis = (
        db.query(models.Analyses)
        .filter(
            models.Analyses.share_token == share_token,
            models.Analyses.status == "completed",
        )
        .first()
    )
    if analysis is None:
        raise HTTPException(status_code=404, detail="Shared analysis not found")

    response = JSONResponse(content=build_analysis_result(db, analysis))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response