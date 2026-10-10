"""Create a blind human-review worksheet for the latest two-round DeepSeek run."""

from __future__ import annotations

import json
from pathlib import Path

from evals.build_independent_review_packet import append_evidence, append_review_fields, quote

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "backend/evals/deepseek-two-rounds-20260925-151222.json"
OUTPUT = ROOT / "docs/evidence/generated-review/独立人工语义复核补充任务单-20260925.md"


def main() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    if payload.get("fallbackUsed") or not payload.get("citedSourcesExact"):
        raise ValueError("The selected run is not a source-exact AI report")
    contexts = {context["requirement_id"]: context for context in payload["contexts"]}
    analysis = payload["analysis"]
    if not analysis or set(contexts) != {
        item["requirement_id"] for item in analysis["items"]
    }:
        raise ValueError("The selected run does not cover every requirement")
    lines = [
        "# 两轮补检索：独立人工语义复核补充任务单",
        "",
        "生成日期：2026-09-25。状态：**待项目成员以外的真实评审者填写**。",
        "",
        "评审人：____________　单位/关系：____________　日期：____________",
        "",
        "请在评审前不要查看项目的助手初审结论。引用编号与原文件一致只是一项机械校验；"
        "请逐句判断解释是否受片段支持，不能把静态代码当作运行结果、本人贡献或能力认证。",
        "",
        f"原始模型结果：`backend/evals/{SOURCE.name}`。此任务单不预填人工结论。",
        "",
        "## 工作流判断",
        "",
        "第一轮模型请求检索 FastAPI 路由、请求处理与测试实现；工具从当前合成代码索引补回 "
        "`R1-E3`。第二轮模型没有再次请求工具。",
        "",
        "| 人工判断 | 填写 |",
        "| --- | --- |",
        "| 新增 `R1-E3` 是否带来实质新信息 | 是 / 部分 / 否：______ |",
        "| 模型第二轮停止是否合理 | 是 / 否 / 无法判断：______ |",
        "| 如果继续检索，最该寻找什么 | ______ |",
        "| 依据与源文件行号 | ______ |",
        "",
        "## 逐项解释与评级",
        "",
        "**模型摘要**",
        "",
        quote(analysis["summary"]),
        "",
    ]
    for number, item in enumerate(analysis["items"], 1):
        context = contexts[item["requirement_id"]]
        rating = item["rating"]
        lines.extend(
            [
                f"### {number}. {context['skill']}",
                "",
                f"- 岗位要求：{context['requirement_title']}",
                f"- 引用编号：{', '.join(item['citation_ids'])}",
                "",
                "**模型解释**",
                "",
                quote(item["explanation"]),
                "",
                f"**模型初评：{rating['level']}/5**",
                "",
                quote(rating["reason"]),
                "",
                "**模型声明的缺口**",
                "",
                quote(item["information_gap"]),
                "",
                "**模型建议**",
                "",
                quote(item["suggestion"]),
                "",
                "**引用的源文件原文**",
                "",
            ]
        )
        by_id = {evidence["citation_id"]: evidence for evidence in context["evidence"]}
        append_evidence(lines, [by_id[citation_id] for citation_id in item["citation_ids"]])
        append_review_fields(lines)
        lines.append("")
    lines.extend(
        [
            "## 汇总与签署",
            "",
            "| 指标 | 人工填写 |",
            "| --- | --- |",
            "| 已完成逐项语义判断 | ____ / 2 |",
            "| 支持 / 部分支持 / 不支持 / 无法判断 | ____ / ____ / ____ / ____ |",
            "| 过度推断项数 | ____ |",
            "| 工作流停止决定是否可接受 | 是 / 否 / 无法判断 |",
            "| 阻断问题与修复要求 | ______ |",
            "",
            "评审人签名：____________　日期：____________",
            "",
        ]
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
