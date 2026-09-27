import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.models.enums import ReportStatus, UserRole
from app.models.user import User
from app.models.verification import Verification
from app.schemas.verification import VerificationRequest
from app.services import image_service, report_service, verification_service
from app.utils.file_utils import InvalidUploadError


async def verify_report(
    db: Session,
    current_user: User,
    report_id: uuid.UUID,
    payload: VerificationRequest,
    evidence_image: UploadFile | None,
) -> Verification:
    if current_user.role == UserRole.CITIZEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only authorities can verify repairs.")

    try:
        report = report_service.get_report(db, report_id)
    except report_service.ReportNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

    if current_user.role == UserRole.AUTHORITY and report.assigned_authority_id != current_user.authority_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not in your jurisdiction.")

    if report.status != ReportStatus.VERIFICATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report must be in 'verification' status to be verified (currently '{report.status.value}').",
        )

    evidence_path = None
    if evidence_image is not None:
        try:
            evidence_path = await image_service.store_report_image(
                str(report.id), evidence_image, suffix="verification"
            )
        except InvalidUploadError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return verification_service.verify_repair(
        db, report, current_user.id, payload.result, payload.notes, evidence_path
    )
