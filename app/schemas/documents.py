from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentBase(BaseModel):
    file: str
    filename: str
    title: str | None = None
    publisher: str | None = None
    publication_date: date | None = None
    source_url: str | None = None
    status: str = "pending"
    extracted_text: str | None = None


class DocumentCreate(DocumentBase):
    analysis_id: UUID


class DocumentUpdate(BaseModel):
    file: str | None = None
    filename: str | None = None
    title: str | None = None
    publisher: str | None = None
    publication_date: date | None = None
    source_url: str | None = None
    status: str | None = None
    extracted_text: str | None = None


class DocumentResponse(DocumentBase):
    id: UUID
    analysis_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
