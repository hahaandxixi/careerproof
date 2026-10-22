"""Bounded test-source selection. Uploaded output remains an untrusted candidate."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

OUTPUT_SUMMARY = re.compile(
    r"(?m)^[ \t]*(?:=+[ \t]*)?\d+[ \t]+(?:passed|failed|errors?|skipped)\b[^\n]*$"
)


def pytest_output_line(path: str, content: str) -> int | None:
    if PurePosixPath(path).suffix.lower() not in {".txt", ".log"}:
        return None
    # Recognize an output format, never its truth or its relation to the code.
    if (
        "pytest" not in path.lower()
        and "test session starts" not in content
        and "[100%]" not in content
    ):
        return None
    match = OUTPUT_SUMMARY.search(content)
    return content.count("\n", 0, match.start()) + 1 if match else None


def output_candidate(entry) -> bool:
    return (
        entry.provenance == "portfolio" and entry.evidence_type == "retrieved_context"
        and pytest_output_line(entry.file_path, entry.snippet) is not None
    )


def select_test_context(entries, limit: int):
    personal_tests = [entry for entry in entries
                      if entry.provenance == "portfolio" and entry.evidence_type == "pytest_test"]
    outputs = [entry for entry in entries if output_candidate(entry)]
    if not personal_tests:
        return entries[:limit]
    # Keep real assertion code ahead of fixtures/dependencies. With room, reserve
    # one slot for an uploaded output, explicitly NOT proof of successful execution.
    chosen = personal_tests[:max(1, limit - bool(outputs and limit > 1))]
    if outputs and len(chosen) < limit:
        chosen.append(outputs[0])
    for entry in entries:
        if len(chosen) == limit:
            break
        if entry not in chosen:
            chosen.append(entry)
    return chosen
