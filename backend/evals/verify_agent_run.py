"""Read-only verification of a saved Agent report against frozen source evidence."""
from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from zipfile import ZipFile

MAX_COST_YUAN = 5.0
INPUT_PRICE = 2.0
OUTPUT_PRICE = 8.0


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _source_files(zip_path: Path) -> dict[str, list[str]]:
    with ZipFile(zip_path) as archive:
        return {
            name: archive.read(name).decode("utf-8", errors="replace").splitlines()
            for name in archive.namelist()
            if not name.endswith("/")
        }


def _resolve_source_path(raw_path: str, sources: dict[str, list[str]]) -> str | None:
    if raw_path in sources:
        return raw_path
    if "/" in raw_path:
        candidate = raw_path.split("/", 1)[1]
        if candidate in sources:
            return candidate
    return None


def _supported(criteria: Iterable[dict]) -> int:
    return sum(1 for row in criteria if isinstance(row, dict) and row.get("supported") is True)


def verify(
    report: dict,
    zip_path: Path,
    attempts: list[dict],
    usage: list[dict],
    *,
    min_items: int = 5,
) -> dict:
    failures: list[str] = []
    unverified: list[str] = []
    sources = _source_files(zip_path)
    items = report.get("items")
    if not isinstance(items, list) or len(items) < min_items:
        failures.append(f"report has {len(items or [])} items; expected at least {min_items}")

    all_evidence_ids: set[str] = set()
    for index, item in enumerate(items or [], 1):
        prefix = f"item[{index}] {item.get('skill') or item.get('requirementTitle')}"
        evidence_rows = item.get("evidenceList") or []
        item_ids = {row.get("citationId") for row in evidence_rows if row.get("citationId")}
        if not item_ids:
            failures.append(f"{prefix}: no citation IDs")
        all_evidence_ids.update(item_ids)
        for row in evidence_rows:
            citation = row.get("citationId") or "?"
            raw_path = str(row.get("filePath") or "")
            source_path = _resolve_source_path(raw_path, sources)
            if source_path is None:
                failures.append(f"{prefix}: evidence {citation} path not in fixed ZIP: {raw_path}")
                continue
            start, end = row.get("lineStart"), row.get("lineEnd")
            if type(start) is not int or type(end) is not int or start < 1 or end < start:
                failures.append(f"{prefix}: evidence {citation} has invalid line range")
                continue
            if end > len(sources[source_path]):
                failures.append(f"{prefix}: evidence {citation} line range exceeds source")
                continue
            if not str(row.get("snippet") or "").strip():
                failures.append(f"{prefix}: evidence {citation} has empty snippet")

        ai_ids = item.get("aiCitationIds") or []
        if not set(ai_ids).issubset(item_ids):
            failures.append(f"{prefix}: AI citation IDs are not a subset of evidence citations")

        level = item.get("evidenceLevel")
        criteria = item.get("ratingCriteria") or []
        supported = _supported(criteria)
        if item.get("verdict") in {"gap", "claimed_only", "unsupported"}:
            if level is not None:
                failures.append(f"{prefix}: non-supported verdict must not have a level")
        elif type(level) is not int or level < 1 or level > supported:
            failures.append(
                f"{prefix}: level {level!r} exceeds locally supported criteria {supported}"
            )

        if item.get("skill") == "Python":
            source_text = "\n".join(
                "\n".join(
                    sources[
                        _resolve_source_path(str(row.get("filePath") or ""), sources) or ""
                    ]
                )
                for row in evidence_rows
            )
            for token in ("def register", "def cancel", "BEGIN", "rollback"):
                if token not in source_text:
                    failures.append(f"{prefix}: missing business anchor {token!r}")
        if item.get("skill") in {"Redis"} and item.get("verdict") == "supported":
            failures.append(
                f"{prefix}: Redis is unsupported by the fixed material and must stay gap"
            )

    if not all_evidence_ids:
        failures.append("report has no usable evidence citations")

    tool_calls = report.get("aiToolCalls") or []
    completed = [call for call in tool_calls if call.get("status") == "completed"]
    for call in completed:
        if call.get("citationId") not in all_evidence_ids:
            failures.append(f"completed tool call has no valid citation: {call!r}")

    if not attempts:
        failures.append("no physical request attempts")
    if not usage:
        failures.append("no trusted usage rows")
    input_tokens = sum(int(row.get("input_tokens") or 0) for row in usage)
    output_tokens = sum(int(row.get("output_tokens") or 0) for row in usage)
    cost = (input_tokens * INPUT_PRICE + output_tokens * OUTPUT_PRICE) / 1_000_000
    if cost > MAX_COST_YUAN:
        failures.append(f"cost exceeds limit: {cost:.6f}")
    ai_usage = report.get("aiUsage") or {}
    if usage and (
        ai_usage.get("input_tokens") != input_tokens
        or ai_usage.get("output_tokens") != output_tokens
    ):
        failures.append("report aiUsage does not match trusted usage rows")

    if not completed:
        unverified.append("tool execution: no completed retrieve_more_evidence call")
    unverified.append("page rendering and human semantic review are outside this verifier")

    result = {
        "status": "fail" if failures else "pass",
        "failures": failures,
        "unverified": unverified,
        "items": len(items or []),
        "evidenceCitations": len(all_evidence_ids),
        "physicalRequests": len(attempts),
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "costYuanAtPeak": f"{cost:.6f}",
        "toolCalls": tool_calls,
        "materialZip": str(zip_path),
    }
    return result


def claims_markdown(result: dict) -> str:
    lines = [
        "# Agent run verification claims",
        "",
        f"- 状态：**{result['status']}**",
        f"- 报告项数：{result['items']}",
        f"- 证据引用数：{result['evidenceCitations']}",
        f"- 物理请求：{result['physicalRequests']}",
        f"- 输入/输出：{result['inputTokens']}/{result['outputTokens']}",
        f"- 高峰价估算：{result['costYuanAtPeak']} 元",
        "",
        "## 可声称",
        "",
        "- 引用路径/行号均来自固定 ZIP；",
        "- 每项 AI 引用均为证据引用子集；",
        "- 等级未超过本地 supported criteria 数；",
        "- 用量行存在且与报告汇总一致；",
        "- 费用未超过 5 元。",
        "",
        "## 不可声称",
        "",
    ]
    lines.extend(f"- {row}" for row in result["unverified"])
    if result["failures"]:
        lines += ["", "## 失败", ""] + [f"- {row}" for row in result["failures"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--attempts", type=Path, required=True)
    parser.add_argument("--usage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--claims", type=Path, required=True)
    parser.add_argument("--min-items", type=int, default=5)
    args = parser.parse_args()
    result = verify(
        _load_json(args.report),
        args.zip,
        _load_json(args.attempts),
        _load_json(args.usage),
        min_items=args.min_items,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.claims.write_text(claims_markdown(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
