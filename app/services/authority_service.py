"""Business rules for authorities and zones."""
import uuid

from geoalchemy2.shape import from_shape
from shapely.geometry import Polygon
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.authority import Authority
from app.models.zone import Zone
from app.schemas.authority import AuthorityCreate, ZoneCreate


def create_authority(db: Session, payload: AuthorityCreate) -> Authority:
    authority = Authority(
        name=payload.name,
        level=payload.level,
        parent_authority_id=payload.parent_authority_id,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
    )
    db.add(authority)
    db.commit()
    db.refresh(authority)
    return authority


def list_authorities(db: Session) -> list[Authority]:
    return list(db.execute(select(Authority)).scalars().all())


def get_authority(db: Session, authority_id: uuid.UUID) -> Authority | None:
    return db.get(Authority, authority_id)


def create_zone(db: Session, payload: ZoneCreate) -> Zone:
    polygon = Polygon(payload.boundary_coordinates)
    zone = Zone(
        name=payload.name,
        authority_id=payload.authority_id,
        boundary=from_shape(polygon, srid=4326),
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


def get_next_authority(db: Session, current_authority_id: uuid.UUID) -> Authority | None:
    """Determines the next escalation target from explicit hierarchy data
    (parent_authority_id), never inferred from naming conventions."""
    current = db.get(Authority, current_authority_id)
    if current is None or current.parent_authority_id is None:
        return None
    return db.get(Authority, current.parent_authority_id)
