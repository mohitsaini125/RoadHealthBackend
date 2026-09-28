"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-01 00:00:00

"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    user_role = postgresql.ENUM("citizen", "authority", "admin", name="user_role")
    damage_severity = postgresql.ENUM("low", "medium", "high", "critical", name="damage_severity")
    report_priority = postgresql.ENUM("low", "medium", "high", "critical", name="report_priority")
    report_status = postgresql.ENUM(
        "submitted", "under_review", "assigned", "accepted", "in_progress",
        "repair_completed", "verification", "resolved", "rejected",
        "rejected_for_rework", "escalated", name="report_status",
    )
    verification_result = postgresql.ENUM("passed", "failed", name="verification_result")

    op.create_table(
        "authorities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("level", sa.Integer, nullable=False, server_default="1"),
        sa.Column("parent_authority_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("authorities.id"), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("role", user_role, nullable=False, server_default="citizen"),
        sa.Column("authority_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("authorities.id"), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_authority_id", "users", ["authority_id"])

    op.create_table(
        "zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("authority_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("authorities.id"), nullable=False),
        sa.Column("boundary", geoalchemy2.Geometry(geometry_type="POLYGON", srid=4326), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_zones_authority_id", "zones", ["authority_id"])

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_number", sa.String(32), nullable=False, unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("image_path", sa.String(512), nullable=False),
        sa.Column("repair_evidence_path", sa.String(512), nullable=True),
        sa.Column("location", geoalchemy2.Geometry(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("address", sa.String(512), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("damage_type", sa.String(64), nullable=True),
        sa.Column("severity", damage_severity, nullable=True),
        sa.Column("ai_confidence", sa.Float, nullable=True),
        sa.Column("status", report_status, nullable=False, server_default="submitted"),
        sa.Column("priority", report_priority, nullable=True),
        sa.Column("assigned_authority_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("authorities.id"), nullable=True),
        sa.Column("repair_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_escalation_level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("repaired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_reports_report_number", "reports", ["report_number"])
    op.create_index("ix_reports_user_id", "reports", ["user_id"])
    op.create_index("ix_reports_status", "reports", ["status"])
    op.create_index("ix_reports_priority", "reports", ["priority"])
    op.create_index("ix_reports_assigned_authority_id", "reports", ["assigned_authority_id"])
    op.create_index("ix_reports_created_at", "reports", ["created_at"])
    op.execute("CREATE INDEX ix_reports_location ON reports USING GIST (location)")
    op.execute("CREATE INDEX ix_zones_boundary ON zones USING GIST (boundary)")

    op.create_table(
        "report_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("from_status", report_status, nullable=True),
        sa.Column("to_status", report_status, nullable=False),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("notes", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_report_status_history_report_id", "report_status_history", ["report_id"])

    op.create_table(
        "ai_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("damage_type", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("bounding_boxes", postgresql.JSONB, nullable=True),
        sa.Column("estimated_severity", sa.String(32), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_assessments_report_id", "ai_assessments", ["report_id"])

    op.create_table(
        "verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("result", verification_result, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("evidence_image_path", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_verifications_report_id", "verifications", ["report_id"])

    op.create_table(
        "escalations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("from_authority_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("authorities.id"), nullable=True),
        sa.Column("to_authority_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("authorities.id"), nullable=False),
        sa.Column("previous_level", sa.Integer, nullable=False),
        sa.Column("new_level", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(512), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_escalations_report_id", "escalations", ["report_id"])


def downgrade() -> None:
    op.drop_table("escalations")
    op.drop_table("verifications")
    op.drop_table("ai_assessments")
    op.drop_table("report_status_history")
    op.drop_table("reports")
    op.drop_table("zones")
    op.drop_table("users")
    op.drop_table("authorities")

    bind = op.get_bind()
    for enum_name in ("verification_result", "report_status", "report_priority", "damage_severity", "user_role"):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
