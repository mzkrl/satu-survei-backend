from pydantic import BaseModel, ConfigDict
from uuid import UUID

class UserCreate(BaseModel):
    username: str
    email: str | None = None
    password: str

class UserUpdate(BaseModel):
    username: str | None = None
    email: str | None = None
    password: str | None = None

class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str | None = None
    password: str

    model_config = ConfigDict(from_attributes=True)