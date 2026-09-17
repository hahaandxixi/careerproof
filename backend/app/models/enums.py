from enum import StrEnum


class UserRole(StrEnum):
    STUDENT = "student"
    ENTERPRISE = "enterprise"
    ADMIN = "admin"


class MembershipRole(StrEnum):
    OWNER = "owner"
    HR = "hr"
    REVIEWER = "reviewer"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    MISSING = "missing"
    UNKNOWN = "unknown"


class ConfirmationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CORRECTED = "corrected"


class EvidenceStrength(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MatchVerdict(StrEnum):
    VERIFIED = "verified"
    CLAIMED_ONLY = "claimed_only"
    GAP = "gap"
