import uuid
from datetime import datetime

from pydantic import BaseModel


class AuthorityResponse(BaseModel):
    id: uuid.UUID
    name: str
    level: int
    parent_authority_id: uuid.UUID | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthorityCreate(BaseModel):
    name: str
    level: int = 1
    parent_authority_id: uuid.UUID | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class ZoneResponse(BaseModel):
    id: uuid.UUID
    name: str
    authority_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ZoneCreate(BaseModel):
    name: str
    authority_id: uuid.UUID
    # GeoJSON-style polygon: [[lon, lat], [lon, lat], ...] closed ring
    boundary_coordinates: list[list[float]]
