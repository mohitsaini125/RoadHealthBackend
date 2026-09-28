"""
Business rules for the report lifecycle: creation, listing, status transitions,
repair evidence, and deadline calculation. Routes/controllers stay thin;
all of this logic lives here.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import (
    ALLOWED_STATUS_TRANSITIONS,
    DamageSeverity,
    ReportPriority,
    ReportStatus,
)
from app.models.report import Report
from app.models.report_status_history import ReportStatusHistory
from app.models.user import User
from app.services import ai_service, location_service
from app.services.ai_service import AIResult, AIServiceUnavailableError, MODEL_VERSION_STUB


class ReportError(Exception):
    """Raised for invalid report operations (bad transition, not found, etc.)."""


class InvalidTransitionError(ReportError):
    pass


class ReportNotFoundError(ReportError):
    pass


# --- Severity -> priority mapping. Adjust once the project owner finalizes rules. ---
_SEVERITY_TO_PRIORITY = {
    DamageSeverity.CRITICAL: ReportPriority.CRITICAL,
    DamageSeverity.HIGH: ReportPriority.HIGH,
    DamageSeverity.MEDIUM: ReportPriority.MEDIUM,
    DamageSeverity.LOW: ReportPriority.LOW,
}

_PRIORITY_TO_SLA_HOURS = {
    ReportPriority.CRITICAL: settings.SLA_HOURS_CRITICAL,
    ReportPriority.HIGH: settings.SLA_HOURS_HIGH,
    ReportPriority.MEDIUM: settings.SLA_HOURS_MEDIUM,
    ReportPriority.LOW: settings.SLA_HOURS_LOW,
}


def _generate_report_number(db: Session) -> str:
    """Simple sequential-looking, human-friendly report number: RH-YYYYMMDD-XXXX."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"RH-{today}-"
    count_today = db.execute(
        select(Report).where(Report.report_number.like(f"{prefix}%"))
    ).scalars().all()
    seq = len(count_today) + 1
    return f"{prefix}{seq:04d}"


def determine_severity_and_priority(
    ai_result: AIResult,
) -> tuple[DamageSeverity | None, ReportPriority | None]:
    """Derives severity/priority from the AI result. With the dev stub (no
    real prediction yet) both stay None until a human/authority reviews it."""
    severity_str = ai_result.estimated_severity
    if severity_str is None:
        return None, None
    try:
        severity = DamageSeverity(severity_str)
    except ValueError:
        return None, None
    return severity, _SEVERITY_TO_PRIORITY.get(severity)


def calculate_repair_deadline(priority: ReportPriority | None) -> datetime | None:
    if priority is None:
        return None
    hours = _PRIORITY_TO_SLA_HOURS.get(priority)
    if hours is None:
        return None
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _record_status_history(
    db: Session,
    report: Report,
    to_status: ReportStatus,
    changed_by_user_id: uuid.UUID | None,
    notes: str | None,
    from_status: ReportStatus | None = None,
) -> None:
    db.add(
        ReportStatusHistory(
            report_id=report.id,
            from_status=from_status,
            to_status=to_status,
            changed_by_user_id=changed_by_user_id,
            notes=notes,
        )
    )


