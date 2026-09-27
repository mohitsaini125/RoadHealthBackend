from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers import dashboard_controller, report_controller
from app.database import get_db
from app.dependencies import require_authority
from app.models.enums import DamageSeverity, ReportPriority, ReportStatus
from app.models.user import User
from app.schemas.dashboard import DashboardAnalyticsResponse, DashboardSummaryResponse, MapReportPoint
from app.schemas.report import ReportListQuery, ReportResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def summary(current_user: User = Depends(require_authority), db: Session = Depends(get_db)):
    return dashboard_controller.get_summary(db, current_user)


@router.get("/reports", response_model=list[ReportResponse])
def reports(
    status_filter: ReportStatus | None = None,
    severity: DamageSeverity | None = None,
    priority: ReportPriority | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_authority),
    db: Session = Depends(get_db),
):
    query = ReportListQuery(
        status=status_filter, severity=severity, priority=priority, page=page, page_size=page_size
    )
    return report_controller.list_reports(db, current_user, query)


@router.get("/map", response_model=list[MapReportPoint])
def map_view(
    min_lat: float = Query(...),
    min_lon: float = Query(...),
    max_lat: float = Query(...),
    max_lon: float = Query(...),
    _current_user: User = Depends(require_authority),
    db: Session = Depends(get_db),
):
    return dashboard_controller.get_map_points(db, min_lat, min_lon, max_lat, max_lon)


@router.get("/overdue", response_model=list[ReportResponse])
def overdue(current_user: User = Depends(require_authority), db: Session = Depends(get_db)):
    return dashboard_controller.get_overdue_reports(db, current_user)


@router.get("/escalated", response_model=list[ReportResponse])
def escalated(current_user: User = Depends(require_authority), db: Session = Depends(get_db)):
    return dashboard_controller.get_escalated_reports(db, current_user)


@router.get("/analytics", response_model=DashboardAnalyticsResponse)
def analytics(current_user: User = Depends(require_authority), db: Session = Depends(get_db)):
    return dashboard_controller.get_analytics(db, current_user)
