"""Observe one numbered ZCode task using read-only local SQLite connections."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


def read_connection(path: Path):
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
    connection.execute("PRAGMA query_only=ON")
    connection.row_factory = sqlite3.Row
    return connection


def observe(number: int, session_id: str | None = None) -> dict:
    local = Path.home() / ".zcode"
    with closing(read_connection(local / "v2/tasks-index.sqlite")) as connection:
        columns = "workspace_path,task_id,task_status,provider,model,created_at,updated_at,deleted,archived"
        tasks = list(connection.execute(
            f"SELECT {columns} FROM tasks WHERE task_id=?" if session_id else
            f"SELECT {columns} FROM tasks WHERE deleted=0 AND (title LIKE ? OR title LIKE ? OR title LIKE ?)",
            (session_id,) if session_id else
            (f"传智杯{number}：%", f"传智杯{number}:%", f"传智杯{number} %"),
        ))
    if len(tasks) != 1:
        raise RuntimeError(f"Expected one matching numbered task; observed {len(tasks)}")
    task = dict(tasks[0])
    if Path(task["workspace_path"]).resolve() != Path("D:/jbcode").resolve():
        raise RuntimeError("Numbered task is outside the authorized project")
    session_id = task["task_id"]
    queries = {
        "recentModels": (
            "SELECT id,status,provider_id,model_id,variant,started_at,first_token_at,"
            "completed_at,output_tokens,error_type,finish_reason FROM model_usage "
            "WHERE session_id=? ORDER BY started_at DESC LIMIT 3"
        ),
        "recentTools": (
            "SELECT tool_name,status,started_at,completed_at,exit_code,error_type "
            "FROM tool_usage WHERE session_id=? ORDER BY started_at DESC LIMIT 3"
        ),
        "latestAssistantMetadata": (
            "SELECT time_created,time_updated,json_extract(data,'$.role') AS role,"
            "json_extract(data,'$.finish') AS finish,"
            "json_extract(data,'$.time.completed') AS completed_at "
            "FROM message WHERE session_id=? AND json_extract(data,'$.role')='assistant' "
            "ORDER BY time_created DESC LIMIT 1"
        ),
    }
    result = {
        "observedAtUtc": datetime.now(UTC).isoformat(),
        "taskNumber": number,
        "task": task,
        "scope": "read-only metadata for this exact task; no input, message, credential or database mutation",
        "caution": "An indexed running flag alone is not a live execution proof; inspect recent call timestamps and repeated observations.",
    }
    with closing(read_connection(local / "cli/db/db.sqlite")) as connection:
        for name, query in queries.items():
            result[name] = [dict(row) for row in connection.execute(query, (session_id,))]
    return result


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--number", type=int, default=19)
    parser.add_argument("--session-id", help="previously verified exact session ID; survives title changes")
    parser.add_argument("--output", help="new JSON filename in this evidence directory")
    arguments = parser.parse_args()
    if not 1 <= arguments.number <= 9999:
        parser.error("number must be between 1 and 9999")
    if arguments.session_id and not re.fullmatch(
        r"sess_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        arguments.session_id,
    ):
        parser.error("session ID must be a previously verified sess_UUID")
    output = None
    if arguments.output:
        if Path(arguments.output).name != arguments.output or not arguments.output.endswith(".json"):
            parser.error("output must be a JSON filename without directories")
        output = Path(__file__).with_name(arguments.output)
        if output.exists():
            parser.error("snapshot already exists; choose a new output filename")
    serialized = json.dumps(observe(arguments.number, arguments.session_id), ensure_ascii=False, indent=2) + "\n"
    if output:
        with output.open("x", encoding="utf-8") as destination:
            destination.write(serialized)
    print(serialized, end="")
