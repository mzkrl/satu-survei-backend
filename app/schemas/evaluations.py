from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["valid", "questionable", "invalid", "insufficient_evidence"]


class EvaluationBase(BaseModel):
    verdict: Verdict
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    explanation: str | None = None
    evidence_ids: list[Any] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    limitations: list[Any] = Field(default_factory=list)


class EvaluationCreate(EvaluationBase):
    claim_id: UUID


class EvaluationUpdate(BaseModel):
    verdict: Verdict | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    explanation: str | None = None
    evidence_ids: list[Any] | None = None
    metrics: dict[str, Any] | None = None
    limitations: list[Any] | None = None


class EvaluationResponse(EvaluationBase):
    id: UUID
    claim_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
