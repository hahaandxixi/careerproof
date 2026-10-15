"""0019 rejects corrupt inputs without discarding consent or dependent history."""

import re

import pytest
import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.core.database import Base
from app.models.analysis import MatchItem
from app.models.enums import MatchVerdict
from app.tests.test_ai_request_attempt_migration import attempt_pg as attempt_pg
from app.tests.test_ai_request_attempt_migration import migration

REVISION = "0019_data_integrity_constraints.py"
VERDICTS = {"supported", "partial", "claimed_only", "gap", "unsupported"}
INDEXES = {
    "applications": {"ix_applications_student_created", "ix_applications_job_created",
                     "uq_applications_active_job_student"},
    "analysis_tasks": {"ix_analysis_tasks_owner_type_status_created"},
    "match_reports": {"ix_match_reports_job_candidate_created"},
    "notifications": {"ix_notifications_recipient_unread"},
}
INVALID = [
    ("applications", "status"), ("applications", "reply_kind"),
    ("jobs", "status"), ("job_requirements", "normalized_status"),
    ("match_items", "verdict"),
]


def legacy(c):
    for ddl in [
        "jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL)",
        "job_requirements (id TEXT PRIMARY KEY, job_id TEXT REFERENCES jobs(id) "
        "ON DELETE CASCADE, normalized_status TEXT NOT NULL)",
        "applications (id TEXT PRIMARY KEY, job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE, "
        "student_id TEXT NOT NULL, status TEXT NOT NULL, reply_kind TEXT, "
        "created_at TEXT NOT NULL, report_snapshot TEXT NOT NULL)",
        "application_events (id TEXT PRIMARY KEY, application_id TEXT REFERENCES "
        "applications(id) ON DELETE CASCADE, detail TEXT)",
        "notifications (id TEXT PRIMARY KEY, event_id TEXT REFERENCES application_events(id) "
        "ON DELETE CASCADE, recipient_id TEXT NOT NULL, read_at TEXT)",
        "match_items (id TEXT PRIMARY KEY, report_id TEXT NOT NULL, "
        "requirement_id TEXT NOT NULL, verdict TEXT NOT NULL)",
        "analysis_tasks (id TEXT PRIMARY KEY, created_by TEXT, task_type TEXT, "
        "status TEXT, created_at TEXT)",
        "match_reports (id TEXT PRIMARY KEY, job_id TEXT, candidate_ref TEXT, created_at TEXT)",
    ]:
        c.exec_driver_sql("CREATE TABLE " + ddl)
    c.exec_driver_sql("CREATE UNIQUE INDEX uq_applications_active_job_student "
                     "ON applications(job_id,student_id) WHERE status != 'withdrawn'")
    for statement in [
        "INSERT INTO jobs VALUES ('j','published')",
        "INSERT INTO job_requirements VALUES ('q','j','normalized')",
        "INSERT INTO applications VALUES ('a','j','s','withdrawn',NULL,'2026','frozen')",
        "INSERT INTO application_events VALUES ('e','a','withdrawn')",
        "INSERT INTO notifications VALUES ('n','e','s',NULL)",
        "INSERT INTO match_items VALUES ('i','r','q','partial')",
    ]:
        c.exec_driver_sql(statement)


def snapshot(c):
    return {t: c.exec_driver_sql(f"SELECT * FROM {t} ORDER BY id").all() for t in
            ("jobs", "job_requirements", "applications", "application_events",
             "notifications", "match_items")}


def exercise(c):
    legacy(c)
    before = snapshot(c)
    m = migration(REVISION)
    with Operations.context(MigrationContext.configure(c)):
        m.upgrade()
    assert snapshot(c) == before
    for table, column in INVALID:
        with pytest.raises(sa.exc.IntegrityError), c.begin_nested():
            c.exec_driver_sql(f"UPDATE {table} SET {column}='bogus'")
    with pytest.raises(sa.exc.IntegrityError), c.begin_nested():
        c.exec_driver_sql("INSERT INTO match_items VALUES ('duplicate','r','q','supported')")
    for table, names in INDEXES.items():
        assert names <= {i['name'] for i in sa.inspect(c).get_indexes(table)}
    assert "uq_match_items_report_requirement" in {
        x['name'] for x in sa.inspect(c).get_unique_constraints('match_items')}
    for table, column in INVALID:
        assert f"ck_{table}_{column}" in {
            x['name'] for x in sa.inspect(c).get_check_constraints(table)}
    with Operations.context(MigrationContext.configure(c)):
        m.downgrade()
    assert snapshot(c) == before
    # Constraints actually disappeared; rollback the test mutation before re-upgrading.
    with c.begin_nested() as savepoint:
        c.exec_driver_sql("UPDATE match_items SET verdict='bogus'")
        savepoint.rollback()
    with Operations.context(MigrationContext.configure(c)):
        m.upgrade()
    assert snapshot(c) == before
    # Both historical withdrawals and one fresh active consent remain representable.
    c.exec_driver_sql("INSERT INTO applications VALUES "
                     "('new','j','s','submitted',NULL,'2027','new')")
    with pytest.raises(sa.exc.IntegrityError), c.begin_nested():
        c.exec_driver_sql("INSERT INTO applications VALUES "
                         "('dup','j','s','viewed',NULL,'2028','dup')")


