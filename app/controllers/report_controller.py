import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportCreate, ReportListQuery, ReportStatusUpdate
from app.services import image_service, report_service
from app.utils.file_utils import InvalidUploadError


def _authorize_report_access(current_user: User, report: Report) -> None:
    """Citizens may only see their own reports; authorities/admins may see
    reports assigned to their authority (or, for admins, any report)."""
    if current_user.role == UserRole.CITIZEN and report.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your report.")
    if current_user.role == UserRole.AUTHORITY and report.assigned_authority_id != current_user.authority_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This report is not in your jurisdiction.",
        )


async def create_report(
    db: Session, current_user: User, payload: ReportCreate, image: UploadFile
) -> Report:
    temp_id = str(uuid.uuid4())
    try:
        relative_path = await image_service.store_report_image(temp_id, image, suffix="original")
    except InvalidUploadError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return report_service.create_report(
        db,
        citizen=current_user,
        latitude=payload.latitude,
        longitude=payload.longitude,
        description=payload.description,
        image_relative_path=relative_path,
    )


def get_report(db: Session, current_user: User, report_id: uuid.UUID) -> Report:
    try:
        report = report_service.get_report(db, report_id)
    except report_service.ReportNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    _authorize_report_access(current_user, report)
    return report


def list_reports(db: Session, current_user: User, query: ReportListQuery) -> list[Report]:
    if current_user.role == UserRole.CITIZEN:
        return report_service.list_reports(
            db,
            citizen_id=current_user.id,
            status=query.status,
            severity=query.severity,
            priority=query.priority,
            page=query.page,
            page_size=query.page_size,
        )
    if current_user.role == UserRole.AUTHORITY:
        return report_service.list_reports(
            db,
            authority_id=current_user.authority_id,
            status=query.status,
            severity=query.severity,
            priority=query.priority,
            page=query.page,
            page_size=query.page_size,
        )
    # Admin: unrestricted, optionally filtered by the requested authority_id.
    return report_service.list_reports(
        db,
        authority_id=query.authority_id,
        status=query.status,
        severity=query.severity,
        priority=query.priority,
        page=query.page,
        page_size=query.page_size,
    )


def update_status(
    db: Session, current_user: User, report_id: uuid.UUID, payload: ReportStatusUpdate
) -> Report:
    report = get_report(db, current_user, report_id)
    if current_user.role == UserRole.CITIZEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Citizens cannot change report status.",
        )
    try:
        return report_service.update_status(db, report, payload.status, current_user.id, payload.notes)
    except report_service.InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


async def upload_repair_evidence(
    db: Session, current_user: User, report_id: uuid.UUID, image: UploadFile, notes: str | None
) -> Report:
    report = get_report(db, current_user, report_id)
    if current_user.role == UserRole.CITIZEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only authorities can upload repair evidence.")

    try:
        relative_path = await image_service.store_report_image(str(report.id), image, suffix="repair")
    except InvalidUploadError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    try:
        return report_service.attach_repair_evidence(db, report, relative_path, current_user.id, notes)
    except report_service.InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
