import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import authority_controller
from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.schemas.authority import AuthorityCreate, AuthorityResponse, ZoneCreate, ZoneResponse

router = APIRouter(prefix="/authorities", tags=["Authorities"])


@router.post("", response_model=AuthorityResponse, status_code=201)
def create_authority(
    payload: AuthorityCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return authority_controller.create_authority(db, payload)


@router.get("", response_model=list[AuthorityResponse])
def list_authorities(db: Session = Depends(get_db)):
    return authority_controller.list_authorities(db)


@router.get("/{authority_id}", response_model=AuthorityResponse)
def get_authority(authority_id: uuid.UUID, db: Session = Depends(get_db)):
    return authority_controller.get_authority(db, authority_id)


@router.post("/zones", response_model=ZoneResponse, status_code=201)
def create_zone(
    payload: ZoneCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return authority_controller.create_zone(db, payload)
