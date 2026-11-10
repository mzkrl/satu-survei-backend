from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ClaimBase(BaseModel):
    statement: str
    category: str | None = None
    status: str = "pending"


class ClaimCreate(ClaimBase):
    analysis_id: UUID


class ClaimUpdate(BaseModel):
    statement: str | None = None
    category: str | None = None
    status: str | None = None


class ClaimResponse(ClaimBase):
    id: UUID
    analysis_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
