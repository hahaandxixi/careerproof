# -*- coding: utf-8 -*-
"""AI-01-R2 independent read-only review probes.

In-memory synthetic material only: pure function calls, no database, no
browser, no service, no network, no real model, no file writes elsewhere.
Run from backend/ with the project venv python.

Exit code: 0 = all probes matched expectations; 1 = at least one
counterexample (actual != expected).
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from app.tools.task_boundaries import (  # noqa: E402
    conflicting_implementation_sources,
    task_boundary_error,
    unsupported_attribution,
)
from app.agents.contracts import (  # noqa: E402
    AIRequirementAnalysis,
    EvidenceAnalysis,
    EvidenceCandidate,
    EvidenceTaskPlan,
    RequirementEvidenceContext,
    overclaim_flags,
    validate_grounded_analysis,
)

ROWS = []


def record(pid, category, input_desc, expected, actual, note):
    ok = expected == actual
    ROWS.append((pid, category, ok, input_desc, expected, actual, note))
    tag = "MATCH  " if ok else "COUNTEREXAMPLE"
    print(f"[{tag}] {pid} ({category})")
    print(f"  输入: {input_desc}")
    print(f"  预期: {expected}")
    print(f"  实际: {actual}")
    print(f"  说明: {note}")
    print()


def expect_error(fn):
    try:
        result = fn()
    except ValueError as exc:
        return f"ValueError: {exc}"
    return repr(result)


# ---------------------------------------------------------------- controls
record(
    "CTL-1", "控制", "unsupported_attribution('直接提交小组项目报告作为个人贡献')",
    "True", repr(unsupported_attribution("直接提交小组项目报告作为个人贡献")),
    "既有红灯行为仍应拒绝肯定替代归属",
)
record(
    "CTL-2", "控制", "unsupported_attribution('核对小组报告是否证明本人负责模块')",
    "False", repr(unsupported_attribution("核对小组报告是否证明本人负责模块")),
    "既有允许例：是否 型核验计划",
)

# --------------------------------------- A. 误拒合法否定/待核验/未来补证
record(
    "A1", "误拒合法否定", "unsupported_attribution('核对小组报告能否证明本人负责模块')",
    "False", repr(unsupported_attribution("核对小组报告能否证明本人负责模块")),
    "能否 与既有允许词 是否 仅一字之差；能否 未列入 _UNCERTAIN，核验计划被误拒",
)
record(
    "A2", "误拒待核验", "unsupported_attribution('声称小组报告可证明本人贡献。此声明不作为事实，仅保留待核验。')",
    "False",
    repr(unsupported_attribution("声称小组报告可证明本人贡献。此声明不作为事实，仅保留待核验。")),
    "拒绝采纳声明放在下一句（句号分句）时 声称+拒绝 豁免失效；逗号版（既有允许例）通过",
)
record(
    "A2c", "控制", "unsupported_attribution('声称小组报告可证明本人贡献，此声明待核验，不作为事实')",
    "False", repr(unsupported_attribution("声称小组报告可证明本人贡献，此声明待核验，不作为事实")),
    "逗号版允许例（回归测试同款）",
)
record(
    "A3", "误拒本人具名小组提交记录",
    "task_boundary_error(deliverable='个人贡献证据补充说明', steps=['补充小组仓库中本人具名的提交记录作为个人贡献证明'], acceptance_checks=['每项职责对应到具名提交'])",
    "None",
    repr(task_boundary_error(
        deliverable="个人贡献证据补充说明",
        steps=["补充小组仓库中本人具名的提交记录作为个人贡献证明"],
        acceptance_checks=["每项职责对应到具名提交"],
        personal_source_texts=[],
    )),
    "前次审计明示不拦‘小组项目中本人具名提交记录’；小组仓库 措辞被当作群体产物误拒",
)
record(
    "A3c", "控制", "task_boundary_error(steps=['列出小组项目中本人具名的提交记录'], ...)",
    "None",
    repr(task_boundary_error(
        deliverable="个人贡献证据补充说明",
        steps=["列出小组项目中本人具名的提交记录"],
        acceptance_checks=["每项职责对应到具名提交"],
        personal_source_texts=[],
    )),
    "小组项目 措辞按审计意图放行；与 A3 对比显示同类合法输入仅因词形不同结果相反",
)
record(
    "A4", "误拒合法否定（长距离否定）",
    "unsupported_attribution('写明小组项目成果不能在缺少本人具名提交记录、模块分工表、时间戳与代码评审意见的验收流程中证明本人负责后端模块')",
    "False",
    repr(unsupported_attribution(
        "写明小组项目成果不能在缺少本人具名提交记录、模块分工表、时间戳与代码评审意见的验收流程中证明本人负责后端模块")),
    "否定词距动词超过25字且无逗号重置窗口时，不能 前缀保护失效",
)
record(
    "A5", "待讨论边界（待核验无声称）",
    "unsupported_attribution('小组报告可作为本人贡献，此说法待核验')",
    "待讨论", repr(unsupported_attribution("小组报告可作为本人贡献，此说法待核验")),
    "待核验 但无 声称 框架：设计可能有意要求声称框架，不判缺陷，仅记录",
)
record(
    "A6", "待讨论边界（未来验收措辞）",
    "overclaim_flags('确认测试结果全部通过后归档运行记录')",
    "待讨论（设计可能要求区分未然/已然）", repr(overclaim_flags("确认测试结果全部通过后归档运行记录")),
    "验收检查里的未来验证意图命中 execution_claim；不判确定缺陷，记录词法局限",
)

# ------------------------------------------------- B. 漏接非法个人归因
record(
    "B1", "漏接（动词缺口）", "unsupported_attribution('将小组项目成果当作本人实践成果提交')",
    "True", repr(unsupported_attribution("将小组项目成果当作本人实践成果提交")),
    "当作 不在动词枚举 作为|证明|证实|等同|归为|计入 内",
)
record(
    "B2", "漏接（动词缺口）", "unsupported_attribution('将参考实现视为本人实践成果')",
    "True", repr(unsupported_attribution("将参考实现视为本人实践成果")),
    "视为 不在动词枚举内",
)
record(
    "B3", "漏接（来源词缺口）", "unsupported_attribution('将他人完成的导出模块计入个人实践成果')",
    "True", repr(unsupported_attribution("将他人完成的导出模块计入个人实践成果")),
    "他人 不在来源枚举 参考|第三方|小组|团队 内",
)
record(
    "B4", "漏接（来源词缺口）", "unsupported_attribution('将同学整理的接口文档视为本人接口能力证明')",
    "True", repr(unsupported_attribution("将同学整理的接口文档视为本人接口能力证明")),
    "同学/课程设计等同类来源词均未覆盖",
)

# --------------------------------- C. 来源冲突未正确降级 / 误当冲突
CONFLICT_PAIR = ["导出功能已实现，支持CSV。", "导出功能尚未实现，按钮占位。"]
record(
    "C1", "误当冲突（本人旧日志演进）",
    "conflicting_implementation_sources(['FastAPI未实现的部分已由本人补全，含过期分支。', 'FastAPI已实现，支持过期与并发。'])",
    "False（未实现的部分已补全=演进，非冲突）",
    repr(conflicting_implementation_sources([
        "FastAPI未实现的部分已由本人补全，含过期分支。",
        "FastAPI已实现，支持过期与并发。",
    ])),
    "行首最左解析只取 未实现，丢掉 已由本人补全；同一来源历史与现状被判冲突",
)
record(
    "C1b", "误当冲突导致的误拒",
    "task_boundary_error(..., personal_source_texts=['FastAPI未实现的部分已由本人补全，含过期分支。', 'FastAPI已实现，支持过期与并发。'], 普通验收计划)",
    "None",
    repr(task_boundary_error(
        deliverable="FastAPI缓存过期分支说明",
        steps=["运行缓存过期分支并记录输出"],
        acceptance_checks=["运行记录与实现版本可对应"],
        personal_source_texts=[
            "FastAPI未实现的部分已由本人补全，含过期分支。",
            "FastAPI已实现，支持过期与并发。",
        ],
    )),
    "合法计划被要求三组冲突标记词，否则拒绝",
)
record(
    "C2", "误当冲突（带日期旧记录）",
    "task_boundary_error(..., personal_source_texts=['导出功能已实现，支持CSV。', '导出功能尚未实现，2025年1月旧记录。'], 普通验收计划)",
    "None（旧记录=版本化演进，不得误当冲突）",
    repr(task_boundary_error(
        deliverable="导出功能验收归档",
        steps=["运行导出功能并记录输出"],
        acceptance_checks=["导出结果有记录"],
        personal_source_texts=["导出功能已实现，支持CSV。", "导出功能尚未实现，2025年1月旧记录。"],
    )),
    "旧版 跳过仅存在于 contracts 的旧日志守卫；冲突检查无任何时间/版本限定词豁免",
)
record(
    "C3", "漏接（静默选边可带齐标记词）",
    "task_boundary_error(冲突来源, deliverable='导出功能冲突背景与归档说明', steps=['按已实现一侧归档导出结论，分别注明其余来源位置'], acceptance_checks=['版本差异后续待核验'])",
    "非None（归档选边结论违反‘不静默选边’）",
    repr(task_boundary_error(
        deliverable="导出功能冲突背景与归档说明",
        steps=["按已实现一侧归档导出结论，分别注明其余来源位置"],
        acceptance_checks=["版本差异后续待核验"],
        personal_source_texts=CONFLICT_PAIR,
    )),
    "三组标记词（冲突/待核验/分别）凑齐即放行，实际仍采信一侧；词法守卫可绕过",
)
record(
    "C4", "待讨论边界（语序变体漏接）",
    "conflicting_implementation_sources(['未实现导出功能。', '导出功能已实现。'])",
    "待讨论（设计声明仅同一主语前缀形态）",
    repr(conflicting_implementation_sources(["未实现导出功能。", "导出功能已实现。"])),
    "否定前置的行无法匹配 ^主语+状态+实现；设计文档已声明窄范围，不判缺陷",
)

# --------------------- D. contracts.py 既有守卫（HEAD 已存在，非本次改动引入）
GAP_CONTEXT = RequirementEvidenceContext(
    requirement_id="R1",
    requirement_title="实现 Redis 缓存读写并记录运行结果",
    skill="FastAPI",
    verdict="gap",
    rule_score=0.0,
    claimed=True,
    claim_text="熟悉 FastAPI 缓存。",
    evidence=[EvidenceCandidate(
        citation_id="R1-E1",
        file_path="app/cache.py",
        line_start=1,
        line_end=3,
        evidence_type="semantic_document_candidate",
        strength="low",
        snippet="FastAPI过期分支未实现，已列入补全计划。",
        context_complete=False,
        provenance="portfolio",
    )],
)

D1_ANALYSIS = EvidenceAnalysis(
    summary="本次为缓存要求整理缺口与补全计划。",
    items=[AIRequirementAnalysis(
        requirement_id="R1",
        explanation="材料说明过期分支当前缺失，需要先补全再验证。",
        citation_ids=["R1-E1"],
        information_gap="过期分支缺少实现与运行记录",
        suggestion="补充过期分支实现说明后再运行验证",
        task_plan=EvidenceTaskPlan(
            deliverable="FastAPI过期分支补全与运行记录",
            steps=["补全FastAPI过期分支实现后运行并记录输出"],
            acceptance_checks=["运行记录与补全代码可对应"],
        ),
        confidence=0.8,
    )],
    model="synthetic-probe",
)
record(
    "D1", "contracts既有守卫（补全动词缺口）",
    "validate_grounded_analysis(gap上下文, 计划=补全实现后运行记录输出)",
    "None（设计要求‘补全实现，再进入验收’，该计划先补全后运行应放行）",
    expect_error(lambda: validate_grounded_analysis([GAP_CONTEXT], D1_ANALYSIS)),
    "runtime守卫动词表 缺 补全/补齐（而 _SCOPE_CHECK 含 补全/补齐），先补全后运行的合法未来计划被误拒；HEAD 已存在",
)

D1C_ANALYSIS = EvidenceAnalysis(
    summary="本次为缓存要求整理缺口与补全计划。",
    items=[AIRequirementAnalysis(
        requirement_id="R1",
        explanation="材料说明过期分支当前缺失，需要先补全再验证。",
        citation_ids=["R1-E1"],
        information_gap="过期分支缺少实现与运行记录",
        suggestion="补充过期分支实现说明后再运行验证",
        task_plan=EvidenceTaskPlan(
            deliverable="FastAPI过期分支补全与运行记录",
            steps=["编写FastAPI过期分支实现代码后运行并记录输出"],
            acceptance_checks=["运行记录与补全代码可对应"],
        ),
        confidence=0.8,
    )],
    model="synthetic-probe",
)
record(
    "D1c", "控制", "同D1但步骤动词改为 编写...实现代码",
    "None", expect_error(lambda: validate_grounded_analysis([GAP_CONTEXT], D1C_ANALYSIS)),
    "编写 在动词表内故放行；与 D1 对比确认缺口仅因 补全 一词",
)

SUPPORTED_CONTEXT = RequirementEvidenceContext(
    requirement_id="R1",
    requirement_title="实现缓存读写",
    skill="Python",
    verdict="supported",
    rule_score=0.8,
    claimed=True,
    claim_text=None,
    evidence=[EvidenceCandidate(
        citation_id="R1-E1",
        file_path="app/cache.py",
        line_start=1,
        line_end=10,
        evidence_type="python_code",
        strength="high",
        snippet="def cache_get(key):\n    return lookup(key)\n",
        context_complete=True,
        provenance="portfolio",
        function_line_start=1,
        function_line_end=10,
    )],
)
D2_ANALYSIS = EvidenceAnalysis(
    summary="本次分析定位缓存读写函数并说明输入边界。",
    items=[AIRequirementAnalysis(
        requirement_id="R1",
        explanation="已定位缓存读写函数并给出输入边界说明。",
        citation_ids=["R1-E1"],
        information_gap="引用函数体已完整；仍不清楚相邻工具函数体是否包含参数校验",
        suggestion="补充相邻工具函数的定位与说明。",
        confidence=0.8,
    )],
    model="synthetic-probe",
)
record(
    "D2", "contracts既有守卫（相邻函数体误判）",
    "validate_grounded_analysis(supported上下文, information_gap 提到未引用的相邻工具函数体)",
    "None（完整上下文只覆盖被引用函数；相邻未引用函数的不确定陈述合法）",
    expect_error(lambda: validate_grounded_analysis([SUPPORTED_CONTEXT], D2_ANALYSIS)),
    "函数体是否 模式不区分是否指被引用函数；指向其他函数的合法缺口被误拒；HEAD 已存在",
)

# ---------------------------------------------------------------- summary
counter = [row for row in ROWS if not row[2]]
print("=" * 72)
print(f"探针总数: {len(ROWS)}  匹配: {len(ROWS) - len(counter)}  反例/待讨论记录: {len(counter)}")
for pid, category, _, _, expected, actual, _ in counter:
    print(f"  - {pid} [{category}] 预期={expected} 实际={actual}")
sys.exit(0 if not any(not row[2] and row[4] != "待讨论" for row in ROWS) else 1)
