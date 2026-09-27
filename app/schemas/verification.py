import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import VerificationResult


class VerificationRequest(BaseModel):
    result: VerificationResult
    notes: str | None = Field(default=None, max_length=1024)


class VerificationResponse(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID
    verified_by_user_id: uuid.UUID
    result: VerificationResult
    notes: str | None = None
    evidence_image_path: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EscalationResponse(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID
    from_authority_id: uuid.UUID | None = None
    to_authority_id: uuid.UUID
    previous_level: int
    new_level: int
    reason: str
    escalated_at: datetime
    resolved_at: datetime | None = None

    model_config = {"from_attributes": True}
