"""Bounded observations of exact selected sources, never a business or run verdict.

Only new rule reports persist this text. Neither selection, ratings, model inputs
nor historical reports are changed by these presentation facts.
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import PurePosixPath

from app.tools.code_analyzer import FrozenRetrievalSource
from app.tools.display_path import display_file_path, display_path_text

VERSION = "rule-narrative-v1"
MAX_TEXT = 2200
IMPLEMENTATIONS = {
    "python_code", "fastapi_route", "pytest_test", "sql_query", "sql_schema",
    "react_component", "typescript_code",
}


def _source_observations(snippet: str, path: str) -> str:
    if not path.endswith(".py"):
        return "源码片段"
    try:
        tree = ast.parse(textwrap.dedent(snippet))
    except (SyntaxError, ValueError, RecursionError):
        return "局部源码，结构尚未确认"
    nodes = list(ast.walk(tree))
    names = [node.name for node in tree.body
             if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)]
    facts = []
    if any(isinstance(node, ast.If) for node in nodes):
        facts.append("条件分支")
    if any(isinstance(node, ast.Raise) for node in nodes):
        facts.append("显式抛错")
    if any(isinstance(node, ast.Assert) for node in nodes):
        facts.append("assert断言")
    for node in nodes:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in {"commit", "rollback"}:
            facts.append(node.func.attr + "调用")
        if (
            node.func.attr in {"execute", "executemany"} and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and re.match(r"\s*(?:SELECT|INSERT|UPDATE|DELETE)\b", node.args[0].value, re.I)
        ):
            facts.append("带参数的SQL调用" if len(node.args) > 1 else "SQL调用")
    labels = [*names[:2], *list(dict.fromkeys(facts))[:4]]
    return "、".join(label[:80] for label in labels) or "源码结构"


def build_rule_narrative(
    evidence: list[dict], sources: tuple[FrozenRetrievalSource, ...],
) -> dict | None:
    """Describe verified portfolio snippets; inventory means uploaded, not trusted.

    Sources must be the worker's frozen personal sources (reference/images already
    excluded). Inventory paths never become citations or affect the evidence cap.
    """
    source_map = {source.file.path: source for source in sources}
    selected = []
    seen = set()
    for entry in evidence[:12]:
        path = entry.get("file_path", "")
        source = source_map.get(path)
        if (
            not source or len(path) > 260 or entry.get("provenance") != "portfolio"
            or entry.get("evidence_type") not in IMPLEMENTATIONS
            or entry.get("content_hash") != source.content_hash
        ):
            continue
        start, end = entry["line_start"], entry["line_end"]
        lines = source.file.content.splitlines()
        if not 1 <= start <= end <= len(lines):
            continue
        snippet = "\n".join(lines[start - 1:end])
        if snippet != entry["snippet"] or len(snippet) > 4000 or end - start >= 40:
            continue
        key = (path, start, end)
        if key in seen:
            continue
        seen.add(key)
        selected.append(
            f"{display_file_path(path)} 第{start}—{end}行"
            f"（{_source_observations(snippet, path)}）"
        )
        if len(selected) == 3:
            break
    if not selected:
        return None
    reason = (
        "本项静态引用：" + "；".join(selected)
        + "。上述是源码中可见的结构，不代表本项全部业务条件已满足、运行成功或本人贡献。"
    )
    paths = sorted(path for path in source_map if len(path) <= 260)
    test_paths = [path for path in paths if PurePosixPath(path).name.startswith("test")
                  and path.endswith(".py")][:1]
    text_paths = [path for path in paths if PurePosixPath(path).suffix in {".txt", ".json"}
                  and not PurePosixPath(path).name.startswith("requirements")][:3]
    inventory = []
    if test_paths:
        inventory.append("已上传测试命名文件：" + "、".join(
            display_file_path(path) for path in test_paths
        ))
    if text_paths:
        inventory.append("已上传文本/JSON材料：" + "、".join(
            display_file_path(path) for path in text_paths
        ))
    kinds = {entry.get("evidence_type") for entry in evidence[:12]
             if entry.get("provenance") == "portfolio"}
    focus = (
        "已有断言的输入、预期结果和未覆盖的异常场景"
        if "pytest_test" in kinds else
        "SQL读写条件、参数与事务边界"
        if kinds & {"sql_query", "sql_schema"} else
        "接口输入校验、响应与错误分支"
        if "fastapi_route" in kinds else
        "上述函数的输入、条件分支、返回值与异常路径"
    )
    gap = f"先对照{focus}，逐条核对本项岗位要求。"
    if inventory:
        gap += "；".join(inventory) + "。已有材料无需重复上传；先定位其中与本项有关的断言和记录，"
        gap += "核对输入、预期/实际输出及源码版本，仅补充尚未覆盖的场景。"
    else:
        gap += "先核对所选材料中是否已有对应测试或记录，仅为尚未覆盖的场景补充验证材料。"
    gap += "文件存在不代表运行成功；记录真实性、业务覆盖和本人贡献仍未确认。"
    return {
        "version": VERSION,
        "reason": display_path_text(reason)[:MAX_TEXT],
        "gap": display_path_text(gap)[:MAX_TEXT],
    }


def saved_rule_narrative(snapshot: dict) -> dict | None:
    narrative = snapshot.get("ruleNarrative")
    if (
        isinstance(narrative, dict) and narrative.get("version") == VERSION
        and all(isinstance(narrative.get(key), str) and 0 < len(narrative[key]) <= MAX_TEXT
                for key in ("reason", "gap"))
    ):
        return narrative
    return None
