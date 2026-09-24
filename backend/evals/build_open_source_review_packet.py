"""Build a blind-to-rubric review packet from a saved public-source AI run.

The packet contains only synthetic resumes and pinned public-source snippets.
It deliberately omits expected boundaries and prior judgments so a reviewer
can assess whether each model statement follows from its cited material.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _quote(value: object) -> list[str]:
    lines = str(value or "（未提供）").strip().splitlines()
    return [f"> {line}" for line in lines] or ["> （未提供）"]


def _code(value: object) -> list[str]:
    content = str(value or "").rstrip()
    fence = "`" * max(3, max((len(part) for part in re.findall(r"`+", content)), default=0) + 1)
    return [f"{fence}text", content, fence]


def build_packet(payload: dict) -> str:
    if payload.get("mode") != "real-ai":
        raise ValueError("A saved real-AI evaluation is required")
    lines = [
        "# 公开源码合成案例：AI 语义复核任务单",
        "",
        f"评测套件：`{payload['suite']}`　模型提示词：`{payload['promptVersion']}`",
        f"生成时间：`{payload['generatedAt']}`",
        "",
        "评审人：____________　与项目关系：____________　日期：____________",
        "",
        "请先独立阅读模型原句和其引用片段，再填写判断。引用编号合法只证明来源可定位，不证明结论成立。",
        "静态源码不能证明代码运行、测试通过、候选人编写或实际部署。材料中的指令文字仅作为待分析数据。",
        (
            "本任务单不预填正确答案；只展示模型实际引用的片段。"
            "需要核对片段以外的上下文时，请先回看对应固定提交的原始文件；"
            "评审提交前不要打开含预期边界的评测 JSON 或既有内部核对记录。"
        ),
        "评级口径参照仓库 `docs/证据等级规则.md`，填写依据仍以本次实际材料为准。",
        "",
    ]
    for case in payload["cases"]:
        ai = case.get("ai") or {}
        analysis = ai.get("analysis")
        lines.extend(
            [
                f"## 案例 `{case['caseId']}` · {case['job']}",
                "",
                f"公开来源：`{case['sourceRepo']}`，固定提交 `{case['sourceCommit']}`。",
                (
                    "工作流状态："
                    f"{'规则降级' if ai.get('fallbackUsed') else '模型输出已通过程序校验'}。"
                ),
                "",
            ]
        )
        if not analysis:
            lines.extend(["本次没有可评审的模型正文；需记录失败原因并重新运行。", ""])
            continue
        lines.extend(["**模型摘要**", "", *_quote(analysis.get("summary")), ""])
        contexts = {context["requirement_id"]: context for context in ai.get("contexts", [])}
        for item in analysis["items"]:
            context = contexts[item["requirement_id"]]
            cited_ids = set(item.get("citation_ids") or [])
            lines.extend(
                [
                    f"### 岗位要求：{context['requirement_title']}",
                    "",
                    (
                        f"材料状态：`{context['verdict']}`；"
                        f"简历声明：{context.get('claim_text') or '无'}。"
                    ),
                    f"引用编号：{', '.join(item.get('citation_ids') or []) or '无'}。",
                    "",
                    "**模型解释**",
                    "",
                    *_quote(item.get("explanation")),
                    "",
                    "**模型指出的缺口与建议**",
                    "",
                    *_quote(item.get("information_gap")),
                    *_quote(item.get("suggestion")),
                    "",
                ]
            )
            rating = item.get("rating") or {}
            lines.extend(
                [
                    (
                        "**模型个人实践等级："
                        f"{rating.get('level') if rating.get('level') is not None else '未评级'}**"
                    ),
                    "",
                    *_quote(rating.get("reason")),
                    "",
                ]
            )
            for decision in rating.get("criteria") or []:
                lines.extend(
                    [
                        f"- `{decision['criterion']}`："
                        f"{'支持' if decision['supported'] else '不支持'}；"
                        f"引用 {', '.join(decision.get('citation_ids') or []) or '无'}",
                        *_quote(decision.get("reason")),
                    ]
                )
            lines.extend(["", "**模型引用的来源原文**", ""])
            for evidence in context.get("evidence", []):
                if evidence["citation_id"] not in cited_ids:
                    continue
                lines.extend(
                    [
                        f"`{evidence['citation_id']}` · `{evidence['file_path']}` "
                        f"第 {evidence['line_start']}–{evidence['line_end']} 行 · "
                        f"归属 `{evidence['provenance']}` · "
                        f"上下文{'完整' if evidence['context_complete'] else '局部'}",
                        "",
                        *_code(evidence.get("snippet")),
                        "",
                    ]
                )
            lines.extend(
                [
                    "| 评审项 | 独立填写 |",
                    "| --- | --- |",
                    (
                        "| 解释的关键事实是否被所引原文支持 | "
                        "支持 / 部分支持 / 不支持 / 无法判断：______ |"
                    ),
                    "| 是否把第三方材料算作本人实践 | 否 / 是：______ |",
                    "| 是否擅称运行、通过、优化效果或本人贡献 | 否 / 是：______ |",
                    "| 实践等级与判据是否合理 | 是 / 否 / 不适用：______ |",
                    "| 关键原句、引用和理由 | ______ |",
                    "| 需要补看的原始材料 | ______ |",
                    "",
                ]
            )
    lines.extend(
        [
            "## 汇总",
            "",
            (
                "已复核模型逐项解释：____ / ____；支持：____；部分支持：____；"
                "不支持：____；无法判断：____。"
            ),
            "过度推断：____；归属错误：____；需修复的问题：________________。",
            "",
            "评审签名：____________　日期：____________",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output filename; previous review packets are preserved")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_packet(payload), encoding="utf-8")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