def test_sqlite_integrity_roundtrip(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'integrity.db'}")
    try:
        with engine.begin() as c:
            exercise(c)
    finally:
        engine.dispose()


async def test_postgres_integrity_roundtrip(attempt_pg):  # noqa: F811
    engine, schema = attempt_pg
    async with engine.begin() as c:
        assert await c.scalar(sa.text('SELECT current_schema()')) == schema
        await c.run_sync(exercise)


@pytest.mark.parametrize(('table', 'column'), INVALID)
def test_sqlite_invalid_legacy_refused_before_ddl(tmp_path, table, column):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'invalid.db'}")
    try:
        with engine.begin() as c:
            legacy(c)
            c.exec_driver_sql(f"UPDATE {table} SET {column}='bogus'")
            before = snapshot(c)
            with pytest.raises(RuntimeError, match=table), Operations.context(
                MigrationContext.configure(c)
            ):
                migration(REVISION).upgrade()
            assert snapshot(c) == before
            assert not sa.inspect(c).get_check_constraints('applications')
    finally:
        engine.dispose()


def test_sqlite_duplicate_legacy_refused_before_ddl(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'duplicate.db'}")
    try:
        with engine.begin() as c:
            legacy(c)
            c.exec_driver_sql("INSERT INTO match_items VALUES ('dup','r','q','gap')")
            before = snapshot(c)
            with pytest.raises(RuntimeError, match='match_items'), Operations.context(
                MigrationContext.configure(c)
            ):
                migration(REVISION).upgrade()
            assert snapshot(c) == before
            assert not sa.inspect(c).get_check_constraints('applications')
    finally:
        engine.dispose()


def test_sqlite_foreign_keys_guard(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'fk.db'}")
    try:
        with engine.begin() as c:
            c.exec_driver_sql('PRAGMA foreign_keys=ON')
            with pytest.raises(RuntimeError, match='foreign_keys'), Operations.context(
                MigrationContext.configure(c)
            ):
                migration(REVISION).upgrade()
    finally:
        engine.dispose()


def test_model_verdict_constraint_matches_enum_and_writer_contract():
    assert {v.value for v in MatchVerdict} == VERDICTS
    constraint = next(c for c in MatchItem.__table__.constraints
                      if c.name == 'ck_match_items_verdict')
    assert set(re.findall(r"'([^']+)'", str(constraint.sqltext))) == VERDICTS


def test_model_checks_and_index_columns_match_revision():
    m = migration(REVISION)
    for table, checks in m.CHECKS.items():
        constraints = {c.name: str(c.sqltext) for c in Base.metadata.tables[table].constraints
                       if isinstance(c, sa.CheckConstraint)}
        for column, expression in checks.items():
            assert constraints[f'ck_{table}_{column}'] == expression
    for table, name, columns in m.INDEXES:
        index = next(i for i in Base.metadata.tables[table].indexes if i.name == name)
        assert [c.name for c in index.columns] == columns
        if table == 'notifications':
            for dialect in ('sqlite', 'postgresql'):
                assert str(index.dialect_options[dialect]['where']) == 'read_at IS NULL'


@pytest.mark.parametrize(('table', 'column'), [*INVALID, ('match_items', None)])
async def test_postgres_invalid_legacy_refused_before_ddl(attempt_pg, table, column):  # noqa: F811
    engine, schema = attempt_pg

    def check(c):
        legacy(c)
        if column is None:
            c.exec_driver_sql("INSERT INTO match_items VALUES ('dup','r','q','gap')")
        else:
            c.exec_driver_sql(f"UPDATE {table} SET {column}='bogus'")
        before = snapshot(c)
        with pytest.raises(RuntimeError, match=table), Operations.context(
            MigrationContext.configure(c)
        ):
            migration(REVISION).upgrade()
        assert snapshot(c) == before
        assert not sa.inspect(c).get_check_constraints('applications')

    async with engine.begin() as c:
        assert await c.scalar(sa.text('SELECT current_schema()')) == schema
        await c.run_sync(check)
