import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import DamageSeverity, ReportPriority, ReportStatus


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Human-friendly, sequential-looking identifier shown to citizens/authorities.
    report_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    # Set when the authority uploads evidence of the completed repair; consumed
    # by the verification step. Not part of the spec's minimal field list but
    # needed to carry the evidence path between "repair done" and "verified".
    repair_evidence_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # PostGIS Point (SRID 4326) — authoritative spatial field.
    location = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    # Plain lat/lon kept for client convenience; must stay derived from `location`.
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    damage_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[DamageSeverity | None] = mapped_column(
        Enum(DamageSeverity, name="damage_severity", values_callable=lambda e: [v.value for v in e]),
        nullable=True,
    )
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status", values_callable=lambda e: [v.value for v in e]),
        nullable=False,
        default=ReportStatus.SUBMITTED,
        index=True,
    )
    priority: Mapped[ReportPriority | None] = mapped_column(
        Enum(ReportPriority, name="report_priority", values_callable=lambda e: [v.value for v in e]),
        nullable=True,
        index=True,
    )

    assigned_authority_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("authorities.id"), nullable=True, index=True
    )

    repair_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    current_escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    repaired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    citizen: Mapped["User"] = relationship(back_populates="reports")
    status_history: Mapped[list["ReportStatusHistory"]] = relationship(
        back_populates="report", order_by="ReportStatusHistory.created_at"
    )
    ai_assessments: Mapped[list["AIAssessment"]] = relationship(back_populates="report")
    verifications: Mapped[list["Verification"]] = relationship(back_populates="report")
    escalations: Mapped[list["Escalation"]] = relationship(back_populates="report")
