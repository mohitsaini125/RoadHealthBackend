import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Authority(Base):
    """
    An authority organization (e.g. municipal ward office, district PWD office,
    state authority). `level` orders the escalation hierarchy — a higher
    number is a higher authority. `parent_authority_id` gives the next
    escalation target explicitly, rather than inferring it.
    """
    __tablename__ = "authorities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_authority_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("authorities.id"), nullable=True
    )
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    parent: Mapped["Authority"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Authority"]] = relationship(back_populates="parent")
    users: Mapped[list["User"]] = relationship(back_populates="authority")
    zones: Mapped[list["Zone"]] = relationship(back_populates="authority")
