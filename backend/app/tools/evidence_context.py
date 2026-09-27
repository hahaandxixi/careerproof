"""Bounded, source-exact context retrieval. Never executes uploaded code."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import replace

from app.tools.code_analyzer import CodeEvidence, ProjectFileSnapshot
from app.tools.matcher import MatchResult

MAX_LINES = 40
MAX_CHARACTERS = 4000
MAX_EVIDENCE_PER_REQUIREMENT = 12


def source_key(evidence) -> tuple:
    return (evidence.file_path, evidence.line_start, evidence.line_end, evidence.evidence_type)


def retrieve_context(
    evidence: CodeEvidence, file: ProjectFileSnapshot, tree: ast.AST | None
) -> CodeEvidence:
    lines = file.content.splitlines()
    if evidence.content_hash != hashlib.sha256(file.content.encode("utf-8")).hexdigest():
        raise ValueError("Evidence source hash mismatch")
    start, end = evidence.line_start, evidence.line_end
    if not 1 <= start <= end <= len(lines):
        raise ValueError("Evidence source range is invalid")
    if evidence.snippet != "\n".join(lines[start - 1 : end]).strip()[:240]:
        raise ValueError("Evidence anchor does not match source")

    complete = False
    function_start = function_end = None
    note = "局部原文，不能据此判断完整实现；运行结果和本人贡献需人工核验"
    if "dependency" in evidence.evidence_type:
        complete, note = True, "完整依赖声明；仅证明声明，不能证明安装、运行或功能实现"
    elif tree is not None:
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                node_start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                node_end = node.end_lineno or node.lineno
                if node_start <= start <= end <= node_end:
                    functions.append((node_end - node_start, node_start, node_end))
        if functions:
            _, start, end = min(functions)
            function_start, function_end = start, end
            complete = True
            note = "已补取整个函数及装饰器原文；未执行代码，测试结果与本人贡献需人工核验"

    # One supplementary source read only. Expand to the enclosing function when
    # available, otherwise retain a small contiguous window around the anchor.
    if not complete:
        start, end = max(1, start - 2), min(len(lines), end + 6)
    wanted_start, wanted_end = start, end
    anchor_start, anchor_end = evidence.line_start, evidence.line_end
    anchor_text = "\n".join(lines[anchor_start - 1 : anchor_end])
    if anchor_end - anchor_start + 1 > MAX_LINES or len(anchor_text) > MAX_CHARACTERS:
        raise ValueError("Source anchor exceeds the context budget")

    # Keep the existing head window for early anchors. For late anchors, shift
    # a bounded continuous window towards them instead of collapsing to one line.
    end = min(wanted_end, start + MAX_LINES - 1)
    if anchor_end > end:
        start = max(
            wanted_start,
            anchor_end - MAX_LINES + 1,
            min(anchor_start - MAX_LINES // 2, wanted_end - MAX_LINES + 1),
        )
        end = min(wanted_end, start + MAX_LINES - 1)
    while len("\n".join(lines[start - 1 : end])) > MAX_CHARACTERS:
        # Trim the farther side, never any part of the verified anchor. The
        # anchor budget check guarantees at least one removable side exists.
        before, after = anchor_start - start, end - anchor_end
        if before > after:
            start += 1
        else:
            end -= 1
    if start > wanted_start or end < wanted_end:
        complete = False
        note = "上下文超过40行或4000字符，只展示连续局部原文；其余实现和运行结果需人工核验"
    snippet = "\n".join(lines[start - 1 : end])
    if not snippet.strip():
        raise ValueError("Source context is empty")
    return replace(
        evidence,
        line_start=start,
        line_end=end,
        snippet=snippet,
        context_complete=complete,
        context_note=note,
        function_line_start=function_start,
        function_line_end=function_end,
    )


def enrich_evidence(result: MatchResult, files: list[ProjectFileSnapshot]) -> MatchResult:
    file_map = {file.path.replace("\\", "/"): file for file in files}
    trees: dict[str, ast.AST | None] = {}
    expanded = 0
    limited = 0
    items = []
    for item in result.items:
        evidence_list = []
        for evidence in item.evidence_list[:MAX_EVIDENCE_PER_REQUIREMENT]:
            file = file_map[evidence.file_path]
            if file.path not in trees:
                try:
                    trees[file.path] = (
                        ast.parse(file.content) if file.path.endswith(".py") else None
                    )
                except (SyntaxError, ValueError):
                    trees[file.path] = None
            contextual = retrieve_context(evidence, file, trees[file.path])
            expanded += contextual.line_end > contextual.line_start
            limited += not contextual.context_complete
            evidence_list.append(contextual)
        items.append(
            replace(
                item,
                evidence_list=evidence_list,
                evidence=evidence_list[0] if evidence_list and item.evidence else None,
            )
        )
    return replace(
        result,
        items=items,
        retrieval_steps=[
            {
                "name": "补取并核对证据上下文",
                "rounds": 1 if expanded else 0,
                "expandedCount": expanded,
                "limitedCount": limited,
                "sourceExact": True,
                "maxLines": MAX_LINES,
                "maxCharacters": MAX_CHARACTERS,
            },
            *result.retrieval_steps,
        ],
    )
