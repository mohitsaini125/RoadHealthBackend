import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.authority import Authority
from app.models.enums import ReportStatus, UserRole
from app.models.escalation import Escalation
from app.models.report import Report
from app.models.user import User
from app.schemas.dashboard import (
    AuthorityWorkloadItem,
    DashboardAnalyticsResponse,
    DashboardSummaryResponse,
    MapReportPoint,
)
from app.services.location_service import find_reports_in_bounding_box

_OVERDUE_ELIGIBLE = [
    ReportStatus.ASSIGNED,
    ReportStatus.ACCEPTED,
    ReportStatus.IN_PROGRESS,
]


def _scope_authority_id(current_user: User) -> uuid.UUID | None:
    """Authority users only ever see their own authority's numbers; admins see all."""
    if current_user.role == UserRole.AUTHORITY:
        return current_user.authority_id
    return None


def _reports_by_status(db: Session, authority_id: uuid.UUID | None) -> dict[str, int]:
    stmt = select(Report.status, func.count(Report.id)).group_by(Report.status)
    if authority_id is not None:
        stmt = stmt.where(Report.assigned_authority_id == authority_id)
    rows = db.execute(stmt).all()
    return {status.value: count for status, count in rows}


def _reports_by_severity(db: Session, authority_id: uuid.UUID | None) -> dict[str, int]:
    stmt = select(Report.severity, func.count(Report.id)).group_by(Report.severity)
    if authority_id is not None:
        stmt = stmt.where(Report.assigned_authority_id == authority_id)
    rows = db.execute(stmt).all()
    return {(severity.value if severity else "unassessed"): count for severity, count in rows}


def _overdue_count(db: Session, authority_id: uuid.UUID | None) -> int:
    now = datetime.now(timezone.utc)
    stmt = select(func.count(Report.id)).where(
        Report.repair_deadline.is_not(None),
        Report.repair_deadline < now,
        Report.status.in_(_OVERDUE_ELIGIBLE),
    )
    if authority_id is not None:
        stmt = stmt.where(Report.assigned_authority_id == authority_id)
    return db.execute(stmt).scalar_one()


def _escalated_count(db: Session, authority_id: uuid.UUID | None) -> int:
    stmt = select(func.count(Report.id)).where(Report.status == ReportStatus.ESCALATED)
    if authority_id is not None:
        stmt = stmt.where(Report.assigned_authority_id == authority_id)
    return db.execute(stmt).scalar_one()


def _average_resolution_hours(db: Session, authority_id: uuid.UUID | None) -> float | None:
    stmt = select(
        func.avg(func.extract("epoch", Report.verified_at - Report.created_at) / 3600.0)
    ).where(Report.status == ReportStatus.RESOLVED, Report.verified_at.is_not(None))
    if authority_id is not None:
        stmt = stmt.where(Report.assigned_authority_id == authority_id)
    result = db.execute(stmt).scalar_one_or_none()
    return round(result, 2) if result is not None else None


def get_summary(db: Session, current_user: User) -> DashboardSummaryResponse:
    authority_id = _scope_authority_id(current_user)
    total_stmt = select(func.count(Report.id))
    if authority_id is not None:
        total_stmt = total_stmt.where(Report.assigned_authority_id == authority_id)

    return DashboardSummaryResponse(
        total_reports=db.execute(total_stmt).scalar_one(),
        reports_by_status=_reports_by_status(db, authority_id),
        reports_by_severity=_reports_by_severity(db, authority_id),
        overdue_count=_overdue_count(db, authority_id),
        escalated_count=_escalated_count(db, authority_id),
        average_resolution_hours=_average_resolution_hours(db, authority_id),
    )


def get_overdue_reports(db: Session, current_user: User) -> list[Report]:
    authority_id = _scope_authority_id(current_user)
    now = datetime.now(timezone.utc)
    stmt = select(Report).where(
        Report.repair_deadline.is_not(None),
        Report.repair_deadline < now,
        Report.status.in_(_OVERDUE_ELIGIBLE),
    )
    if authority_id is not None:
        stmt = stmt.where(Report.assigned_authority_id == authority_id)
    return list(db.execute(stmt).scalars().all())


def get_escalated_reports(db: Session, current_user: User) -> list[Report]:
    authority_id = _scope_authority_id(current_user)
    stmt = select(Report).where(Report.status == ReportStatus.ESCALATED)
    if authority_id is not None:
        stmt = stmt.where(Report.assigned_authority_id == authority_id)
    return list(db.execute(stmt).scalars().all())


def get_map_points(
    db: Session, min_lat: float, min_lon: float, max_lat: float, max_lon: float
) -> list[MapReportPoint]:
    reports = find_reports_in_bounding_box(db, min_lat, min_lon, max_lat, max_lon)
    return [
        MapReportPoint(
            id=r.id,
            report_number=r.report_number,
            latitude=r.latitude,
            longitude=r.longitude,
            status=r.status.value,
            severity=r.severity.value if r.severity else None,
            priority=r.priority.value if r.priority else None,
            created_at=r.created_at,
        )
        for r in reports
    ]


def get_analytics(db: Session, current_user: User) -> DashboardAnalyticsResponse:
    authority_id = _scope_authority_id(current_user)

    workload_stmt = (
        select(
            Authority.id,
            Authority.name,
            func.count(Report.id).filter(
                Report.status.notin_([ReportStatus.RESOLVED, ReportStatus.REJECTED])
            ),
            func.count(Report.id).filter(
                Report.repair_deadline < datetime.now(timezone.utc),
                Report.status.in_(_OVERDUE_ELIGIBLE),
            ),
        )
        .join(Report, Report.assigned_authority_id == Authority.id, isouter=True)
        .group_by(Authority.id, Authority.name)
    )
    if authority_id is not None:
        workload_stmt = workload_stmt.where(Authority.id == authority_id)

    workload_rows = db.execute(workload_stmt).all()
    workload = [
        AuthorityWorkloadItem(
            authority_id=row[0], authority_name=row[1], open_reports=row[2], overdue_reports=row[3]
        )
        for row in workload_rows
    ]

    return DashboardAnalyticsResponse(
        reports_by_status=_reports_by_status(db, authority_id),
        reports_by_severity=_reports_by_severity(db, authority_id),
        average_resolution_hours=_average_resolution_hours(db, authority_id),
        authority_workload=workload,
    )
