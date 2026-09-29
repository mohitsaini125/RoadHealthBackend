import uuid
from datetime import datetime

from pydantic import BaseModel, Field, computed_field, field_validator

from app.models.enums import DamageSeverity, ReportPriority, ReportStatus


def _to_image_url(raw_path: str) -> str:
    """
    Normalise a stored image path to a public URL path.
    Handles three formats that may exist in the database:
      - /uploads/reports/filename      → already correct
      - reports/filename               → /uploads/reports/filename
      - app/uploads/reports/filename   → /uploads/reports/filename
    """
    p = raw_path.lstrip("/")
    if p.startswith("app/"):
        p = p[len("app/"):]
    if not p.startswith("uploads/"):
        p = f"uploads/{p}"
    return f"/{p}"


class ReportCreate(BaseModel):
    """Non-file fields accompanying the multipart image upload."""
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("latitude", "longitude")
    @classmethod
    def not_nan(cls, v: float) -> float:
        if v != v:  # NaN check
            raise ValueError("Coordinate must be a valid number.")
        return v


class ReportStatusUpdate(BaseModel):
    """Only authorities/admins may drive transitions; validated against
    ALLOWED_STATUS_TRANSITIONS server-side, never applied as a raw string."""
    status: ReportStatus
    notes: str | None = Field(default=None, max_length=1024)


class RepairEvidenceResponse(BaseModel):
    report_id: uuid.UUID
    evidence_image_path: str
    notes: str | None = None
    uploaded_at: datetime


class ReportStatusHistoryEntry(BaseModel):
    from_status: ReportStatus | None
    to_status: ReportStatus
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportResponse(BaseModel):
    id: uuid.UUID
    report_number: str
    user_id: uuid.UUID
    image_path: str
    repair_evidence_path: str | None = None
    latitude: float
    longitude: float
    address: str | None = None
    description: str | None = None
    damage_type: str | None = None
    severity: DamageSeverity | None = None
    ai_confidence: float | None = None
    status: ReportStatus
    priority: ReportPriority | None = None
    assigned_authority_id: uuid.UUID | None = None
    repair_deadline: datetime | None = None
    current_escalation_level: int
    created_at: datetime
    updated_at: datetime
    repaired_at: datetime | None = None
    verified_at: datetime | None = None

    @computed_field
    @property
    def image_url(self) -> str:
        """Public URL path the mobile app uses to fetch the image.
        Combine with API_ORIGIN: API_ORIGIN + report.image_url"""
        return _to_image_url(self.image_path)

    model_config = {"from_attributes": True}


class ReportDetailResponse(ReportResponse):
    status_history: list[ReportStatusHistoryEntry] = []


class ReportListQuery(BaseModel):
    status: ReportStatus | None = None
    severity: DamageSeverity | None = None
    priority: ReportPriority | None = None
    authority_id: uuid.UUID | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

