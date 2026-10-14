"""Failed checkpoint updates must not corrupt the previous complete evidence."""
import json
from uuid import UUID

import pytest

from evals import release_smoke


def test_checkpoint_replace_failure_keeps_previous(tmp_path, monkeypatch):
    path = tmp_path / "run.json"
    path.write_text('{"status":"running","steps":["previous"]}', encoding="utf-8")
    previous = path.read_bytes()

    def fail_replace(*args):
        raise OSError("injected replacement failure")

    monkeypatch.setattr(release_smoke.os, "replace", fail_replace)
    with pytest.raises(OSError):
        release_smoke.save_checkpoint(path, {"status": "passed"})
    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]


def test_checkpoint_invalid_payload_keeps_previous(tmp_path):
    path = tmp_path / "run.json"
    path.write_text('{"status":"running"}', encoding="utf-8")
    previous = path.read_bytes()
    with pytest.raises(TypeError):
        release_smoke.save_checkpoint(path, {"invalid": object()})
    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]


def test_checkpoint_collision_preserves_unowned_temporary(tmp_path, monkeypatch):
    path = tmp_path / "run.json"
    path.write_text('{"status":"running"}', encoding="utf-8")
    token = UUID(int=1)
    monkeypatch.setattr(release_smoke, "uuid4", lambda: token)
    temporary = path.with_name(f".{path.name}.{token.hex}.tmp")
    temporary.write_text("foreign file", encoding="utf-8")
    with pytest.raises(FileExistsError):
        release_smoke.save_checkpoint(path, {"status": "passed"})
    assert json.loads(path.read_text()) == {"status": "running"}
    assert temporary.read_text() == "foreign file"


def test_checkpoint_success_leaves_complete_json(tmp_path):
    path = tmp_path / "run.json"
    path.write_text('{"status":"running"}', encoding="utf-8")
    result = {"status": "passed", "steps": ["完整检查点"]}
    release_smoke.save_checkpoint(path, result)
    assert json.loads(path.read_text(encoding="utf-8")) == result
    assert list(tmp_path.iterdir()) == [path]


def test_checkpoint_flush_failure_keeps_previous(tmp_path, monkeypatch):
    path = tmp_path / "run.json"
    path.write_text('{"status":"running"}', encoding="utf-8")
    previous = path.read_bytes()

    def fail_sync(*args):
        raise OSError("injected flush failure")

    monkeypatch.setattr(release_smoke.os, "fsync", fail_sync)
    with pytest.raises(OSError):
        release_smoke.save_checkpoint(path, {"status": "passed"})
    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.asyncio
async def test_failed_checkpoint_cannot_mask_original_failure(tmp_path, monkeypatch):
    original = RuntimeError("injected original smoke failure")
    monkeypatch.setattr(release_smoke, "validate_run", lambda *args: ({}, {}))

    async def fail_snapshot(*args):
        raise original

    def fail_save(*args):
        raise OSError("injected checkpoint failure")

    monkeypatch.setattr(release_smoke, "snapshot_hashes", fail_snapshot)
    monkeypatch.setattr(release_smoke, "save_checkpoint", fail_save)
    with pytest.raises(RuntimeError) as caught:
        await release_smoke.exercise("owned-test", tmp_path)
    assert caught.value is original
    path = tmp_path / ".tmp/release-smoke/owned-test.json"
    assert json.loads(path.read_text()) == {
        "runId": "owned-test", "status": "starting", "steps": []
    }
