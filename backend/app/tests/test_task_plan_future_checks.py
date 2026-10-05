"""Future task checks are conditions, never already observed execution."""

from copy import deepcopy

import pytest

from evals.run_task_plan_quality import case_context, draft_probe, load_cases, validate_output


def probe():
    case = next(row for row in load_cases() if row["id"] == "api-run-record-missing")
    contexts, _, _ = case_context(case)
    return contexts, draft_probe(contexts[0], case["referenceDraft"])


@pytest.mark.parametrize("check", [
    "确认测试结果全部通过后归档运行记录",
    "待服务运行成功后保存具名运行记录",
    "核验测试用例全部通过后提交原始输出",
])
def test_future_execution_condition_in_task_checks_is_accepted(check):
    contexts, output = probe()
    output["items"][0]["task_plan"]["acceptance_checks"] = [check]
    assert validate_output(contexts, output)["accepted"]


@pytest.mark.parametrize("check", [
    "测试结果全部通过，归档运行记录",
    "已确认测试结果全部通过后归档运行记录",
    "确认测试结果全部通过后归档运行记录；服务运行成功",
    "确认测试结果全部通过后归档服务运行成功的声明",
    "确认测试结果全部通过后归档运行记录，证明本人具备开发能力",
])
def test_task_checks_cannot_turn_observed_or_ability_claims_into_conditions(check):
    contexts, output = probe()
    output["items"][0]["task_plan"]["acceptance_checks"] = [check]
    assert not validate_output(contexts, output)["accepted"]


@pytest.mark.parametrize("field", ["summary", "explanation", "information_gap"])
def test_conditional_exception_does_not_apply_to_analysis_conclusions(field):
    contexts, output = probe()
    output = deepcopy(output)
    target = output if field == "summary" else output["items"][0]
    target[field] = "确认测试结果全部通过后归档运行记录"
    assert not validate_output(contexts, output)["accepted"]
