from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


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
    evidence: list[Any] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    limitations: list[Any] = Field(default_factory=list)


class QCReportSchema(BaseModel):
    status: str
    issues: list[Any] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)
    needs_reevaluation: list[str] = Field(default_factory=list)


class Visualizations(BaseModel):
    verdict_distribution: list[dict[str, Any]] = Field(default_factory=list)
    statistical_comparisons: list[dict[str, Any]] = Field(default_factory=list)
    time_series: list[dict[str, Any]] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    analysis_id: str
    document: DocumentInfo
    summary: AnalysisSummary
    claims: list[ClaimViz]
    visualizations: Visualizations
    quality_control: QCReportSchema


class AnalysisListItem(BaseModel):
    analysis_id: str
    title: str
    filename: str | None = None
    status: str
    created_at: datetime
    summary: AnalysisSummary


class AnalyzeQueuedResponse(BaseModel):
    analysis_id: str
    job_id: str | None = None
    status: str
    deduplicated: bool = False


class AnalysisStatusResponse(BaseModel):
    analysis_id: str
    status: str
    error: str | None = None


class ShareLinkResponse(BaseModel):
    analysis_id: str
    share_token: str
    share_url: str | None = None
    shared_at: datetime | None = None
