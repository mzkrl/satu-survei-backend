from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class DocumentInfo(BaseModel):
    title: str | None = None
    publisher: str | None = None
    publication_date: str | date | None = None


class AnalysisSummary(BaseModel):
    total_claims: int
    valid: int
    questionable: int
    invalid: int
    insufficient_evidence: int


class ClaimViz(BaseModel):
    claim_id: str
    statement: str | None = None
    raw_excerpt: str | None = None
    page_number: int | None = None
    verdict: str
    confidence: float | None = None
    explanation: str | None = None
    evidence: list[Any] = []
    metrics: dict[str, Any] = {}
    limitations: list[Any] = []


class QCReportSchema(BaseModel):
    status: str
    issues: list[Any] = []
    corrections: list[str] = []


class Visualizations(BaseModel):
    verdict_distribution: list[dict[str, Any]] = []
    statistical_comparisons: list[dict[str, Any]] = []
    time_series: list[dict[str, Any]] = []


class AnalyzeResponse(BaseModel):
    analysis_id: str
    document: DocumentInfo
    summary: AnalysisSummary
    claims: list[ClaimViz]
    visualizations: Visualizations
    quality_control: QCReportSchema
