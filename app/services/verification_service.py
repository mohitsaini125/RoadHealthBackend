"""Business rules for verifying (or rejecting) a completed repair."""
import uuid

from sqlalchemy.orm import Session

from app.models.enums import ReportStatus, VerificationResult
from app.models.report import Report
from app.models.verification import Verification
from app.services import report_service


def verify_repair(
    db: Session,
    report: Report,
    verified_by_user_id: uuid.UUID,
    result: VerificationResult,
    notes: str | None,
    evidence_image_path: str | None,
) -> Verification:
    """
    Records the verification result and drives the report to its next state:
    passed -> resolved, failed -> rejected_for_rework.
    """
    verification = Verification(
        report_id=report.id,
        verified_by_user_id=verified_by_user_id,
        result=result,
        notes=notes,
        evidence_image_path=evidence_image_path,
    )
    db.add(verification)
    db.flush()

    next_status = (
        ReportStatus.RESOLVED if result == VerificationResult.PASSED else ReportStatus.REJECTED_FOR_REWORK
    )
    report_service.update_status(
        db,
        report,
        next_status,
        verified_by_user_id,
        notes or f"Verification {result.value}.",
    )

    db.commit()
    db.refresh(verification)
    return verification
