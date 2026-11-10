from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AnalysisBase(BaseModel):
    title: str
    status: str = "draft"


class AnalysisCreate(AnalysisBase):
    user_id: UUID


class AnalysisUpdate(BaseModel):
    title: str | None = None
    status: str | None = None


class AnalysisResponse(AnalysisBase):
    id: UUID
    user_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
