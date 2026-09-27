import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.authority import Authority
from app.models.zone import Zone
from app.schemas.authority import AuthorityCreate, ZoneCreate
from app.services import authority_service


def create_authority(db: Session, payload: AuthorityCreate) -> Authority:
    return authority_service.create_authority(db, payload)


def list_authorities(db: Session) -> list[Authority]:
    return authority_service.list_authorities(db)


def get_authority(db: Session, authority_id: uuid.UUID) -> Authority:
    authority = authority_service.get_authority(db, authority_id)
    if authority is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Authority not found.")
    return authority


def create_zone(db: Session, payload: ZoneCreate) -> Zone:
    authority = authority_service.get_authority(db, payload.authority_id)
    if authority is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Authority not found.")
    if len(payload.boundary_coordinates) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A zone boundary needs at least 3 coordinates.",
        )
    return authority_service.create_zone(db, payload)
