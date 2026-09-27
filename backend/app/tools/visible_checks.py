"""Bounded Python syntax facts and narrow missing-evidence conflicts, not entailment."""

import ast
import re
import textwrap


class VisibleCodeFactConflict(ValueError):
    def __init__(self, field, text, facts):
        super().__init__("Career output conflicts with a bounded visible-code fact")
        self.field = field
        self.claim = visible_check_conflict_claim(text, facts) or text
        self.citation_ids = list(
            dict.fromkeys(citation for fact in facts for citation in fact.get("citationIds", []))
        )


def parameter_error_fact(snippet):
    try:
        tree = ast.parse(textwrap.dedent(snippet))
    except (SyntaxError, ValueError):
        return False
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        parameters = {
            arg.arg
            for arg in [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
        }
        for condition in ast.walk(function):
            if not isinstance(condition, ast.If):
                continue
            referenced = {n.id for n in ast.walk(condition.test) if isinstance(n, ast.Name)}
            if not parameters.intersection(referenced):
                continue
            for node in ast.walk(condition):
                if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                    continue
                called = node.exc.func
                name = (
                    called.id
                    if isinstance(called, ast.Name)
                    else (called.attr if isinstance(called, ast.Attribute) else None)
                )
                status = next(
                    (kw.value for kw in node.exc.keywords if kw.arg == "status_code"),
                    node.exc.args[0] if node.exc.args else None,
                )
                if (
                    name == "HTTPException"
                    and isinstance(status, ast.Constant)
                    and isinstance(status.value, int)
                    and 400 <= status.value <= 599
                ):
                    return True
    return False


def visible_code_facts(job):
    citations = [
        e.citation_id
        for e in job.evidence
        if e.citation_id and e.file_path.endswith(".py") and parameter_error_fact(e.snippet)
    ]
    if not citations:
        return []
    return [
        {
            "kind": "parameter_error_branch",
            "citationIds": list(dict.fromkeys(citations)),
            "description": "片段含针对函数参数的条件判断和4xx/5xx的HTTPException；"
            "只说明源码可见，不证明实际响应或全部边界覆盖。",
        }
    ]


_SUBJECT = r"(?:(?:输入|参数)(?:校验|验证)|(?:错误|异常)(?:响应|处理))"
_NEGATIVE = r"(?:尚未|未曾|未|没有|缺少|缺乏)(?:展示|显示|提供|包含|出现|实现|可见)?"
_MISSING = re.compile(
    _SUBJECT
    + r"[^。！？；，,\n]{0,50}?"
    + _NEGATIVE
    + "|"
    + _NEGATIVE
    + r"[^。！？；，,\n]{0,20}?"
    + _SUBJECT
)


def visible_check_conflict_claim(text, facts):
    if not any(f.get("kind") == "parameter_error_branch" for f in facts):
        return None
    for sentence in re.split(r"[。！？；，,\n]", text):
        for match in _MISSING.finditer(sentence):
            # Full coverage and execution are not established by this syntax fact.
            claim = sentence[max(0, match.start() - 8) : match.end() + 20]
            if re.search(
                r"完整|所有|全部|更多|其他|覆盖|的(?:相关)?(?:测试|运行|执行|记录)", claim
            ):
                continue
            prefix = sentence[max(0, match.start() - 12) : match.start()]
            if re.search(r"不能说|不得说|并非|不是|不代表|无需", prefix):
                continue
            return sentence
    return None


def conflicts_with_visible_checks(text, facts):
    return visible_check_conflict_claim(text, facts) is not None
