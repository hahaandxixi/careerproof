import pytest

from app.tools.task_boundaries import (
    conflicting_implementation_sources,
    task_boundary_error,
    unsupported_attribution,
)


@pytest.mark.parametrize("text", [
    "直接提交小组项目报告作为个人贡献",
    "小组报告可证明本人负责后端模块",
    "引用参考仓库的统计查询作为个人实践",
    "参考实现可作为本人 SQL 能力证明",
    "将第三方代码计入个人实践成果",
])
def test_group_and_reference_substitution_rejected(text):
    assert unsupported_attribution(text)


@pytest.mark.parametrize("text", [
    "不能将参考实现作为个人实践",
    "参考实现不可作为个人能力证明",
    "小组报告不等于个人贡献",
    "核对小组报告是否证明本人负责模块",
    "上传本人负责模块的贡献证明并核对提交记录",
    "声称小组报告可证明本人贡献，此声明待核验，不作为事实",
    "对照参考样例后补充本人实践记录",
])
def test_uncertain_and_future_personal_proof_not_rejected(text):
    assert not unsupported_attribution(text)


def test_named_conflict_needs_parallel_pending_source_check():
    sources = ["导出功能已实现，支持CSV。", "导出功能尚未实现，按钮占位。"]
    assert conflicting_implementation_sources(sources)
    assert task_boundary_error(
        deliverable="导出功能验收说明", steps=["按导出功能说明归档结论"],
        acceptance_checks=["导出功能按已实现归档"], personal_source_texts=sources,
    ) is not None
    assert task_boundary_error(
        deliverable="冲突材料待核验记录", steps=["并列两处来源，分别核对版本和时间"],
        acceptance_checks=["保留待核验状态"], personal_source_texts=sources,
    ) is None


def test_different_version_or_conditional_statement_is_not_conflict():
    assert not conflicting_implementation_sources([
        "v1导出功能尚未实现。", "v2导出功能已实现。",
    ])
    assert not conflicting_implementation_sources([
        "如果导出功能已实现，应记录响应。", "导出功能尚未实现。",
    ])


def test_complete_scope_requires_check_or_completion_not_repeat_upload():
    args = dict(deliverable="缓存完整功能验收记录",
                acceptance_checks=["读写与过期行为有记录"], personal_source_texts=[])
    assert task_boundary_error(steps=["对完整缓存链路执行验收"], **args) is not None
    assert task_boundary_error(
        steps=["核对现有读写范围，补齐缺失分支后验收"], **args,
    ) is None
    assert task_boundary_error(
        deliverable="完整测试日志", steps=["运行现有具名函数并记录结果"],
        acceptance_checks=["日志含命令与环境"], personal_source_texts=[],
    ) is None


def test_case_reference_drafts_keep_pending_verification_boundary():
    # The authored case-library reference drafts state the refusal / pending /
    # future-supplement boundary explicitly; the pure module must keep them.
    assert task_boundary_error(
        deliverable="缓存读路径说明与写路径实现补全",
        steps=["标注已实现的读路径片段与行号", "补充写路径与过期策略的实现步骤及测试计划"],
        acceptance_checks=["已实现部分与缺失分支分别列出", "写路径实现前不标记缓存完整可用"],
        personal_source_texts=["@lru_cache(maxsize=128)\ndef cache_get(key):"],
    ) is None
    assert task_boundary_error(
        deliverable="个人负责模块的提交与边界说明",
        steps=["列出本人提交的模块文件与对应提交记录", "标注与他人协作部分的接口边界"],
        acceptance_checks=["每项职责可对应到具名提交", "协作边界有双方确认记录"],
        personal_source_texts=["后端：由小组协作完成，具体分工见附件"],
    ) is None
    assert task_boundary_error(
        deliverable="冲突材料核验记录",
        steps=["并列两处陈述的出处与行号", "将结论状态标记为待核验", "分别核实来源后再更新结论"],
        acceptance_checks=["结论前保留冲突待核验标记", "不单独采信任一来源"],
        personal_source_texts=["导出功能已实现，支持CSV。", "导出功能尚未实现，按钮占位。"],
    ) is None
    assert task_boundary_error(
        deliverable="参考样例定位与个人实践差距说明",
        steps=["标注参考 SQL 的来源与作用", "对比说明本人当前缺少的实践记录"],
        acceptance_checks=["参考材料标注为第三方来源", "不将参考实现计入个人证据"],
        personal_source_texts=["计划为订单模块补充统计查询，当前只有需求说明。"],
    ) is None


def test_future_contribution_proof_delivery_is_not_treated_as_proven():
    # Naming a future "personal contribution proof" deliverable is a future
    # supplement plan, not an assertion that the group artifact proves it now.
    group_source = ["仓库提交：全组共用账号，未区分作者"]
    assert task_boundary_error(
        deliverable="本人贡献证明补交计划",
        steps=["下一版本补交本人负责模块的贡献证明并核对提交记录"],
        acceptance_checks=["补交前计划不得标记为已完成"],
        personal_source_texts=group_source,
    ) is None
