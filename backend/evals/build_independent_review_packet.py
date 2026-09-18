from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "backend" / "evals"
OUTPUT = ROOT / "docs" / "独立人工语义复核任务单-20260918.md"


def load_json(name: str) -> dict[str, Any]:
    return json.loads((EVAL_DIR / name).read_text(encoding="utf-8"))


def quote(value: object) -> str:
    text = str(value or "未提供").strip()
    return "\n".join(f"> {line}" for line in text.splitlines())


def code_block(value: object) -> str:
    text = str(value or "").rstrip()
    return f"```text\n{text}\n```"


def append_evidence(lines: list[str], evidence: list[dict[str, Any]]) -> None:
    if not evidence:
        lines.append("本场景没有白名单项目证据。")
        return

    for item in evidence:
        lines.extend(
            [
                f"**{item['citation_id']} · `{item['file_path']}` 第 "
                f"{item['line_start']}–{item['line_end']} 行 · "
                f"上下文{'完整' if item.get('context_complete') else '局部'}**",
                "",
                code_block(item.get("snippet")),
                "",
            ]
        )


def append_review_fields(lines: list[str], include_rating: bool = True) -> None:
    rows = [
        "| 人工判断 | 填写 |",
        "| --- | --- |",
        "| 结论支持度 | 支持 / 部分支持 / 不支持 / 无法判断：______ |",
        "| 是否存在过度推断 | 否 / 是：______ |",
    ]
    if include_rating:
        rows.append("| 评级是否符合统一判据 | 是 / 否 / 不适用：______ |")
    rows.extend(
        [
            "| 关键原句、对应引用与理由 | ______ |",
            "| 需补证据或修改 | ______ |",
        ]
    )
    lines.extend(rows)


def append_model_case(
    lines: list[str],
    index: int,
    result: dict[str, Any],
    analysis: dict[str, Any],
) -> None:
    context = result["contexts"][0]
    item = analysis["items"][0]
    rating = item["rating"]
    evidence = [entry for ctx in result["contexts"] for entry in ctx.get("evidence", [])]

    lines.extend(
        [
            f"### {index}. `{result['id']}`",
            "",
            f"- 岗位要求：{context['requirement_title']}",
            f"- 独立评审关注点：{result['rubric']}",
            "- 程序状态：模型有正文；确定性单括号修复后通过结构与引用校验。",
            "",
            "**模型摘要**",
            "",
            quote(analysis.get("summary")),
            "",
            "**模型逐项解释**",
            "",
            quote(item.get("explanation")),
            "",
            f"**模型评级：{rating.get('level')}/5**",
            "",
            quote(rating.get("reason")),
            "",
            "**模型声明的缺口**",
            "",
            quote(item.get("information_gap")),
            "",
            "**白名单证据原文**",
            "",
        ]
    )
    append_evidence(lines, evidence)
    append_review_fields(lines)
    lines.append("")


def append_rule_case(lines: list[str], index: int, result: dict[str, Any]) -> None:
    context = result["contexts"][0]
    lines.extend(
        [
            f"### {index}. `{result['id']}`",
            "",
            f"- 岗位要求：{context['requirement_title']}",
            f"- 独立评审关注点：{result['rubric']}",
            f"- 生产行为：未调用外部模型；原因 `{result.get('skippedReason')}`。",
            "",
            "**规则输出**",
            "",
            quote(result.get("ruleSummary")),
            "",
            "| 人工判断 | 填写 |",
            "| --- | --- |",
            "| 跳过模型是否合理 | 是 / 否：______ |",
            "| 规则措辞是否把缺证据写成缺能力 | 否 / 是：______ |",
            "| 理由与建议 | ______ |",
            "",
        ]
    )


def append_sql_regression(lines: list[str], payload: dict[str, Any]) -> None:
    result = payload["results"][0]
    append_model_case(lines, 12, result, result["analysis"])


