from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.agents.quality_control import run_quality_control
from app.services.analyze_pipeline import _json_safe
from app.services.visualization import build_visualization


def _latest_evaluations(
    db: Session, analysis_id: Any
) -> dict[str, models.Evaluations]:
    """Return the newest evaluation for every claim in an analysis."""
    rows = (
        db.query(models.Evaluations)
        .join(models.Claims, models.Evaluations.claim_id == models.Claims.id)
        .filter(models.Claims.analysis_id == analysis_id)
        .order_by(models.Evaluations.created_at.asc())
        .all()
    )
    latest: dict[str, models.Evaluations] = {}
    # Ascending order means the last row for a claim is the newest one.
    for row in rows:
        latest[str(row.claim_id)] = row
    return latest


def _document_pages(extracted_text: str | None, page_numbers: set[int]) -> set[int]:
    pages = {int(n) for n in re.findall(r"\[Page (\d+)\]", extracted_text or "")}
    pages |= {p for p in page_numbers if p is not None}
    return pages


def build_analysis_result(db: Session, analysis: models.Analyses) -> dict[str, Any]:
    """Rebuild the same response shape as POST /analyze from persisted rows."""
    document = (
        db.query(models.Documents)
        .filter(models.Documents.analysis_id == analysis.id)
        .order_by(models.Documents.created_at.asc())
        .first()
    )
    claims = (
        db.query(models.Claims)
        .filter(models.Claims.analysis_id == analysis.id)
        .order_by(models.Claims.created_at.asc())
        .all()
    )
    latest_evaluations = _latest_evaluations(db, analysis.id)
    evidence = (
        db.query(models.Evidence)
        .filter(models.Evidence.document_id == document.id)
        .order_by(models.Evidence.created_at.asc())
        .all()
        if document
        else []
    )

    evidence_payload = [
        {
            "id": str(item.id),
            "metric": item.metric,
            "value": float(item.value) if item.value is not None else None,
            "raw_value": (item.metadata_ or {}).get("raw_value")
            if isinstance(item.metadata_, dict)
            else None,
            "unit": item.unit,
            "population": item.population,
            "geography": item.geography,
            "period": item.period,
            "sample_size": item.sample_size,
            "raw_excerpt": item.raw_excerpt,
            "page_number": item.page_number,
            "document_id": str(item.document_id),
        }
        for item in evidence
    ]
    evidence_by_id = {row["id"]: row for row in evidence_payload}

    claims_payload = [
        {
            "id": str(claim.id),
            "statement": claim.statement,
            "category": claim.category,
            "raw_excerpt": claim.raw_excerpt,
            "page_number": claim.page_number,
            "document_id": str(claim.document_id),
        }
        for claim in claims
    ]

    evaluations_by_claim: dict[str, dict[str, Any]] = {}
    evaluations_payload: list[dict[str, Any]] = []
    for claim in claims:
        cid = str(claim.id)
        evaluation = latest_evaluations.get(cid)
        if evaluation is None:
            evaluations_by_claim[cid] = {
                "verdict": "insufficient_evidence",
                "confidence": None,
                "explanation": "This claim has not been evaluated yet.",
                "evidence_ids": [],
                "metrics": {},
                "limitations": ["Evaluation is not available for this claim."],
            }
            continue
        payload = {
            "id": str(evaluation.id),
            "claim_id": cid,
            "verdict": evaluation.verdict,
            "confidence": float(evaluation.confidence)
            if evaluation.confidence is not None
            else None,
            "explanation": evaluation.explanation,
            "evidence_ids": evaluation.evidence_ids or [],
            "metrics": evaluation.metrics or {},
            "limitations": evaluation.limitations or [],
        }
        evaluations_by_claim[cid] = payload
        evaluations_payload.append(payload)

    page_numbers = {
        int(p)
        for p in (
            [claim.page_number for claim in claims]
            + [item.page_number for item in evidence]
        )
        if p is not None
    }
    document_pages = _document_pages(
        document.extracted_text if document else None, page_numbers
    )
    qc_report = run_quality_control(
        claims_payload,
        evaluations_payload,
        evidence_payload,
        document_pages,
        set(evidence_by_id),
        evidence_by_id,
    ).model_dump()

    document_info = {
        "title": document.title if document else analysis.title,
        "publisher": document.publisher if document else None,
        "publication_date": (
            document.publication_date.isoformat()
            if document and document.publication_date
            else None
        ),
    }
    result = build_visualization(
        analysis_id=str(analysis.id),
        document=document_info,
        claims=claims_payload,
        evaluations_by_claim=evaluations_by_claim,
        evidence_by_id=evidence_by_id,
        qc_report=qc_report,
    )
    result["quality_control"] = _json_safe(qc_report)
    return _json_safe(result)


def summary_for_analysis(db: Session, analysis: models.Analyses) -> dict[str, int]:
    result = build_analysis_result(db, analysis)
    summary = result.get("summary") or {}
    return {
        "total_claims": int(summary.get("total_claims", 0)),
        "valid": int(summary.get("valid", 0)),
        "questionable": int(summary.get("questionable", 0)),
        "invalid": int(summary.get("invalid", 0)),
        "insufficient_evidence": int(summary.get("insufficient_evidence", 0)),
    }
