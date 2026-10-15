"""Versioned interpretation of saved evidence, independent of numeric scores."""

import ast
import re
import textwrap

LEGACY_VERSION = "practice-evidence-v4-candidate-boundary"
VERSION = "practice-evidence-v5-redis-operation"
CANDIDATE_TYPES = {"semantic_document_candidate", "retrieved_context"}


def is_empty_implementation(evidence: dict) -> bool:
    """Recognize explicit stubs without executing uploaded source code."""
    evidence_type = evidence.get("evidenceType", evidence.get("evidence_type", ""))
    snippet = evidence.get("snippet")
    if not snippet or evidence_type not in {
        "python_code",
        "fastapi_route",
        "pytest_test",
        "react_component",
        "typescript_code",
    }:
        return False
    if evidence_type in {"python_code", "fastapi_route", "pytest_test"}:
        try:
            tree = ast.parse(textwrap.dedent(snippet))
        except (SyntaxError, ValueError):
            return bool(re.search(r"\bpass\s*(?:#.*)?$", snippet.strip()))
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        ]
        if not functions:
            return False

        def empty_body(node) -> bool:
            meaningful = [
                statement
                for statement in node.body
                if not (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                )
            ]
            return bool(meaningful) and all(
                isinstance(statement, ast.Pass)
                or (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and statement.value.value is Ellipsis
                )
                or (
                    isinstance(statement, ast.Raise)
                    and isinstance(statement.exc, ast.Call)
                    and isinstance(statement.exc.func, ast.Name)
                    and statement.exc.func.id == "NotImplementedError"
                )
                for statement in meaningful
            )

        return all(empty_body(node) for node in functions)
    compact = re.sub(r"\s+", " ", snippet)
    return bool(re.search(r"(?:=>|function\b[^{}]*|\([^)]*\))\s*\{\s*\}", compact))


def _rule_classification(
    snapshot: dict, verdict: str, review_status: str | None = None,
    *, include_candidates: bool = False, version: str = VERSION,
) -> dict:
    selected_version = VERSION if version == VERSION else LEGACY_VERSION

    def result(level, label, reason, gap):
        return dict(
            evidence_level=level,
            evidence_level_label=label,
            evidence_level_reason=reason,
            evidence_level_gap=gap,
            evidence_level_version=selected_version,
        )

    if verdict == "unsupported":
        return result(None, "暂不支持评估", "当前规则不覆盖该要求。", "需人工审阅对应材料。")
    if review_status in {"rejected", "corrected"}:
        return result(
            None,
            "待重新核验",
            "证据已被驳回或标记修正，暂停展示自动等级。",
            "需核对修正内容或重新分析材料；不自动沿用原等级。",
        )
    all_evidence = snapshot.get("evidenceList") or (
        [snapshot["evidence"]] if snapshot.get("evidence") else []
    )
    evidence = [
        item for item in all_evidence if item.get("provenance", "portfolio") != "reference"
    ]
    if not include_candidates:
        direct_evidence = [
            item for item in evidence
            if item.get("evidenceType", item.get("evidence_type")) not in CANDIDATE_TYPES
        ]
        if evidence and not direct_evidence:
            return result(
                None, "待核对检索候选",
                "仅有检索候选，尚未确认与该要求相关，不据此展示实践等级。",
                "核对候选与要求的对应关系，补充直接相关的材料或经校验的 AI 引用解释。",
            )
        evidence = direct_evidence
    if not evidence:
        if all_evidence:
            return result(
                None,
                "仅有第三方参考",
                "第三方源码可作学习参考，不能证明本人实践或提高个人评级。",
                "提交本人实现、可复现验证结果和贡献记录。",
            )
        if snapshot.get("claimed"):
            return result(
                None,
                "仅有声明，未评级",
                "简历自述不作为实践等级依据。",
                "补充可定位的作品或实现材料。",
            )
        return result(
            None,
            "未找到证据",
            "本次材料未提供支持证据，不代表没有能力。",
            "补充与要求直接相关的材料。",
        )
    skill = snapshot.get("skill", "")
    empty_evidence = [item for item in evidence if is_empty_implementation(item)]
    usable_evidence = [item for item in evidence if not is_empty_implementation(item)]
    implementation_types = {
        "python_code",
        "fastapi_route",
        "pytest_test",
        "sql_query",
        "sql_schema",
        "react_component",
        "typescript_code",
    }
    direct = any(
        e.get("evidenceType", e.get("evidence_type")) in implementation_types
        and e.get("contextComplete", e.get("context_complete", False))
        for e in usable_evidence
    )
    if direct and skill in {"索引优化", "备份恢复"}:
        return result(
            2,
            "局部操作",
            "发现相关定义或命令，但不足以核实完整优化或恢复过程。",
            "索引需执行计划与前后对比；备份恢复需完整恢复步骤和一致性验证记录。",
        )
    if direct:
        return result(
            3,
            "任务实现",
            "引用包含规则识别出的实现及完整上下文；未使用旧分数换算。",
            "仍需可核对的运行结果与验证记录，不能确认本人贡献。",
        )
    operation_types = {
        "python_code",
        "fastapi_route",
        "pytest_test",
        "sql_query",
        "sql_schema",
        "react_component",
        "typescript_code",
        "shell_command",
        "shell_script",
        "sql_grant",
        "db_monitor_query",
        "backup_command",
        "restore_command",
        "index_definition",
        "alert_rule",
        "postgres_usage",
    }
    if selected_version == VERSION:
        operation_types.add("redis_usage")
    if any(
        e.get("evidenceType", e.get("evidence_type")) in operation_types for e in usable_evidence
    ):
        return result(
            2,
            "局部操作",
            "存在直接操作或实现片段，但完整任务链与上下文尚不充分。",
            "补充输入、操作、输出和异常处理，以及可定位的验证材料。",
        )
    if empty_evidence:
        return result(
            1,
            "基础线索",
            "发现与要求相关的函数或组件，但实现为空壳，不能作为实际操作证据。",
            "补充非空实现、输入输出处理及可定位的验证材料。",
        )
    return result(
        1,
        "基础线索",
        "存在相关依赖、配置或结构化说明，尚未形成直接操作证据。",
        "补充与该要求直接相关的操作或实现，证书名称与自述不能替代项目证据。",
    )


