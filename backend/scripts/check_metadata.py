from app import models  # noqa: F401
from app.core.database import Base

EXPECTED_TABLES = {
    "users",
    "refresh_tokens",
    "student_profiles",
    "enterprises",
    "enterprise_memberships",
    "skills",
    "skill_aliases",
    "jobs",
    "job_requirements",
    "applications",
    "resumes",
    "resume_versions",
    "resume_sections",
    "projects",
    "project_versions",
    "project_files",
    "analysis_tasks",
    "agent_steps",
    "evidence_sources",
    "skill_evidence",
    "match_reports",
    "match_items",
    "matching_formula_versions",
    "ai_usage_logs",
    "audit_logs",
}


missing = EXPECTED_TABLES - set(Base.metadata.tables)
if missing:
    raise SystemExit(f"Missing model tables: {sorted(missing)}")
print(f"Metadata OK: {len(Base.metadata.tables)} tables")
