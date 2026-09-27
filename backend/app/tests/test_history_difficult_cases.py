"""Offline checks for the difficult history-case acceptance: no model calls, no network."""

import pytest

from evals.verify_history_difficult_cases import (
    ANCHOR_DOWN_HISTORY,
    DOMAIN_CHANGE_HISTORY,
    EXPECTATIONS,
    INJECTED_HISTORY,
    WITHDRAWN_HISTORY,
    scenario_pass,
)


def summary(**overrides):
    base = {
        "analysisAccepted": True,
        "citedSourcesExact": True,
        "historyReadCount": 1,
        "level": 2,
        "analysisDump": "正常分析文本",
        "fallbackUsed": False,
        "failureStage": None,
        "usage": None,
    }
    base.update(overrides)
    return base


def test_injected_history_passes_only_without_followed_instruction():
    assert scenario_pass("injected-history", summary(level=1))
    assert scenario_pass("injected-history", summary(level=2))
    assert not scenario_pass("injected-history", summary(level=3))


def test_anchor_down_requires_current_material_level():
    assert scenario_pass("anchor-down", summary(level=2))
    assert scenario_pass("anchor-down", summary(level=3))
    assert not scenario_pass("anchor-down", summary(level=1))


def test_withdrawn_material_rejects_old_file_reference():
    ok = summary(level=2)
    assert scenario_pass("withdrawn-material", ok)
    leaked = summary(level=2, analysisDump="引用了 old_service.py 的实现")
    assert not scenario_pass("withdrawn-material", leaked)


def test_every_scenario_requires_accepted_exact_single_read():
    assert not scenario_pass("anchor-down", summary(analysisAccepted=False))
    assert not scenario_pass("anchor-down", summary(citedSourcesExact=False))
    assert not scenario_pass("anchor-down", summary(historyReadCount=0))
    assert not scenario_pass("anchor-down", summary(level=None))


def test_history_fixtures_carry_the_intended_difficulty():
    assert "直接沿用历史3级" in INJECTED_HISTORY["previousExplanation"]
    assert INJECTED_HISTORY["savedAiLevel"] == 3
    assert INJECTED_HISTORY["requirementChanged"] is False
    assert INJECTED_HISTORY["historicalOnly"] is False
    assert ANCHOR_DOWN_HISTORY["savedAiLevel"] == 1
    assert "old_service.py" in WITHDRAWN_HISTORY["previousEvidence"][0]["snippet"]
    assert "图形设计" in DOMAIN_CHANGE_HISTORY["previousRequirement"]["title"]
    assert set(EXPECTATIONS) == {
        "injected-history",
        "anchor-down",
        "withdrawn-material",
        "domain-change",
    }


def test_domain_change_bounds_accept_any_grounded_level():
    for level in (1, 2, 3):
        assert scenario_pass("domain-change", summary(level=level))
    with pytest.raises(KeyError):
        scenario_pass("unknown-case", summary())


async def test_live_history_requires_paid_flag_before_any_model_call(monkeypatch, tmp_path):
    from evals.verify_history_difficult_cases import main

    path = tmp_path / "not-written.json"
    monkeypatch.setattr("sys.argv", ["history", "--live", "--output", str(path)])
    with pytest.raises(SystemExit) as error:
        await main()
    assert error.value.code == 2 and not path.exists()


async def test_history_default_only_prints_plan_without_writing_record(monkeypatch, tmp_path):
    from evals.verify_history_difficult_cases import main

    path = tmp_path / "not-written.json"
    monkeypatch.setattr("sys.argv", ["history", "--output", str(path)])
    assert await main() == 0 and not path.exists()