def append_tool_regression(lines: list[str], payload: dict[str, Any]) -> None:
    item = payload["items"][0]
    evidence = [
        {
            "citation_id": e["citationId"],
            "file_path": e["filePath"],
            "line_start": e["lineStart"],
            "line_end": e["lineEnd"],
            "context_complete": e["contextComplete"],
            "snippet": e["snippet"],
        }
        for e in item["evidenceList"]
    ]
    tool = payload["toolCalls"][0]
    lines.extend(
        [
            "### 13. `controlled-function-calling-report`",
            "",
            f"- 岗位要求：{item['requirementTitle']}",
            f"- 工具调用：`{tool['tool']}`，范围 `{tool['scope']}`，新增 `{tool['citationId']}`。",
            f"- 模型评级：{item['evidenceLevel']}/5（{item['evidenceLevelLabel']}）。",
            (
                "- 独立评审关注点：补检索是否真正补到支持三项判据的原文；"
                "是否把静态代码扩大为运行成功或本人贡献。"
            ),
            "",
            "**模型解释**",
            "",
            quote(item.get("aiExplanation")),
            "",
            "**模型评级理由**",
            "",
            quote(item.get("evidenceLevelReason")),
            "",
            "**模型声明的缺口**",
            "",
            quote(item.get("aiInformationGap")),
            "",
            "**工具调用后报告采用的证据**",
            "",
        ]
    )
    append_evidence(lines, evidence)
    append_review_fields(lines)
    lines.append("")


def main() -> None:
    run = load_json("trust-deepseek-v6-20260918-run1.json")
    revalidated = load_json("trust-deepseek-v6-20260918-revalidated-v7.json")
    sql = load_json("trust-deepseek-v9-sql-20260918-run2.json")
    tool = load_json("deepseek-tool-report-20260918-152713.json")

    repaired = {item["id"]: item for item in revalidated["results"]}
    lines = [
        "# 独立人工语义复核任务单",
        "",
        "生成日期：2026-09-18。状态：**待项目成员以外的真实评审者填写**。本任务单只整理已有合成样本、模型原文和白名单证据，不预填人工结论。",
        "",
        "评审人：____________　单位/关系：____________　日期：____________",
        "",
        (
            "独立性声明：评审前未查看 "
            "`trust-deepseek-v6-assistant-review-20260918.json`，"
            "并按自己的判断核对模型原句与证据原文。签名：____________"
        ),
        "",
        "## 评审规则",
        "",
        "1. 先把模型输出拆成可检验陈述，再逐条对照引用原文；引用编号合法不等于内容支持结论。",
        "2. 静态代码只能证明材料中存在相应实现，不能证明已运行、测试通过、本人贡献或能力认证。",
        (
            "3. `支持` 表示所有关键陈述均有证据；`部分支持` 表示主要方向正确但含"
            "无依据扩大；`不支持` 表示关键结论与证据不符。"
        ),
        "4. 发现把空实现、依赖声明、自述或提示注入当成完成能力时，标记过度推断并写出原句。",
        "5. 前 11 项核验固定难例；第 12、13 项核验当前 PostgreSQL 口径和受控补检索生产结果。",
        "",
        "原始文件：",
        "",
        "- `backend/evals/evidence-trust-cases.json`",
        "- `backend/evals/trust-deepseek-v6-20260918-run1.json`",
        "- `backend/evals/trust-deepseek-v6-20260918-revalidated-v7.json`",
        "- `backend/evals/trust-deepseek-v9-sql-20260918-run2.json`",
        "- `backend/evals/deepseek-tool-report-20260918-152713.json`",
        "",
        "## 固定难例",
        "",
    ]

    for index, result in enumerate(run["results"], start=1):
        if result.get("externalAttempted"):
            append_model_case(lines, index, result, repaired[result["id"]]["analysis"])
        else:
            append_rule_case(lines, index, result)

    lines.extend(["## 当前口径定向回归", ""])
    append_sql_regression(lines, sql)
    append_tool_regression(lines, tool)
    lines.extend(
        [
            "## 汇总与签署",
            "",
            "| 指标 | 人工填写 |",
            "| --- | --- |",
            "| 已完成语义复核的模型输出 | ____ / 10 |",
            "| 规则跳过场景已复核 | ____ / 3 |",
            "| 支持 / 部分支持 / 不支持 / 无法判断 | ____ / ____ / ____ / ____ |",
            "| 人工过度推断数 / 已判断模型输出数 | ____ / ____ |",
            "| 评级口径不合理数 | ____ |",
            "| 是否允许进入正式录制 | 是 / 否 |",
            "",
            "阻断问题与修复要求：",
            "",
            "________________________________________________________________________",
            "",
            "评审结论：________________________________________________________________",
            "",
            "评审人签名：____________　日期：____________",
            "",
            (
                "通过门槛：10 个模型输出全部完成语义判断；3 个规则跳过场景均确认"
                "措辞合理；空实现、运行结果、本人贡献、提示注入等关键边界没有未处理"
                "的过度推断。任何阻断项修复后必须生成新结果复评，不覆盖原始文件。"
            ),
            "",
        ]
    )
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
