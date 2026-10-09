"""Negative harness guards cannot access a foreign database or fabricate a window."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.tests.ops_hard_stop_worker import record_state, validate_config


def config(**changes):
    return {
        "database_url": "postgresql+asyncpg://synthetic:synthetic@127.0.0.1:5432/careerproof",
        "schema": f"cp_test_{uuid4().hex}",
        "task_id": str(uuid4()),
        "chain": "matching",
        "phase": "receipt_committed",
        "input_limit": 40000,
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"schema": "public"},
        {"schema": "cp_e2e_closure-20261005"},
        {"chain": "unknown"},
        {"phase": "after_fake_commit"},
        {"database_url": "postgresql+asyncpg://synthetic:synthetic@remote.invalid/careerproof"},
        {"database_url": "postgresql+asyncpg://synthetic:synthetic@localhost/production"},
        {"database_url": "sqlite+aiosqlite:///synthetic.sqlite"},
        {"input_limit": True},
        {"input_limit": 100001},
    ],
)
def test_invalid_worker_config_rejected_before_database_or_http(changes):
    with pytest.raises(ValueError):
        validate_config(config(**changes))


@pytest.mark.parametrize("chain", ["verification", "matching"])
def test_both_real_entry_chains_accept_only_own_local_scope(chain):
    assert validate_config(config(chain=chain)) == chain


def test_parent_observes_complete_old_marker_until_new_marker_is_published(tmp_path, monkeypatch):
    marker = tmp_path / "state.json"
    before = {"event": "preflight_ok"}
    after = {"event": "hanging", "nonce": uuid4().hex}
    record_state(marker, before)
    original_replace = Path.replace
    observed = []

    def observe_before_publication(pending, destination):
        observed.append(json.loads(marker.read_text(encoding="utf-8")))
        assert json.loads(pending.read_text(encoding="utf-8")) == after
        return original_replace(pending, destination)

    monkeypatch.setattr(Path, "replace", observe_before_publication)
    record_state(marker, after)
    assert observed == [before]
    assert json.loads(marker.read_text(encoding="utf-8")) == after
