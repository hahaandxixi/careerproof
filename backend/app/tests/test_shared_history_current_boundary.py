"""Goal 39: a current shared-account claim must not be exempted by the bare
word ``历史记录``.

Codex-reproduced miss: ``shared_history_attribution_impossible`` returned
False for 「项目当前共用账号，历史记录无法区分作者」 because the historical
word exempted the whole line, treating a CURRENT unattributable history as a
resolved old description. Red cases pin that the current claim fires and
rejects history-extraction plans exactly like the plain 「提交未区分作者」
wording. Green cases keep resolved old descriptions and independent named
new-evidence paths unrejected. Pure functions only; no DB/model/service.
"""

import pytest

from app.tools.task_boundaries import (
    shared_history_attribution_impossible,
    task_boundary_error,
)

CURRENT_HISTORY_SOURCE = "项目当前共用账号，历史记录无法区分作者"
CURRENT_PLAIN_SOURCE = "项目当前共用账号，提交未区分作者"


def extraction_plan_error(source: str):
    return task_boundary_error(
        deliverable="本人在小组项目中的具名提交清单",
        steps=["从提交历史筛出本人署名", "标注每项提交对应的责任范围"],
        acceptance_checks=["提交记录包含作者与时间", "责任范围与岗位要求逐条对应"],
        personal_source_texts=[source],
    )


# --- Red: 历史记录 must not exempt a currently unattributable history. ---


def test_current_shared_account_history_word_does_not_exempt():
    assert shared_history_attribution_impossible([CURRENT_HISTORY_SOURCE]) is True


def test_current_history_wording_rejects_extraction_like_plain_wording():
    assert extraction_plan_error(CURRENT_HISTORY_SOURCE) is not None
    assert extraction_plan_error(CURRENT_PLAIN_SOURCE) is not None


def test_mixed_past_and_current_facts_scope_check_fires_on_current_claim():
    # 旧事实与当前事实同句混合：当前仍无法归属 wins over the 此前 marker.
    assert (
        shared_history_attribution_impossible(["此前共用账号，当前提交仍无法区分作者"])
        is True
    )


# --- Green: resolved old descriptions and independent named proof stay legal. ---


def test_resolved_old_descriptions_are_not_triggered():
    sources = [
        "此前共用账号，历史记录曾无法区分作者，现已改用个人账号",
        "历史记录无法区分作者的问题已解决，提交现已区分作者",
        "此前共用账号，历史记录无法区分作者",
    ]
    for source in sources:
        assert shared_history_attribution_impossible([source]) is False, source


def test_resolved_old_description_does_not_reject_extraction_plan():
    assert (
        extraction_plan_error("此前共用账号，历史记录曾无法区分作者，现已改用个人账号")
        is None
    )


def test_independent_named_new_evidence_is_not_rejected():
    error = task_boundary_error(
        deliverable="本人贡献证明补交计划",
        steps=["先核对当前共用账号无法区分作者的边界，再补交独立具名的分工证明"],
        acceptance_checks=["贡献在独立材料核验前仍待核验"],
        personal_source_texts=[CURRENT_HISTORY_SOURCE],
    )
    assert error is None


def test_bare_personal_submission_list_without_extraction_claim_stays_allowed():
    # No 筛出本人署名 / 具名提交清单 shape: the plan does not claim to pull
    # author-distinguishable entries out of the unattributable history.
    error = task_boundary_error(
        deliverable="本人提交清单补交计划",
        steps=["下一版本补交本人提交清单并核对模块范围"],
        acceptance_checks=["补交前保持待核验标记"],
        personal_source_texts=[CURRENT_HISTORY_SOURCE],
    )
    assert error is None


# --- Codex independent holdouts (20261011-GLM-integration-codex): scope. ---


def test_holdout_resolved_current_account_stays_exempt():
    # 当前 belongs to the 已改用 clause, not to the earlier impossibility
    # clause; the resolved old description must stay exempt.
    assert (
        shared_history_attribution_impossible(
            ["此前共用账号，历史记录无法区分作者，当前已改用个人账号"]
        )
        is False
    )


def test_holdout_conditional_clause_does_not_suppress_later_fact():
    # 如果 scopes only its own clause; the later shared-account fact keeps
    # its association with the attribution statement and still triggers.
    assert (
        shared_history_attribution_impossible(
            ["如果后续增加分工证明会再核验；当前共用账号，历史记录无法区分作者"]
        )
        is True
    )


@pytest.mark.parametrize('source', [
    '登录缺陷已解决，仓库仍共用账号，提交未区分作者',
    '此前版本另有缺陷，当前共用账号，历史记录无法区分作者',
    '服务不再崩溃，项目共用账号，提交无法区分作者',
])
def test_unrelated_resolved_or_past_clause_cannot_hide_current_attribution_gap(source):
    assert shared_history_attribution_impossible([source]) is True
    assert extraction_plan_error(source) is not None


def test_explicit_future_personal_commits_are_not_extraction_of_old_history():
    assert task_boundary_error(
        deliverable='今后以个人账号提交新代码形成的具名提交清单',
        steps=['新代码提交前标注本人实现范围'],
        acceptance_checks=['新增记录核对前仍待核验'],
        personal_source_texts=[CURRENT_PLAIN_SOURCE],
    ) is None


def test_future_personal_work_does_not_rescue_separate_history_extraction_step():
    assert task_boundary_error(
        deliverable='今后以个人账号提交新代码形成的具名提交清单',
        steps=['从提交历史筛出本人署名'],
        acceptance_checks=['核对后归档'],
        personal_source_texts=[CURRENT_PLAIN_SOURCE],
    ) is not None
