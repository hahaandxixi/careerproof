"""Initial CareerProof schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps(*, versioned: bool = False) -> list[sa.Column]:
    columns = [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]
    if versioned:
        columns.append(sa.Column("version", sa.Integer(), nullable=False))
    return columns


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "enterprises",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        *timestamps(versioned=True),
    )
    op.create_index("ix_enterprises_name", "enterprises", ["name"])
    op.create_table(
        "knowledge_chunks",
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_metadata", sa.JSON(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_knowledge_chunks_source_type", "knowledge_chunks", ["source_type"])
    op.create_index("ix_knowledge_chunks_source_id", "knowledge_chunks", ["source_id"])
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding_hnsw "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.create_table(
        "matching_formula_versions",
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version_name", sa.String(50), nullable=False, unique=True),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "skills",
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(versioned=True),
    )
    op.create_index("ix_skills_name", "skills", ["name"], unique=True)
    op.create_table(
        "users",
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column(
            "role",
            sa.Enum("STUDENT", "ENTERPRISE", "ADMIN", name="user_role"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(versioned=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_table(
        "analysis_tasks",
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", name="task_status"),
            nullable=False,
        ),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("total_cost_rmb", sa.Numeric(12, 6), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_analysis_tasks_status", "analysis_tasks", ["status"])
    op.create_index("ix_analysis_tasks_task_type", "analysis_tasks", ["task_type"])
    op.create_table(
        "audit_logs",
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_table(
        "enterprise_memberships",
        sa.Column("enterprise_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("OWNER", "HR", "REVIEWER", name="membership_role"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("enterprise_id", "user_id"),
    )
    op.create_index(
        "ix_enterprise_memberships_enterprise_id", "enterprise_memberships", ["enterprise_id"]
    )
    op.create_index("ix_enterprise_memberships_user_id", "enterprise_memberships", ["user_id"])
    op.create_table(
        "jobs",
        sa.Column("enterprise_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_jobs_enterprise_id", "jobs", ["enterprise_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_title", "jobs", ["title"])
    op.create_table(
        "refresh_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("jti_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_refresh_tokens_jti_hash", "refresh_tokens", ["jti_hash"], unique=True)
    op.create_table(
        "skill_aliases",
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(100), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_skill_aliases_alias", "skill_aliases", ["alias"], unique=True)
    op.create_table(
        "student_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("school", sa.String(200), nullable=True),
        sa.Column("major", sa.String(200), nullable=True),
        sa.Column("graduation_year", sa.Integer(), nullable=True),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "agent_steps",
        sa.Column("analysis_task_id", sa.Uuid(), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["analysis_task_id"], ["analysis_tasks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("analysis_task_id", "step_number"),
    )
    op.create_index("ix_agent_steps_analysis_task_id", "agent_steps", ["analysis_task_id"])
    op.create_table(
        "ai_usage_logs",
        sa.Column("analysis_task_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_hit_tokens", sa.Integer(), nullable=False),
        sa.Column("unit_price_snapshot", sa.JSON(), nullable=False),
        sa.Column("cost_rmb", sa.Numeric(12, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["analysis_task_id"], ["analysis_tasks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ai_usage_logs_analysis_task_id", "ai_usage_logs", ["analysis_task_id"])
    op.create_table(
        "applications",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["student_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("job_id", "student_id"),
    )
    op.create_index("ix_applications_status", "applications", ["status"])
    op.create_table(
        "interview_sessions",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["student_id"], ["student_profiles.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
    )
    op.create_table(
        "job_requirements",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("skill_name", sa.String(100), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("normalized_status", sa.String(30), nullable=False),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_job_requirements_job_id", "job_requirements", ["job_id"])
    op.create_index("ix_job_requirements_skill_name", "job_requirements", ["skill_name"])
    op.create_table(
        "match_reports",
        sa.Column("analysis_task_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_ref", sa.String(100), nullable=False),
        sa.Column("formula_version_id", sa.Uuid(), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("gaps", sa.JSON(), nullable=False),
        sa.Column("claimed_only", sa.JSON(), nullable=False),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["analysis_task_id"], ["analysis_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["formula_version_id"], ["matching_formula_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_match_reports_candidate_ref", "match_reports", ["candidate_ref"])
    op.create_table(
        "projects",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["student_id"], ["student_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_projects_student_id", "projects", ["student_id"])
    op.create_table(
        "resumes",
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["student_id"], ["student_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_resumes_student_id", "resumes", ["student_id"])
    op.create_table(
        "interview_answers",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("audio_storage_key", sa.String(500), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_interview_answers_session_id", "interview_answers", ["session_id"])
    op.create_table(
        "project_versions",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("archive_storage_key", sa.String(500), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("analysis_status", sa.String(30), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "version_number"),
    )
    op.create_index("ix_project_versions_content_hash", "project_versions", ["content_hash"])
    op.create_table(
        "resume_versions",
        sa.Column("resume_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("parse_status", sa.String(30), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("resume_id", "version_number"),
    )
    op.create_index("ix_resume_versions_content_hash", "resume_versions", ["content_hash"])
    op.create_table(
        "project_files",
        sa.Column("project_version_id", sa.Uuid(), nullable=False),
        sa.Column("relative_path", sa.String(1000), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("language", sa.String(50), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(1000), nullable=False),
        sa.Column("analysis_status", sa.String(30), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["project_version_id"], ["project_versions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("project_version_id", "relative_path"),
    )
    op.create_index("ix_project_files_project_version_id", "project_files", ["project_version_id"])
    op.create_index("ix_project_files_content_hash", "project_files", ["content_hash"])
    op.create_table(
        "resume_sections",
        sa.Column("resume_version_id", sa.Uuid(), nullable=False),
        sa.Column("section_type", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["resume_version_id"], ["resume_versions.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_resume_sections_resume_version_id", "resume_sections", ["resume_version_id"]
    )
    op.create_table(
        "evidence_sources",
        sa.Column("resume_section_id", sa.Uuid(), nullable=True),
        sa.Column("project_file_id", sa.Uuid(), nullable=True),
        sa.Column("interview_answer_id", sa.Uuid(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        *timestamps(versioned=True),
        sa.CheckConstraint(
            "num_nonnulls(resume_section_id, project_file_id, interview_answer_id) = 1",
            name="ck_evidence_source_exactly_one_reference",
        ),
        sa.ForeignKeyConstraint(["resume_section_id"], ["resume_sections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_file_id"], ["project_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["interview_answer_id"], ["interview_answers.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_evidence_sources_content_hash", "evidence_sources", ["content_hash"])
    op.create_table(
        "skill_evidence",
        sa.Column("analysis_task_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_source_id", sa.Uuid(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "verification_status",
            sa.Enum("VERIFIED", "INFERRED", "MISSING", "UNKNOWN", name="verification_status"),
            nullable=False,
        ),
        sa.Column(
            "confirmation_status",
            sa.Enum("PENDING", "ACCEPTED", "REJECTED", "CORRECTED", name="confirmation_status"),
            nullable=False,
        ),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["analysis_task_id"], ["analysis_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["evidence_source_id"], ["evidence_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("analysis_task_id", "skill_id", "evidence_source_id"),
    )
    op.create_index("ix_skill_evidence_analysis_task_id", "skill_evidence", ["analysis_task_id"])
    op.create_table(
        "match_items",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=True),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column("rule_base_score", sa.Float(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("verdict", sa.String(30), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("formula_version", sa.String(50), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=True),
        *timestamps(versioned=True),
        sa.ForeignKeyConstraint(["report_id"], ["match_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requirement_id"], ["job_requirements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["skill_evidence.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_match_items_report_id", "match_items", ["report_id"])


def downgrade() -> None:
    for table in (
        "match_items",
        "skill_evidence",
        "evidence_sources",
        "resume_sections",
        "project_files",
        "resume_versions",
        "project_versions",
        "interview_answers",
        "resumes",
        "projects",
        "match_reports",
        "job_requirements",
        "interview_sessions",
        "applications",
        "ai_usage_logs",
        "agent_steps",
        "student_profiles",
        "skill_aliases",
        "refresh_tokens",
        "jobs",
        "enterprise_memberships",
        "audit_logs",
        "analysis_tasks",
        "users",
        "skills",
        "matching_formula_versions",
        "knowledge_chunks",
        "enterprises",
    ):
        op.drop_table(table)
    for enum_name in (
        "confirmation_status",
        "verification_status",
        "membership_role",
        "task_status",
        "user_role",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
