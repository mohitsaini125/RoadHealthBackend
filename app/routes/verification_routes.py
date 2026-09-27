import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.controllers import verification_controller
from app.database import get_db
from app.dependencies import get_current_user
from app.models.enums import VerificationResult
from app.models.user import User
from app.schemas.verification import VerificationRequest, VerificationResponse

router = APIRouter(prefix="/reports", tags=["Verification"])


@router.post("/{report_id}/verify", response_model=VerificationResponse, status_code=201)
async def verify_report(
    report_id: uuid.UUID,
    result: VerificationResult = Form(...),
    notes: str | None = Form(default=None),
    evidence_image: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload = VerificationRequest(result=result, notes=notes)
    return await verification_controller.verify_report(db, current_user, report_id, payload, evidence_image)
