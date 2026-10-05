"""Narrow source/plan consistency guards, not general semantic verification."""

from __future__ import annotations

import re

_ATTRIBUTION = re.compile(
    r"(?:参考(?:材料|代码|仓库|实现|样例|SQL)|"
    r"第三方(?:材料|代码|作品|成果|实现|SQL)|"
    r"(?:他人|同学)(?:完成|整理|编写|提供)的.{0,20}?|"
    r"(?:小组|团队)(?:项目)?(?:报告|成果|产物|作品|仓库)).{0,45}?"
    r"(?P<verb>作为|当作|视为|算作|证明|证实|等同|归为|计入).{0,25}?"
    r"(?:本人|个人).{0,25}?(?:实践|能力|贡献|负责|成果)"
)
_UNCERTAIN = re.compile(r"不能|无法|不代表|不等于|不得|不可|不足以|未能|尚不能|是否|能否")
_FULL_SCOPE = re.compile(r"完整.{0,35}(?:功能|链路)")
_SCOPE_CHECK = re.compile(
    r"核对|检查|梳理|标注|列出|补充|补齐|补全|编写|实现|修复|区分|确认.{0,15}(?:范围|覆盖|分支)"
)
_IMPLEMENTATION = re.compile(
    r"^\s*(?:[-*]\s*)?"
    r"(?P<subject>[\w\u4e00-\u9fff][\w\u4e00-\u9fff .:/-]{0,35}?)"
    r"(?P<state>尚未|还未|未|已经|已)实现"
)


def unsupported_attribution(text: str) -> bool:
    sentences = re.split(r"[。！？；\n]", text)
    for index, sentence in enumerate(sentences):
        for match in _ATTRIBUTION.finditer(sentence):
            before_verb = sentence[:match.start("verb")]
            clause_start = max(before_verb.rfind("，"), before_verb.rfind(",")) + 1
            prefix = sentence[clause_start:match.start("verb")]
            if _UNCERTAIN.search(prefix):
                continue
            # A named person's own commit is individual evidence even when
            # it lives in a group repository; a bare group report is not.
            basis = sentence[match.start():match.start("verb")]
            if re.search(r"本人具名(?:的)?(?:提交记录|代码提交|提交日志)", basis):
                continue
            # Reported claims need an explicit refusal/uncertainty, not merely
            # the word 'claim', to avoid endorsing the substitution indirectly.
            refusal = sentence[match.end():]
            if index + 1 < len(sentences) and re.match(
                r"\s*(?:此|该)(?:声明|说法|自述)", sentences[index + 1]
            ):
                refusal += " " + sentences[index + 1]
            if re.search(r"声称|声明|自述", sentence[:match.start("verb")]) and re.search(
                r"不予采纳|不作为事实|不采纳|待核验|待核实|未核验", refusal
            ):
                continue
            return True
    return False


def conflicting_implementation_sources(source_texts: list[str]) -> bool:
    states: dict[str, set[bool]] = {}
    for text in source_texts:
        for line in text.splitlines():
            # Conditional questions are not current implementation assertions.
            if re.search(r"如果|假设|是否|若已|若未", line):
                continue
            if re.search(r"旧记录|旧版|历史记录|此前|曾经", line):
                continue
            if re.search(r"未实现的部分已.{0,15}(?:补全|补齐|完成|实现)", line):
                continue
            match = _IMPLEMENTATION.match(line)
            if not match:
                continue
            subject = re.sub(r"\s+", "", match["subject"])
            states.setdefault(subject, set()).add(match["state"] in {"已", "已经"})
    return any(len(values) > 1 for values in states.values())


def task_boundary_error(
    *, deliverable: str, steps: list[str], acceptance_checks: list[str],
    personal_source_texts: list[str],
) -> str | None:
    texts = [deliverable, *steps, *acceptance_checks]
    if any(unsupported_attribution(text) for text in texts):
        return "AI task plan substitutes group or reference material for personal evidence"
    # A complete-scope acceptance plan must first establish implementation
    # scope or propose its completion. Full logs alone do not trigger this.
    if any(_FULL_SCOPE.search(text) for text in texts) and not any(
        _SCOPE_CHECK.search(step) for step in steps
    ):
        return "AI task plan assumes complete functionality without a scope check"
    if conflicting_implementation_sources(personal_source_texts):
        work = " ".join(texts)
        if any(
            re.search(r"(?:按|采信|选择).{0,12}已实现(?:一侧|来源).{0,12}(?:归档|结论|认定)", text)
            and not re.search(r"不得|不能|不可|不应|避免", text)
            for text in texts
        ):
            return "AI task plan silently selects one side of unresolved source conflict"
        if not (
            re.search(r"冲突|矛盾|不一致|相反", work)
            and re.search(r"待核验|待核实|待确认|核对版本|核实来源|暂不采信", work)
            and re.search(r"并列|分别|两处|两份|逐一|双方", work)
        ):
            return "AI task plan omits unresolved implementation-source conflict"
    return None
