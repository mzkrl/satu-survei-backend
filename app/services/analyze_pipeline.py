from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.services import document_extraction as doc_svc
from app.services.evidence_extraction import extract_evidence
from app.agents.claim_extraction import extract_claims
from app.agents.analysis import evaluate_claim
from app.agents.quality_control import run_quality_control
from app.services.visualization import build_visualization

logger = logging.getLogger(__name__)


def _json_safe(obj: Any) -> Any:
    """Convert DB values (Decimal/date/UUID) without losing integers."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    if hasattr(obj, "hex") and hasattr(obj, "int"):  # UUID
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    return obj


def run_pipeline(db: Session, analysis: models.Analyses, document: models.Documents, pdf_bytes: bytes) -> dict[str, Any]:
    # Stage 2: extraction
    document.status = "processing"
    analysis.status = "processing"
    db.commit()
    try:
        extraction = doc_svc.extract_document(pdf_bytes, document_id=str(document.id))
        md = extraction.metadata or {}
        if md.get("title") and not document.title:
            document.title = md.get("title")
        if md.get("publisher") and not document.publisher:
            document.publisher = md.get("publisher")
        if md.get("publication_date") and not document.publication_date:
            document.publication_date = md.get("publication_date")
        document.extracted_text = extraction.full_text
        document.status = "completed"
        db.commit()
        db.refresh(document)
    except Exception:
        logger.exception("document extraction failed")
        document.status = "failed"
        analysis.status = "failed"
        db.commit()
        raise

    # Stage 3: claim extraction
    try:
        claim_result = extract_claims(extraction.full_text)
        claim_models: list[models.Claims] = []
        seen = set()
        for c in claim_result.claims:
            key = (c.statement or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            cm = models.Claims(
                analysis_id=analysis.id,
                document_id=document.id,
                statement=c.statement,
                category=c.category,
                status="pending",
                raw_excerpt=c.raw_excerpt,
                page_number=c.page_number,
            )
            db.add(cm)
            claim_models.append(cm)
        db.commit()
        for cm in claim_models:
            db.refresh(cm)
    except Exception:
        logger.exception("claim extraction failed")
        analysis.status = "failed"
        db.commit()
        raise

    # Stage 3b: evidence extraction & normalization
    try:
        extracted_evidence = extract_evidence(extraction.full_text)
        evidence_rows: list[models.Evidence] = []
        for ev in extracted_evidence:
            er = models.Evidence(
                document_id=document.id,
                metric=ev.metric,
                value=ev.value,
                unit=ev.unit,
                population=None,
                geography=ev.geography,
                period=ev.period,
                sample_size=None,
                raw_excerpt=ev.raw_excerpt,
                page_number=ev.page_number,
                metadata_={"raw_value": ev.raw_value},
            )
            db.add(er)
            evidence_rows.append(er)
        db.commit()
        for er in evidence_rows:
            db.refresh(er)
        logger.info("evidence counts: extracted=%s persisted=%s", len(extracted_evidence), len(evidence_rows))
    except Exception:
        logger.exception("evidence extraction failed")
        analysis.status = "failed"
        db.commit()
        raise

    # Stage 4: analysis/evaluation (preserve history by appending rows)
    try:
        eval_models: list[models.Evaluations] = []
        ev_payloads = [
            {
                "id": str(e.id),
                "metric": e.metric,
                "value": float(e.value) if e.value is not None else None,
                "raw_value": (e.metadata_ or {}).get("raw_value") if isinstance(getattr(e, "metadata_", None), dict) else None,
                "unit": e.unit,
                "population": e.population,
                "geography": e.geography,
                "period": e.period,
                "sample_size": e.sample_size,
                "raw_excerpt": e.raw_excerpt,
                "page_number": e.page_number,
                "document_id": str(e.document_id),
            }
            for e in evidence_rows
        ]
        for cm in claim_models:
            cm.status = "processing"
            db.commit()
            claim_payload = {
                "id": str(cm.id),
                "statement": cm.statement,
                "category": cm.category,
                "raw_excerpt": cm.raw_excerpt,
                "page_number": cm.page_number,
                "document_id": str(cm.document_id),
            }
            ev_res = evaluate_claim(claim_payload, ev_payloads)
            em = models.Evaluations(
                claim_id=cm.id,
                verdict=ev_res.verdict,
                confidence=ev_res.confidence,
                explanation=ev_res.explanation,
                evidence_ids=ev_res.evidence_ids,
                metrics=_json_safe(ev_res.metrics),
                limitations=_json_safe(ev_res.limitations),
            )
            db.add(em)
            cm.status = "evaluated"
            db.commit()
            db.refresh(em)
            eval_models.append(em)
        if not claim_models:
            pass
    except Exception:
        logger.exception("analysis failed")
        analysis.status = "failed"
        db.commit()
        raise

    # Stage 5: quality control
    try:
        claims_payload = [
            {
                "id": str(c.id),
                "statement": c.statement,
                "raw_excerpt": c.raw_excerpt,
                "page_number": c.page_number,
                "document_id": str(c.document_id),
            }
            for c in claim_models
        ]
        evals_payload = [
            {
                "id": str(e.id),
                "claim_id": str(e.claim_id),
                "verdict": e.verdict,
                "confidence": float(e.confidence) if e.confidence is not None else None,
                "explanation": e.explanation,
                "evidence_ids": e.evidence_ids or [],
                "metrics": e.metrics or {},
                "limitations": e.limitations or [],
            }
            for e in eval_models
        ]
        evidence_payload = ev_payloads
        evidence_by_id = {str(e["id"]): e for e in evidence_payload}
        valid_evidence_ids = set(evidence_by_id.keys())
        doc_pages = {p.page_number for p in extraction.pages}
        logger.info("qc counts: claims=%s evaluations=%s evidence=%s", len(claims_payload), len(evals_payload), len(evidence_payload))
        qc = run_quality_control(
            claims_payload,
            evals_payload,
            evidence_payload,
            doc_pages,
            valid_evidence_ids,
            evidence_by_id,
        )
        for e in eval_models:
            for ep in evals_payload:
                if str(e.id) == ep.get("id"):
                    e.confidence = ep.get("confidence")
                    e.verdict = ep.get("verdict")
                    e.limitations = ep.get("limitations") or []
                    break
        db.commit()
        qc_report = _json_safe(qc.model_dump())
    except Exception:
        logger.exception("quality control failed")
        analysis.status = "failed"
        db.commit()
        raise

    # Stage 6: visualization
    try:
        evaluations_by_claim = {}
        for e in eval_models:
            evaluations_by_claim[str(e.claim_id)] = {
                "verdict": e.verdict,
                "confidence": float(e.confidence) if e.confidence is not None else None,
                "explanation": e.explanation,
                "evidence_ids": e.evidence_ids or [],
                "metrics": e.metrics or {},
                "limitations": e.limitations or [],
            }
        doc_info = {
            "title": document.title or (extraction.metadata or {}).get("title"),
            "publisher": document.publisher or (extraction.metadata or {}).get("publisher"),
            "publication_date": (
                document.publication_date.isoformat()
                if document.publication_date
                else (extraction.metadata or {}).get("publication_date")
            ),
        }
        result = build_visualization(
            analysis_id=str(analysis.id),
            document=_json_safe(doc_info),
            claims=_json_safe(claims_payload),
            evaluations_by_claim=_json_safe(evaluations_by_claim),
            evidence_by_id=_json_safe(evidence_by_id),
            qc_report=qc_report,
        )
        analysis.status = "completed"
        db.commit()
        return result
    except Exception:
        logger.exception("visualization failed")
        analysis.status = "failed"
        db.commit()
        raise
