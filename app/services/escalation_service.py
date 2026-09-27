"""
Business rules for automatic escalation. Triggered periodically by
escalation_scheduler.py, but this module owns all the actual logic —
the scheduler is just a clock.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ESCALATION_ELIGIBLE_STATUSES, ReportStatus
from app.models.escalation import Escalation
from app.models.report import Report
from app.services.authority_service import get_next_authority

logger = logging.getLogger("escalation_service")


def _find_overdue_eligible_reports(db: Session) -> list[Report]:
    """
    Overdue AND in an escalation-eligible status. Resolved/rejected reports
    (and any other terminal status) are excluded by the eligible-status set,
    so a resolved report is never escalated.
    """
    now = datetime.now(timezone.utc)
    stmt = select(Report).where(
        Report.repair_deadline.is_not(None),
        Report.repair_deadline < now,
        Report.status.in_(list(ESCALATION_ELIGIBLE_STATUSES)),
        Report.assigned_authority_id.is_not(None),
    )
    return list(db.execute(stmt).scalars().all())


def _already_escalated_for_deadline(db: Session, report: Report) -> bool:
    """
    Idempotency guard: don't escalate the same overdue report again just
    because the scheduler ticked again while it's still overdue at the
    same escalation level. An escalation is only created once per level.
    """
    stmt = select(Escalation).where(
        Escalation.report_id == report.id,
        Escalation.new_level == report.current_escalation_level + 1,
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def escalate_report(db: Session, report: Report, reason: str) -> Escalation | None:
    if report.assigned_authority_id is None:
        logger.warning("Report %s is overdue but has no assigned authority — skipping.", report.id)
        return None

    if _already_escalated_for_deadline(db, report):
        logger.info("Report %s already escalated at this level — skipping duplicate tick.", report.id)
        return None

    next_authority = get_next_authority(db, report.assigned_authority_id)
    if next_authority is None:
        logger.warning(
            "Report %s is overdue but its authority %s has no parent — cannot escalate further.",
            report.id,
            report.assigned_authority_id,
        )
        return None

    previous_level = report.current_escalation_level
    new_level = previous_level + 1

    escalation = Escalation(
        report_id=report.id,
        from_authority_id=report.assigned_authority_id,
        to_authority_id=next_authority.id,
        previous_level=previous_level,
        new_level=new_level,
        reason=reason,
    )
    db.add(escalation)

    report.assigned_authority_id = next_authority.id
    report.current_escalation_level = new_level
    report.status = ReportStatus.ESCALATED

    logger.info(
        "Escalated report %s from authority %s to %s (level %s -> %s).",
        report.id,
        escalation.from_authority_id,
        escalation.to_authority_id,
        previous_level,
        new_level,
    )
    return escalation


def check_overdue_reports(db: Session) -> int:
    """
    Entry point called by the scheduler tick. Finds every eligible overdue
    report and escalates it. Returns the number of escalations created.
    Safe to call repeatedly — already-escalated reports at the current
    level are skipped, not re-escalated.
    """
    overdue_reports = _find_overdue_eligible_reports(db)
    escalated_count = 0
    for report in overdue_reports:
        try:
            result = escalate_report(db, report, reason="Repair deadline exceeded.")
            if result is not None:
                escalated_count += 1
        except Exception:
            logger.exception("Failed to escalate report %s", report.id)
            db.rollback()
            continue

    db.commit()
    logger.info("Escalation check complete: %s report(s) escalated.", escalated_count)
    return escalated_count
