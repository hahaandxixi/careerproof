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
# The source must explicitly say the shared account makes attribution
# impossible; a bare "共用账号" or a resolvable history does not.
_SHARED_ACCOUNT = re.compile(r"共用(?:账号|帐号|户)")
_ATTRIBUTION_IMPOSSIBLE = re.compile(
    r"未区分作者|未区分提交者|没有区分作者|无法区分.{0,6}(?:作者|提交者|贡献者)"
    r"|不能区分.{0,6}(?:作者|提交者)|无法.{0,6}(?:归属|定位).{0,6}(?:作者|提交者|本人)"
)
# Only "extract author-distinguishable entries from the existing history"
# shapes; obtaining NEW independent proof stays legal (narrow rule, not a
# blanket ban on commits or named proof).
_EXTRACTION_SHAPE = re.compile(
    r"筛出.{0,8}本人署名|具名提交清单|提交记录包含作者.{0,12}可定位为本人"
)
_PLAN_NEGATION = re.compile(r"不能|无法|是否|能否|没有|不再|不存在|改为|避免")


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


# 历史记录 names the record artifact itself, not a past time span, so it
# never exempts a line on its own; past markers lose to a current
# unattributable claim in the same clause (mixed sentences are scoped).
_HISTORICAL_SCOPE = re.compile(r"旧记录|旧版|此前|曾经")
_RESOLVED_SCOPE = re.compile(r"已改用|已换用|现已|不再|已解决")
_CURRENT_SCOPE = re.compile(r"当前|目前|现在")
_PAST_QUALIFIER = re.compile(r"曾|此前|当时|以前")
_CONDITIONAL_SCOPE = re.compile(r"如果|假设|是否|若已|若未")
_CLAUSE_SEP = re.compile(r"[，,；;。！？]")
_ACCOUNT_RESOLUTION = re.compile(r"(?:已改用|已换用).{0,8}(?:个人|独立).{0,4}(?:账号|帐号)")
_AUTHOR_SCOPE = re.compile(r"(?:区分|归属|定位).{0,6}(?:作者|提交者|贡献者|本人)")


def _current_attribution_impossible(line: str) -> bool:
    for match in _ATTRIBUTION_IMPOSSIBLE.finditer(line):
        if _PAST_QUALIFIER.search(line[max(0, match.start() - 4) : match.start()]):
            continue
        return True
    return False


def shared_history_attribution_impossible(source_texts: list[str]) -> bool:
    """True only when a source line explicitly states shared-account history
    makes author attribution impossible now. Conditional, negative and
    resolved statements never trigger. Conditional and current-scope words
    bind to their own clause, so a later independent fact still counts; the
    shared-account fact stays associated with the attribution statement
    across clauses of the surviving scope."""
    for text in source_texts:
        for line in text.splitlines():
            kept = [
                clause
                for clause in _CLAUSE_SEP.split(line)
                if clause and not _CONDITIONAL_SCOPE.search(clause)
                and (
                    _SHARED_ACCOUNT.search(clause)
                    or _ATTRIBUTION_IMPOSSIBLE.search(clause)
                    or _ACCOUNT_RESOLUTION.search(clause)
                    or _AUTHOR_SCOPE.search(clause)
                )
            ]
            if not kept:
                continue
            scope = "，".join(kept)
            if re.search(
                r"(?:没有|未|不再).{0,4}共用(?:账号|帐号|户)"
                r"|(?:可以|能够|可).{0,4}(?:区分|归属|定位)",
                scope,
            ):
                continue
            # A current marker defeats past/resolved markers only inside the
            # clause that itself states the present impossibility.
            current_claim = any(
                _CURRENT_SCOPE.search(clause) and _current_attribution_impossible(clause)
                for clause in kept
            )
            if _RESOLVED_SCOPE.search(scope) and not current_claim:
                continue
            if _HISTORICAL_SCOPE.search(scope) and not current_claim:
                continue
            if _SHARED_ACCOUNT.search(scope) and _current_attribution_impossible(scope):
                return True
    return False


def _shared_account_extraction_error(texts: list[str]) -> str | None:
    for text in texts:
        for sentence in re.split(r"[。！？；;\n]", text):
            for match in _EXTRACTION_SHAPE.finditer(sentence):
                prefix = sentence[max(0, match.start() - 16) : match.start()]
                clause_prefix = _CLAUSE_SEP.split(sentence[:match.start()])[-1]
                # Explicit NEW personal commits are not extracted old history.
                # A separate history-extraction clause/step still fails.
                if (match.group() == "具名提交清单"
                        and re.search(
                            r"(?:今后|以后|下一版本).{0,12}(?:个人|独立)账号.{0,12}新代码",
                            clause_prefix,
                        )
                        and not re.search(r"既有|历史|旧记录|筛出", clause_prefix)):
                    continue
                if _PLAN_NEGATION.search(prefix) or _PLAN_NEGATION.search(match.group()):
                    continue
                return (
                    "AI task plan extracts personal attribution from shared-account "
                    "history that explicitly cannot distinguish authors; provide "
                    "independent named contribution proof or division confirmation "
                    "and keep it pending verification"
                )
    return None


def task_boundary_error(
    *, deliverable: str, steps: list[str], acceptance_checks: list[str],
    personal_source_texts: list[str],
) -> str | None:
    texts = [deliverable, *steps, *acceptance_checks]
    if any(unsupported_attribution(text) for text in texts):
        return "AI task plan substitutes group or reference material for personal evidence"
    # Two-gate rule: the source must explicitly rule out attribution, and the
    # plan must try to extract author-distinguishable entries from that
    # history. Independent named proof / division confirmation with a
    # pending-verification state stays allowed (this differs from the
    # "本人具名提交记录" exemption above, which concerns substitution).
    if shared_history_attribution_impossible(personal_source_texts):
        extraction_error = _shared_account_extraction_error(texts)
        if extraction_error:
            return extraction_error
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
