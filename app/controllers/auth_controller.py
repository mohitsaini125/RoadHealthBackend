from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse
from app.services import auth_service


def signup(db: Session, payload: SignupRequest) -> User:
    try:
        return auth_service.signup(db, payload)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def login(db: Session, payload: LoginRequest) -> TokenResponse:
    try:
        user = auth_service.authenticate(db, payload)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    token, expires_in = auth_service.issue_token(user)
    return TokenResponse(access_token=token, expires_in_minutes=expires_in)


def get_me(current_user: User) -> User:
    return current_user
