"""
All spatial logic lives here — routes and controllers never touch PostGIS directly.
"""
import uuid

from geoalchemy2 import functions as geo_func
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.report import Report
from app.models.zone import Zone

DUPLICATE_REPORT_RADIUS_METERS = 25


def make_point(latitude: float, longitude: float):
    """Builds a PostGIS-ready Point geometry (SRID 4326) from lat/lon."""
    return from_shape(Point(longitude, latitude), srid=4326)


def find_zone_for_point(db: Session, latitude: float, longitude: float) -> Zone | None:
    """Finds the zone whose polygon boundary contains the given point."""
    point = make_point(latitude, longitude)
    stmt = select(Zone).where(geo_func.ST_Contains(Zone.boundary, point)).limit(1)
    return db.execute(stmt).scalar_one_or_none()


def find_nearby_reports(
    db: Session,
    latitude: float,
    longitude: float,
    radius_meters: float = DUPLICATE_REPORT_RADIUS_METERS,
    exclude_resolved: bool = True,
) -> list[Report]:
    """
    Finds existing reports within `radius_meters` of the given point — used
    for duplicate/related-report detection at submission time.
    """
    point = make_point(latitude, longitude)
    stmt = select(Report).where(
        geo_func.ST_DWithin(
            geo_func.ST_Transform(Report.location, 3857),
            geo_func.ST_Transform(point, 3857),
            radius_meters,
        )
    )
    if exclude_resolved:
        stmt = stmt.where(Report.status.notin_(["resolved", "rejected"]))
    return list(db.execute(stmt).scalars().all())


def find_reports_in_bounding_box(
    db: Session,
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
) -> list[Report]:
    """Supports the dashboard map view: reports within a lat/lon bounding box."""
    stmt = select(Report).where(
        geo_func.ST_Within(
            Report.location,
            geo_func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326),
        )
    )
    return list(db.execute(stmt).scalars().all())
