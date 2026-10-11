"""传智杯30 纯离线探针：8例盲评草稿 × 真实生产匹配/上下文/契约。

不调用 provider、不联网、不触数据库；仅调用 app.tools.matcher.match_candidate、
app.agents.evidence_workflow.build_evidence_contexts、app.agents.contracts.validate_grounded_analysis
及各守卫函数。输出 JSON 到 stdout。
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.agents.contracts import (  # noqa: E402
    EvidenceAnalysis,
    EvidenceTaskPlan,
    AIRequirementAnalysis,
    ModelUsage,
    execution_plan_skips_explicitly_missing_implementation,
    overclaim_flags,
    runtime_plan_without_implementation_step,
    validate_grounded_analysis,
)
from app.agents.evidence_workflow import build_evidence_contexts  # noqa: E402
from app.tools.code_analyzer import ProjectFileSnapshot  # noqa: E402
from app.tools.evidence_levels import CANDIDATE_TYPES, _rule_classification  # noqa: E402
from app.tools.function_coverage import redundant_source_request  # noqa: E402
from app.tools.matcher import RequirementInput, SkillClaim, match_candidate  # noqa: E402
from app.tools.resume_parser import SkillClaim as _SkillClaim  # noqa: E402,F401  (形状确认)
from app.tools.task_boundaries import (  # noqa: E402
    task_boundary_error,
    unsupported_attribution,
)

INPUT = BACKEND.parent / "backend" / "evals" / "quality-blind-plan-review-input.json"
REVIEW = (
    BACKEND.parent
    / "docs"
    / "evidence"
    / "20261010-AI-blind-plan-review"
    / "review.json"
)

# 与各案例一一对应的固定中性外圈文本（唯一变量是草稿计划本身）。
EXPLANATION = "当前材料片段与要求相关；运行结果与本人贡献尚未展示，需人工核验。"
GAP = "运行结果与本人贡献未在材料中展示。"
SUGGESTION = "补充可定位的实现或运行记录，并人工核对内容。"
SUMMARY = "共1项要求；按当前材料给出补证建议，运行结果与本人贡献仍需人工核验。"


def load_cases():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    scores = review["summaryForCodex"]["scoreTable"]
    return data, scores


def build_match(case):
    req_id = uuid.uuid5(uuid.NAMESPACE_URL, f"plan-audit-30/{case['id']}")
    requirement = RequirementInput(
        id=req_id,
        title=case["requirement"]["title"],
        skill=case["requirement"]["skill"],
        weight=case["requirement"]["weight"],
    )
    claims = [SkillClaim(skill=case["requirement"]["skill"], claim_text=case["resume"])]
    files = [
        ProjectFileSnapshot(path=f["path"], content=f["content"])
        for f in case["personalFiles"]
    ]
    reference_files = [
        ProjectFileSnapshot(path=f["path"], content=f["content"])
        for f in case.get("referenceFiles", [])
    ]
    return match_candidate([requirement], claims, files, reference_files=reference_files)


def evidence_view(item):
    rows = []
    for e in item.evidence_list:
        rows.append(
            {
                "evidence_type": e.evidence_type,
                "file_path": e.file_path,
                "line_start": e.line_start,
                "line_end": e.line_end,
                "strength": e.strength,
                "provenance": e.provenance,
                "context_complete": e.context_complete,
                "function_line_start": e.function_line_start,
                "function_line_end": e.function_line_end,
                "source_line_count": e.source_line_count,
                "snippet": e.snippet,
            }
        )
    return rows


def rating_for_context(context):
    """按真实上限构造结构性一致的 rating（rating 维度本身非本审计对象）。"""
    portfolio_direct = [
        e.model_dump()
        for e in context.evidence
        if e.provenance == "portfolio" and e.evidence_type not in CANDIDATE_TYPES
    ]
    reasons = {
        "relevance": "片段与要求存在直接相关内容",
        "operation": "存在非空实现或直接操作片段",
        "task": "完整任务链与运行结果未在材料中展示",
    }
    if portfolio_direct:
        cap = _rule_classification(
            {"skill": context.skill, "evidenceList": portfolio_direct},
            context.verdict,
            include_candidates=True,
        )["evidence_level"]
        flags = [cap is not None and cap >= 1, cap is not None and cap >= 2, False]
        cite = portfolio_direct and [
            e.citation_id
            for e in context.evidence
            if e.evidence_type not in CANDIDATE_TYPES and e.provenance == "portfolio"
        ]
        criteria = [
            {
                "criterion": name,
                "supported": flag,
                "citation_ids": cite if flag else [],
                "reason": reasons[name] if flag else reasons[name],
            }
            for name, flag in zip(("relevance", "operation", "task"), flags)
        ]
        level = sum(flags) or None
        reason = "按判据逐项核对；引用片段支持已成立项，其余仍需人工核验。"
    else:
        criteria = [
            {
                "criterion": name,
                "supported": False,
                "citation_ids": [],
                "reason": reasons[name],
            }
            for name in ("relevance", "operation", "task")
        ]
        level = None
        reason = "当前材料未找到可支撑判据的证据；需人工核验。"
    return {"level": level, "reason": reason, "criteria": criteria}


def build_analysis(context, draft):
    citation_ids = []
    if context.evidence and context.verdict in {"supported", "partial"}:
        citation_ids = [
            e.citation_id for e in context.evidence if e.provenance == "portfolio"
        ]
    plan = EvidenceTaskPlan(
        deliverable=draft["deliverable"],
        steps=draft["steps"],
        acceptance_checks=draft["acceptanceChecks"],
    )
    item = AIRequirementAnalysis(
        requirement_id=context.requirement_id,
        explanation=EXPLANATION,
        citation_ids=citation_ids,
        information_gap=GAP,
        suggestion=SUGGESTION,
        task_plan=plan,
        confidence=0.5,
        rating=rating_for_context(context),
    )
    analysis = EvidenceAnalysis(
        summary=SUMMARY,
        items=[item],
        model="offline-probe",
        usage=ModelUsage(),
    )
    return analysis


def guard_breakdown(context, plan):
    plan_texts = [plan.deliverable, *plan.steps, *plan.acceptance_checks]
    personal_texts = [
        e.snippet for e in context.evidence if e.provenance == "portfolio"
    ]
    return {
        "task_boundary_error": task_boundary_error(
            deliverable=plan.deliverable,
            steps=plan.steps,
            acceptance_checks=plan.acceptance_checks,
            personal_source_texts=personal_texts,
        ),
        "unsupported_attribution_per_text": {
            text: unsupported_attribution(text) for text in plan_texts
        },
        "overclaim_flags_narrative": overclaim_flags(
            " ".join([EXPLANATION, GAP, SUGGESTION])
        ),
        "overclaim_flags_plan_planned_execution": {
            text: overclaim_flags(text, planned_execution=True) for text in plan_texts
        },
        "redundant_source_request": {
            text: redundant_source_request(text, context.evidence)
            for text in [SUGGESTION, *plan_texts]
        },
        "runtime_plan_without_implementation_step": (
            runtime_plan_without_implementation_step(plan.deliverable, plan.steps)
        ),
        "execution_plan_skips_explicitly_missing_implementation": (
            execution_plan_skips_explicitly_missing_implementation(context, plan)
        ),
    }


def run_case(case, score):
    result = build_match(case)
    item = result.items[0]
    contexts = build_evidence_contexts(result)
    context = contexts[0]
    record = {
        "caseId": case["id"],
        "blindReviewScores": score,
        "match": {
            "verdict": item.verdict,
            "rule_score": item.rule_base_score,
            "claimed": item.claimed,
            "explanation": item.explanation,
            "evidence": evidence_view(item),
        },
        "context": {
            "requirement_id": context.requirement_id,
            "verdict": context.verdict,
            "evidence_count": len(context.evidence),
            "evidence_types": [e.evidence_type for e in context.evidence],
            "rating_ceiling": context.rating_ceiling,
        },
    }
    try:
        analysis = build_analysis(context, case["draft"])
        validate_grounded_analysis(contexts, analysis)
        record["validate"] = {"accepted": True, "error": None}
    except Exception as exc:  # noqa: BLE001
        record["validate"] = {"accepted": False, "error": f"{type(exc).__name__}: {exc}"}
    record["guards"] = guard_breakdown(context, case_to_plan(case["draft"]))
    record["variants"] = run_variants(case, context)
    return record


def case_to_plan(draft):
    return EvidenceTaskPlan(
        deliverable=draft["deliverable"],
        steps=draft["steps"],
        acceptance_checks=draft["acceptanceChecks"],
    )


def try_plan(case, context, plan):
    """对同一真实 context 换一个 plan 跑完整 validator（外圈文本不变）。"""
    citation_ids = []
    if context.evidence and context.verdict in {"supported", "partial"}:
        citation_ids = [
            e.citation_id for e in context.evidence if e.provenance == "portfolio"
        ]
    item = AIRequirementAnalysis(
        requirement_id=context.requirement_id,
        explanation=EXPLANATION,
        citation_ids=citation_ids,
        information_gap=GAP,
        suggestion=SUGGESTION,
        task_plan=plan,
        confidence=0.5,
        rating=rating_for_context(context),
    )
    analysis = EvidenceAnalysis(
        summary=SUMMARY, items=[item], model="offline-probe", usage=ModelUsage()
    )
    try:
        validate_grounded_analysis([context], analysis)
        return {"accepted": True, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"accepted": False, "error": f"{type(exc).__name__}: {exc}"}


def run_variants(case, context):
    cid = case["id"]
    variants = {}
    if cid == "45c8ae3412":
        variants["v1_只去掉补充写路径步骤"] = try_plan(
            case,
            context,
            EvidenceTaskPlan(
                deliverable=case["draft"]["deliverable"],
                steps=["梳理 cache_get 已覆盖的读路径", "直接运行并验证命中与失效"],
                acceptance_checks=case["draft"]["acceptanceChecks"],
            ),
        )
    elif cid == "b294018f1c":
        variants["v1_控制组_满足岗位要求"] = try_plan(
            case,
            context,
            EvidenceTaskPlan(
                deliverable="进一步完善岗位材料",
                steps=["按要求补充相关资料", "材料满足岗位要求"],
                acceptance_checks=case["draft"]["acceptanceChecks"],
            ),
        )
    elif cid == "09fb4e82f3":
        variants["v1_控制组_小组报告作为本人贡献"] = try_plan(
            case,
            context,
            EvidenceTaskPlan(
                deliverable=case["draft"]["deliverable"],
                steps=["将小组项目报告作为本人贡献证明", *case["draft"]["steps"][1:]],
                acceptance_checks=case["draft"]["acceptanceChecks"],
            ),
        )
    elif cid == "e2fd108ad9":
        variants["v1_去掉已通过措辞保留已部署主张"] = try_plan(
            case,
            context,
            EvidenceTaskPlan(
                deliverable=case["draft"]["deliverable"],
                steps=["整理 metrics.py 源码文件"],
                acceptance_checks=case["draft"]["acceptanceChecks"],
            ),
        )
    elif cid == "853352704e":
        variants["v1_只运行不编写"] = try_plan(
            case,
            context,
            EvidenceTaskPlan(
                deliverable=case["draft"]["deliverable"],
                steps=["本地运行并保存读写请求与响应样例"],
                acceptance_checks=case["draft"]["acceptanceChecks"],
            ),
        )
    return variants


def main():
    data, scores = load_cases()
    results = []
    for case in data["cases"]:
        results.append(run_case(case, scores.get(case["id"])))
    print(
        json.dumps(
            {
                "inputSha256": "a7418dbd53ed5b8b333fcb979902b720c480ee21a66a384cf4acd78fd250ac5e",
                "kind": data["kind"],
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
