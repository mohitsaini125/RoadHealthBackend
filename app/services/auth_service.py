"""Business rules for signup/login. No FastAPI/HTTP concerns here."""
from app.models.enums import UserRole
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest
from app.utils.jwt import create_access_token
from app.utils.security import hash_password, verify_password


class AuthError(Exception):
    """Raised for invalid credentials or duplicate accounts."""


def signup(db: Session, payload: SignupRequest) -> User:
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise AuthError("An account with this email already exists.")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        role=UserRole.CITIZEN,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, payload: LoginRequest) -> User:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise AuthError("Invalid email or password.")
    return user


def issue_token(user: User) -> tuple[str, int]:
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value, "authority_id": str(user.authority_id) if user.authority_id else None},
    )
    return token, settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
