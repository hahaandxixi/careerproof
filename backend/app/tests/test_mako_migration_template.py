"""Render the real Alembic template without loading an environment or database."""

import ast
import shutil
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_current_template_generates_valid_revision_without_database(tmp_path):
    source = Path(__file__).resolve().parents[2] / "alembic" / "script.py.mako"
    script_root = tmp_path / "isolated-migrations"
    script_root.mkdir()
    (script_root / "versions").mkdir()
    shutil.copyfile(source, script_root / "script.py.mako")
    config = Config()
    config.set_main_option("script_location", str(script_root))
    config.set_main_option("revision_environment", "false")
    # There is deliberately no env.py or database URL. Loading any environment
    # would fail rather than silently reaching developer/business data.
    revision = command.revision(
        config, message="synthetic template compatibility", rev_id="dep_mako_probe",
        autogenerate=False,
    )
    generated = Path(revision.path).read_text(encoding="utf-8")
    module = ast.parse(generated)
    functions = {node.name for node in module.body if isinstance(node, ast.FunctionDef)}
    assert functions == {"upgrade", "downgrade"}
    assert revision.revision == "dep_mako_probe"
    assert revision.down_revision is None
    assert "synthetic template compatibility" in generated
