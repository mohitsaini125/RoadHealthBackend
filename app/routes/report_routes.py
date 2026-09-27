import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.controllers import report_controller
from app.database import get_db
from app.dependencies import get_current_user, require_citizen
from app.models.enums import DamageSeverity, ReportPriority, ReportStatus
from app.models.user import User
from app.schemas.report import (
    ReportCreate,
    ReportDetailResponse,
    ReportListQuery,
    ReportResponse,
    ReportStatusUpdate,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("", response_model=ReportResponse, status_code=201)
async def create_report(
    latitude: float = Form(...),
    longitude: float = Form(...),
    description: str | None = Form(default=None),
    image: UploadFile = File(...),
    current_user: User = Depends(require_citizen),
    db: Session = Depends(get_db),
):
    payload = ReportCreate(latitude=latitude, longitude=longitude, description=description)
    return await report_controller.create_report(db, current_user, payload, image)


@router.get("", response_model=list[ReportResponse])
def list_reports(
    status_filter: ReportStatus | None = None,
    severity: DamageSeverity | None = None,
    priority: ReportPriority | None = None,
    authority_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = ReportListQuery(
        status=status_filter,
        severity=severity,
        priority=priority,
        authority_id=authority_id,
        page=page,
        page_size=page_size,
    )
    return report_controller.list_reports(db, current_user, query)


@router.get("/{report_id}", response_model=ReportDetailResponse)
def get_report(
    report_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return report_controller.get_report(db, current_user, report_id)


@router.patch("/{report_id}/status", response_model=ReportResponse)
def update_status(
    report_id: uuid.UUID,
    payload: ReportStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return report_controller.update_status(db, current_user, report_id, payload)


@router.post("/{report_id}/repair-evidence", response_model=ReportResponse)
async def upload_repair_evidence(
    report_id: uuid.UUID,
    notes: str | None = Form(default=None),
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await report_controller.upload_repair_evidence(db, current_user, report_id, image, notes)
