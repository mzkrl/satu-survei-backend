from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.utils.security import hash_password, verify_password, create_access_token
from app.database import get_db
from app import models
from app import schemas

router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)

@router.post("/register", status_code=201)
def register(
    user_data: schemas.UserRegister,
    db: Session = Depends(get_db)
):
    existing_user = db.query(models.Users).filter(
        (models.Users.username == user_data.username)
    ).first()

    if not existing_user and user_data.email:
        existing_user = db.query(models.Users).filter(
            models.Users.email == user_data.email
        ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Username or email already registered"
        )

    new_user = models.Users(
        username=user_data.username,
        email=user_data.email,
        password=hash_password(user_data.password)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "Registration successful",
        "user_id": new_user.id
    }

@router.post("/login", response_model=schemas.TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    identifier = form_data.username
    user = db.query(models.Users).filter(
        or_(models.Users.username == identifier, models.Users.email == identifier)
    ).first()

    if not user or not verify_password(
        form_data.password,
        user.password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    access_token = create_access_token(
        data={"sub": str(user.id)}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }