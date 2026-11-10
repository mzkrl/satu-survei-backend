from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.utils.security import get_current_user
from app.database import get_db
from app import models
from app import schemas

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

@router.get("/me", response_model=schemas.UserResponse)
def get_my_profile(
    current_user: models.Users = Depends(get_current_user)
):
    return current_user