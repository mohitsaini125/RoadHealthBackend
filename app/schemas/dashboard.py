import uuid
from datetime import datetime

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    total_reports: int
    reports_by_status: dict[str, int]
    reports_by_severity: dict[str, int]
    overdue_count: int
    escalated_count: int
    average_resolution_hours: float | None = None


class AuthorityWorkloadItem(BaseModel):
    authority_id: uuid.UUID
    authority_name: str
    open_reports: int
    overdue_reports: int


class DashboardAnalyticsResponse(BaseModel):
    reports_by_status: dict[str, int]
    reports_by_severity: dict[str, int]
    average_resolution_hours: float | None = None
    authority_workload: list[AuthorityWorkloadItem]


class MapReportPoint(BaseModel):
    id: uuid.UUID
    report_number: str
    latitude: float
    longitude: float
    status: str
    severity: str | None = None
    priority: str | None = None
    created_at: datetime
