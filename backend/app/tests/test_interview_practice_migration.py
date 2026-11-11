"""0022: additive interview columns, curated cards, and legacy rows untouched."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.core.database import Base
from app.knowledge.technical_seed import TECHNICAL_KNOWLEDGE
from app.services.technical_knowledge import seed_technical_knowledge


def migration(name):
    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy_database(connection):
    connection.exec_driver_sql("CREATE TABLE student_profiles (id CHAR(32) PRIMARY KEY)")
    connection.exec_driver_sql("CREATE TABLE jobs (id CHAR(32) PRIMARY KEY)")
    connection.exec_driver_sql("CREATE TABLE match_reports (id CHAR(32) PRIMARY KEY)")
    connection.exec_driver_sql("CREATE TABLE job_requirements (id CHAR(32) PRIMARY KEY)")
    connection.exec_driver_sql(
        "CREATE TABLE interview_sessions (id CHAR(32) PRIMARY KEY, "
        "student_id CHAR(32), job_id CHAR(32), status VARCHAR(30), version INTEGER, "
        "created_at DATETIME, updated_at DATETIME)"
    )
    connection.exec_driver_sql(
        "CREATE TABLE interview_answers (id CHAR(32) PRIMARY KEY, session_id CHAR(32), "
        "answer_text TEXT, audio_storage_key VARCHAR(500), duration_seconds INTEGER, "
        "version INTEGER, created_at DATETIME, updated_at DATETIME)"
    )
    connection.exec_driver_sql(
        "INSERT INTO interview_sessions VALUES "
        "('s1','p1','j1','pending',3,'2026-01-01','2026-01-02')"
    )
    connection.exec_driver_sql(
        "INSERT INTO interview_answers VALUES "
        "('a1','s1','旧回答',NULL,NULL,2,'2026-01-01','2026-01-02')"
    )


def columns(connection, table):
    return {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}


def test_upgrade_adds_practice_fields_without_touching_legacy_rows(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        legacy_database(connection)
        module = migration("0022_interview_practice.py")
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()

        session_columns = columns(connection, "interview_sessions")
        assert {
            "report_id",
            "requirement_id",
            "requirement_title",
            "skill",
            "materials_snapshot",
            "evidence_snapshot",
            "knowledge_snapshot",
            "consent_at",
            "current_turn",
            "summary",
        } <= session_columns
        answer_columns = columns(connection, "interview_answers")
        assert {
            "turn_index",
            "kind",
            "question_text",
            "state",
            "feedback",
            "client_token",
            "answered_at",
            "failure_reason",
        } <= answer_columns

        legacy_session = connection.exec_driver_sql(
            "SELECT status, version, report_id FROM interview_sessions WHERE id='s1'"
        ).one()
        assert legacy_session == ("pending", 3, None)
        legacy_answer = connection.exec_driver_sql(
            "SELECT answer_text, turn_index FROM interview_answers WHERE id='a1'"
        ).one()
        assert legacy_answer == ("旧回答", None)

        seeded = connection.exec_driver_sql(
            "SELECT COUNT(*), COUNT(DISTINCT knowledge_id) FROM technical_knowledge_entries"
        ).one()
        assert seeded == (len(TECHNICAL_KNOWLEDGE), len(TECHNICAL_KNOWLEDGE))


def test_downgrade_removes_only_the_new_surface(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'downgrade.db'}")
    with engine.begin() as connection:
        legacy_database(connection)
        module = migration("0022_interview_practice.py")
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
        assert "report_id" not in columns(connection, "interview_sessions")
        assert "turn_index" not in columns(connection, "interview_answers")
        assert (
            connection.exec_driver_sql(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='technical_knowledge_entries'"
            ).scalar()
            == 0
        )
        assert (
            connection.exec_driver_sql(
                "SELECT answer_text FROM interview_answers WHERE id='a1'"
            ).scalar()
            == "旧回答"
        )


@pytest.mark.asyncio
async def test_seeding_twice_keeps_one_row_per_card(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'seed.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=[Base.metadata.tables["technical_knowledge_entries"]]
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        assert await seed_technical_knowledge(session) == len(TECHNICAL_KNOWLEDGE)
        await session.commit()
    async with factory() as session:
        assert await seed_technical_knowledge(session) == 0
        await session.commit()
        count = await session.scalar(sa.text("SELECT COUNT(*) FROM technical_knowledge_entries"))
        assert count == len(TECHNICAL_KNOWLEDGE)
    await engine.dispose()


def test_task_links_preserve_historical_rows(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'task-links.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        legacy_database(connection)
        connection.exec_driver_sql("CREATE TABLE analysis_tasks (id CHAR(32) PRIMARY KEY)")
        module = migration("0023_interview_tasks.py")
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        assert connection.exec_driver_sql(
            "SELECT status, version, question_task_id FROM interview_sessions WHERE id='s1'"
        ).one() == ("pending", 3, None)
        assert connection.exec_driver_sql(
            "SELECT answer_text, version, feedback_task_id FROM interview_answers WHERE id='a1'"
        ).one() == ("旧回答", 2, None)
        connection.exec_driver_sql("INSERT INTO analysis_tasks VALUES ('task1')")
        connection.exec_driver_sql("UPDATE interview_answers SET feedback_task_id='task1'")
        connection.exec_driver_sql("DELETE FROM analysis_tasks WHERE id='task1'")
        assert connection.exec_driver_sql(
            "SELECT answer_text, feedback_task_id FROM interview_answers WHERE id='a1'"
        ).one() == ("旧回答", None)
