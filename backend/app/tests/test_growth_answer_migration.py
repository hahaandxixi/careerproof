"""Real SQLite upgrade/downgrade of the draft table preserves legacy frozen rows."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations


def migration(name):
    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_growth_answer_draft_migration_roundtrip_preserves_legacy_rows(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'answer-draft-migration.db'}")
    growth = migration("0009_evidence_growth.py")
    target = migration("0014_growth_target_job.py")
    drafts = migration("0015_growth_answer_drafts.py")
    insert_draft = (
        "INSERT INTO growth_answer_drafts "
        '(id,growth_task_id,text,"references",revision,created_at,updated_at) '
        "VALUES (?,?,?,?,?,?,?)"
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        for table in ("users", "match_reports", "analysis_tasks", "jobs", "applications"):
            connection.exec_driver_sql(
                f"CREATE TABLE {table} (id CHAR(32) PRIMARY KEY, payload TEXT)"
            )
        connection.exec_driver_sql(
            "INSERT INTO users VALUES (?,?)", ("a" * 32, '{"user":"legacy"}')
        )
        connection.exec_driver_sql(
            "INSERT INTO match_reports VALUES (?,?)", ("a" * 32, '{"report":"frozen"}')
        )
        connection.exec_driver_sql(
            "INSERT INTO applications VALUES (?,?)", ("a" * 32, '{"delivery":"snapshot"}')
        )
        with Operations.context(MigrationContext.configure(connection)):
            growth.upgrade()
        connection.exec_driver_sql(
            "INSERT INTO evidence_growth_tasks "
            "(id,created_by,base_report_id,requirement_id,base_snapshot,plan,materials,status,"
            "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "b" * 32,
                "a" * 32,
                "a" * 32,
                "c" * 32,
                '{"report":"frozen"}',
                '{"steps":["synthetic"]}',
                "[]",
                "planned",
                "2026-10-05",
                "2026-10-05",
            ),
        )
        connection.exec_driver_sql(
            "INSERT INTO evidence_growth_tasks "
            "(id,created_by,base_report_id,requirement_id,base_snapshot,plan,materials,status,"
            "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "f" * 32,
                "a" * 32,
                "a" * 32,
                "d" * 32,
                '{"report":"frozen"}',
                '{"steps":["synthetic"]}',
                "[]",
                "planned",
                "2026-10-05",
                "2026-10-05",
            ),
        )
        with Operations.context(MigrationContext.configure(connection)):
            target.upgrade()
        legacy_task = "SELECT * FROM evidence_growth_tasks WHERE id=?"
        before = (
            connection.exec_driver_sql(legacy_task, ("b" * 32,)).one(),
            connection.exec_driver_sql("SELECT payload FROM match_reports").one(),
            connection.exec_driver_sql("SELECT payload FROM applications").one(),
        )

        with Operations.context(MigrationContext.configure(connection)):
            drafts.upgrade()
        connection.exec_driver_sql(
            insert_draft,
            (
                "e" * 32,
                "b" * 32,
                "草稿正文\n保留换行",
                '[{"reportId":"legacy"}]',
                1,
                "2026-10-05",
                "2026-10-05",
            ),
        )
        connection.exec_driver_sql(
            insert_draft,
            ("g" * 32, "f" * 32, "级联草稿", "[]", 1, "2026-10-05", "2026-10-05"),
        )
        # One draft per growth task.
        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.exec_driver_sql(
                insert_draft,
                ("h" * 32, "b" * 32, "重复任务", "[]", 1, "2026-10-05", "2026-10-05"),
            )
        # Deleting the parent task cascades to its draft.
        connection.exec_driver_sql("DELETE FROM evidence_growth_tasks WHERE id=?", ("f" * 32,))
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM growth_answer_drafts WHERE growth_task_id=?", ("f" * 32,)
            ).scalar()
            == 0
        )

        with Operations.context(MigrationContext.configure(connection)):
            drafts.downgrade()
        assert "growth_answer_drafts" not in sa.inspect(connection).get_table_names()
        after = (
            connection.exec_driver_sql(legacy_task, ("b" * 32,)).one(),
            connection.exec_driver_sql("SELECT payload FROM match_reports").one(),
            connection.exec_driver_sql("SELECT payload FROM applications").one(),
        )
        assert after == before  # legacy task/report/delivery JSON untouched by the round trip
    engine.dispose()
