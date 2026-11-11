from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ClaimBase(BaseModel):
    statement: str
    category: str | None = None
    status: str = "pending"
    raw_excerpt: str | None = None
    page_number: int | None = Field(default=None, gt=0)


class ClaimCreate(ClaimBase):
    analysis_id: UUID
    document_id: UUID


class ClaimUpdate(BaseModel):
    statement: str | None = None
    category: str | None = None
    status: str | None = None
    raw_excerpt: str | None = None
    page_number: int | None = Field(default=None, gt=0)


class ClaimResponse(ClaimBase):
    id: UUID
    analysis_id: UUID
    document_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
