from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvidenceBase(BaseModel):
    metric: str
    value: Decimal
    unit: str | None = None
    population: str | None = None
    geography: str | None = None
    period: str | None = None
    sample_size: int | None = Field(default=None, ge=0)
    raw_excerpt: str | None = None
    page_number: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceCreate(EvidenceBase):
    document_id: UUID


class EvidenceUpdate(BaseModel):
    metric: str | None = None
    value: Decimal | None = None
    unit: str | None = None
    population: str | None = None
    geography: str | None = None
    period: str | None = None
    sample_size: int | None = Field(default=None, ge=0)
    raw_excerpt: str | None = None
    page_number: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] | None = None


class EvidenceResponse(EvidenceBase):
    id: UUID
    document_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