def create_report(
    db: Session,
    citizen: User,
    latitude: float,
    longitude: float,
    description: str | None,
    image_relative_path: str,
) -> Report:
    """
    Orchestrates the full creation flow per spec section 11:
    store record -> run AI assessment -> determine severity/priority ->
    determine authority/zone -> calculate deadline -> initial status history.
    """
    report_id = uuid.uuid4()
    zone = location_service.find_zone_for_point(db, latitude, longitude)

    report = Report(
        id=report_id,
        report_number=_generate_report_number(db),
        user_id=citizen.id,
        image_path=image_relative_path,
        location=location_service.make_point(latitude, longitude),
        latitude=latitude,
        longitude=longitude,
        description=description,
        status=ReportStatus.SUBMITTED,
        assigned_authority_id=zone.authority_id if zone else None,
    )
    db.add(report)
    db.flush()  # assigns defaults, keeps report.id stable for AI service call

    # Run AI assessment via Roboflow — isolated behind ai_service.
    # If the AI backend is unavailable, degrade gracefully: store null fields
    # so the report is still saved and the citizen is not blocked.
    import logging as _logging
    _log = _logging.getLogger(__name__)
    try:
        ai_result = ai_service.assess_image(image_relative_path)
    except AIServiceUnavailableError as exc:
        _log.warning("AI assessment unavailable for report %s: %s", report_id, exc)
        ai_result = AIResult(
            damage_type=None,
            confidence=None,
            bounding_boxes=None,
            estimated_severity=None,
            model_version=f"{MODEL_VERSION_STUB}-error",
            processed_at=datetime.now(timezone.utc),
        )
    severity, priority = determine_severity_and_priority(ai_result)
    report.damage_type = ai_result.damage_type
    report.ai_confidence = ai_result.confidence
    report.severity = severity
    report.priority = priority
    report.repair_deadline = calculate_repair_deadline(priority)

    from app.models.ai_assessment import AIAssessment

    db.add(
        AIAssessment(
            report_id=report.id,
            damage_type=ai_result.damage_type,
            confidence=ai_result.confidence,
            bounding_boxes=ai_result.bounding_boxes,
            estimated_severity=ai_result.estimated_severity,
            model_version=ai_result.model_version,
            processed_at=ai_result.processed_at,
        )
    )

    _record_status_history(db, report, ReportStatus.SUBMITTED, citizen.id, "Report submitted.")

    db.commit()
    db.refresh(report)
    return report


def get_report(db: Session, report_id: uuid.UUID) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise ReportNotFoundError(f"Report {report_id} not found.")
    return report


def list_reports(
    db: Session,
    *,
    citizen_id: uuid.UUID | None = None,
    authority_id: uuid.UUID | None = None,
    status: ReportStatus | None = None,
    severity: DamageSeverity | None = None,
    priority: ReportPriority | None = None,
    page: int = 1,
    page_size: int = 20,
) -> list[Report]:
    stmt = select(Report)
    if citizen_id is not None:
        stmt = stmt.where(Report.user_id == citizen_id)
    if authority_id is not None:
        stmt = stmt.where(Report.assigned_authority_id == authority_id)
    if status is not None:
        stmt = stmt.where(Report.status == status)
    if severity is not None:
        stmt = stmt.where(Report.severity == severity)
    if priority is not None:
        stmt = stmt.where(Report.priority == priority)
    stmt = stmt.order_by(Report.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    return list(db.execute(stmt).scalars().all())


def update_status(
    db: Session,
    report: Report,
    new_status: ReportStatus,
    changed_by_user_id: uuid.UUID,
    notes: str | None,
) -> Report:
    """Validates the transition against the explicit map — clients can never
    force an arbitrary status string."""
    allowed = ALLOWED_STATUS_TRANSITIONS.get(report.status, set())
    if new_status not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition report from {report.status.value} to {new_status.value}."
        )

    old_status = report.status
    report.status = new_status

    if new_status == ReportStatus.REPAIR_COMPLETED:
        report.repaired_at = datetime.now(timezone.utc)
    if new_status == ReportStatus.RESOLVED:
        report.verified_at = datetime.now(timezone.utc)

    _record_status_history(db, report, new_status, changed_by_user_id, notes, from_status=old_status)
    db.commit()
    db.refresh(report)
    return report


def attach_repair_evidence(
    db: Session,
    report: Report,
    evidence_image_path: str,
    changed_by_user_id: uuid.UUID,
    notes: str | None,
) -> Report:
    """
    Authority uploads repair evidence -> report moves to verification.
    Accepts the call from IN_PROGRESS directly (repair just finished) or
    from REPAIR_COMPLETED (repair was marked done in an earlier call),
    hopping through REPAIR_COMPLETED either way so repaired_at is always set.
    """
    report.repair_evidence_path = evidence_image_path
    if report.status == ReportStatus.IN_PROGRESS:
        update_status(db, report, ReportStatus.REPAIR_COMPLETED, changed_by_user_id, "Repair marked complete.")
    return update_status(
        db,
        report,
        ReportStatus.VERIFICATION,
        changed_by_user_id,
        notes or "Repair evidence uploaded.",
    )