def classify_evidence(snapshot: dict, verdict: str, review_status: str | None = None) -> dict:
    """Only validated, persisted AI assessments can replace the rule fallback."""
    from app.agents.contracts import AIRating
    from app.tools.skill_rubric import rubric_for

    # New reports save their interpretation profile. Missing markers retain the
    # legacy read behavior instead of silently upgrading historical reports.
    version = snapshot.get("ruleClassificationVersion", LEGACY_VERSION)
    result = _rule_classification(snapshot, verdict, review_status, version=version)
    ai = snapshot.get("ai") or {}
    rubric = ai.get("ratingRubric") or rubric_for(snapshot.get("skill", "未分类"))
    result.update(
        evidence_level_source="rules",
        skill_path=rubric.get("path", []),
        rating_criteria=[],
    )
    if review_status in {"rejected", "corrected"}:
        result["evidence_level_source"] = "review_suspended"
        return result
    if ai.get("status") != "validated" or not ai.get("rating"):
        return result
    try:
        rating = AIRating.model_validate(ai["rating"])
    except ValueError:
        return result
    # Recheck the structural ceiling when reading saved reports as defense in depth.
    ceiling = _rule_classification(
        snapshot, verdict, review_status, include_candidates=True, version=version
    )["evidence_level"]
    if rating.level is not None and (ceiling is None or rating.level > ceiling):
        return result
    labels = {1: "基础线索", 2: "局部操作", 3: "任务实现", None: "AI 未确认相关实践证据"}
    result.update(
        evidence_level=rating.level,
        evidence_level_label=labels[rating.level],
        evidence_level_reason=rating.reason,
        evidence_level_gap=ai.get("informationGap") or "仍需核验运行结果和本人贡献。",
        evidence_level_version="practice-evidence-v3-ai",
        evidence_level_source="ai_preliminary",
        rating_criteria=[d.model_dump() for d in rating.criteria],
    )
    return result
