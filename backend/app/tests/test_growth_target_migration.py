"""Real SQLite upgrade/downgrade preserves legacy frozen task data."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from alembic.migration import MigrationContext
from alembic.operations import Operations


def migration(name):
    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_growth_target_upgrade_foreign_key_and_downgrade_preserve_snapshot(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'growth-migration.db'}")
    old = migration("0009_evidence_growth.py")
    new = migration("0014_growth_target_job.py")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        for table in ("users", "match_reports", "analysis_tasks", "jobs"):
            connection.exec_driver_sql(f"CREATE TABLE {table} (id CHAR(32) PRIMARY KEY)")
            connection.exec_driver_sql(f"INSERT INTO {table} VALUES (?)", ("a" * 32,))
        with Operations.context(MigrationContext.configure(connection)):
            old.upgrade()
        connection.exec_driver_sql(
            "INSERT INTO evidence_growth_tasks "
            "(id,created_by,base_report_id,requirement_id,base_snapshot,plan,materials,status,"
            "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("b" * 32, "a" * 32, "a" * 32, "c" * 32, '{"report":"frozen"}',
             '{"steps":["synthetic"]}', '[]', "planned", "2026-10-05", "2026-10-05"),
        )
        original = connection.exec_driver_sql("SELECT * FROM evidence_growth_tasks").one()
        with Operations.context(MigrationContext.configure(connection)):
            new.upgrade()
        assert connection.exec_driver_sql(
            "SELECT target_job_id FROM evidence_growth_tasks"
        ).scalar() is None
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.exec_driver_sql(
                "UPDATE evidence_growth_tasks SET target_job_id=?", ("d" * 32,)
            )
        connection.exec_driver_sql(
            "UPDATE evidence_growth_tasks SET target_job_id=?", ("a" * 32,)
        )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.exec_driver_sql("DELETE FROM jobs")
        with Operations.context(MigrationContext.configure(connection)):
            new.downgrade()
        assert connection.exec_driver_sql("SELECT * FROM evidence_growth_tasks").one() == original
        assert "target_job_id" not in {
            column["name"] for column in sa.inspect(connection).get_columns("evidence_growth_tasks")
        }
    engine.dispose()
