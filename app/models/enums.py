"""
Shared enums for user roles, report lifecycle, severity, and verification.
Centralizing these prevents arbitrary status strings from leaking in from clients.
"""
import enum


class UserRole(str, enum.Enum):
    CITIZEN = "citizen"
    AUTHORITY = "authority"
    ADMIN = "admin"


class DamageSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReportPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReportStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    REPAIR_COMPLETED = "repair_completed"
    VERIFICATION = "verification"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    REJECTED_FOR_REWORK = "rejected_for_rework"
    ESCALATED = "escalated"


# Explicit transition map — the single source of truth for which status
# changes are legal. Clients can never set an arbitrary status string;
# report_service validates every transition against this map.
ALLOWED_STATUS_TRANSITIONS: dict[ReportStatus, set[ReportStatus]] = {
    ReportStatus.SUBMITTED: {ReportStatus.UNDER_REVIEW, ReportStatus.REJECTED},
    ReportStatus.UNDER_REVIEW: {ReportStatus.ASSIGNED, ReportStatus.REJECTED},
    ReportStatus.ASSIGNED: {ReportStatus.ACCEPTED, ReportStatus.ESCALATED},
    ReportStatus.ACCEPTED: {ReportStatus.IN_PROGRESS, ReportStatus.ESCALATED},
    ReportStatus.IN_PROGRESS: {ReportStatus.REPAIR_COMPLETED, ReportStatus.ESCALATED},
    ReportStatus.REPAIR_COMPLETED: {ReportStatus.VERIFICATION},
    ReportStatus.VERIFICATION: {ReportStatus.RESOLVED, ReportStatus.REJECTED_FOR_REWORK},
    ReportStatus.REJECTED_FOR_REWORK: {ReportStatus.IN_PROGRESS},
    ReportStatus.ESCALATED: {
        ReportStatus.ASSIGNED,
        ReportStatus.ACCEPTED,
        ReportStatus.IN_PROGRESS,
    },
    ReportStatus.RESOLVED: set(),
    ReportStatus.REJECTED: set(),
}

# Statuses from which an automatic escalation may ever fire.
# Resolved/rejected/terminal reports must never be escalated.
ESCALATION_ELIGIBLE_STATUSES = {
    ReportStatus.ASSIGNED,
    ReportStatus.ACCEPTED,
    ReportStatus.IN_PROGRESS,
}


class VerificationResult(str, enum.Enum):
    PASSED = "passed"
    FAILED = "failed"
