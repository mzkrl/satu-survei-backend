import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.schemas.analyze import AnalyzeResponse
from app.services.file_storage import upload_pdf, StorageError
from app.services.document_extraction import validate_pdf_signature
from app.services.analyze_pipeline import run_pipeline
from app.utils.security import get_current_user
from app.config import settings

router = APIRouter(tags=["Analyze"])
logger = logging.getLogger(__name__)

MAX_UPLOAD = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.Users = Depends(get_current_user),
):
    # Stage 1: validation
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    if file.content_type not in ("application/pdf", "application/x-pdf", "binary/octet-stream"):
        # allow octet-stream but enforce signature
        pass
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="File exceeds upload limit")
    if not validate_pdf_signature(data):
        raise HTTPException(status_code=400, detail="Invalid PDF file signature")

    safe_name = f"{uuid.uuid4()}.pdf"
    try:
        storage_key = upload_pdf(data, safe_name)
    except Exception as e:
        logger.exception("file upload failed")
        raise HTTPException(status_code=500, detail="Failed to store uploaded file") from e

    # create records
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

    try:
        result = run_pipeline(db, analysis, document, data)
        # re-query to ensure status reflected
        db.refresh(analysis)
        db.refresh(document)
        if analysis.status != "completed":
            raise HTTPException(status_code=500, detail="Analysis did not complete successfully")
        return result
    except HTTPException:
        db.rollback()
        raise
    except ValueError as e:
        db.rollback()
        analysis.status = "failed"
        document.status = "failed"
        db.commit()
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("analyze pipeline failed")
        db.rollback()
        # mark failed if records exist
        try:
            a = db.get(models.Analyses, analysis.id)
            d = db.get(models.Documents, document.id)
            if a:
                a.status = "failed"
            if d and d.status != "failed":
                d.status = "failed"
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=500, detail="Internal analysis failure") from e
