import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.schemas.analyze import AnalysisListItem, AnalyzeResponse
from app.services.analysis_results import (
    build_analysis_result,
    summary_for_analysis,
)
from app.services.analyze_pipeline import run_pipeline
from app.services.document_extraction import validate_pdf_signature
from app.services.file_storage import upload_pdf
from app.utils.security import get_current_user

router = APIRouter(tags=["Analyze"])
logger = logging.getLogger(__name__)

MAX_UPLOAD = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


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


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_pdf(
    file: UploadFile = File(...),
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
        status="processing",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    document = models.Documents(
        analysis_id=analysis.id,
        file=storage_key,
        filename=file.filename or safe_name,
        status="pending",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    analysis_id = analysis.id
    document_id = document.id
    try:
        result = run_pipeline(db, analysis, document, data)
    except ValueError as exc:
        db.rollback()
        _mark_failed(db, analysis_id, document_id)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("analyze pipeline failed")
        db.rollback()
        _mark_failed(db, analysis_id, document_id)
        raise HTTPException(status_code=500, detail="Internal analysis failure") from exc

    db.refresh(analysis)
    db.refresh(document)
    if analysis.status != "completed":
        raise HTTPException(status_code=500, detail="Analysis did not complete successfully")
    return result


def _mark_failed(db: Session, analysis_id: uuid.UUID, document_id: uuid.UUID) -> None:
    try:
        analysis = db.get(models.Analyses, analysis_id)
        document = db.get(models.Documents, document_id)
        if analysis is not None:
            analysis.status = "failed"
        if document is not None:
            document.status = "failed"
        db.commit()
    except Exception:
        db.rollback()


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
        try:
            summary = summary_for_analysis(db, analysis)
        except Exception:
            logger.exception("failed to summarize analysis %s", analysis.id)
            summary = {
                "total_claims": 0,
                "valid": 0,
                "questionable": 0,
                "invalid": 0,
                "insufficient_evidence": 0,
            }
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


@router.get("/analyses/{analysis_id}", response_model=AnalyzeResponse)
def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(get_current_user),
):
    analysis = _get_owned_analysis(db, analysis_id, current_user)
    return build_analysis_result(db, analysis)
