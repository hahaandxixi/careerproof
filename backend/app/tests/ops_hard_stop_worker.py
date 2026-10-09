"""Budgeted hard-stop child: runs a real verification or matching entry, then blocks.

Invoked by test_attempt_hard_stop.py as a separate Python process with a JSON config
file. The phase hook is patched in memory only (production source is untouched); after
the configured phase has really committed, the child writes its marker and waits
forever so the parent can perform a genuine process hard stop.
"""

import asyncio
import json
import os
import re
import sys
import traceback
from pathlib import Path
from uuid import UUID

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.agents.provider import DeepSeekProvider  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.models.analysis import AnalysisTask  # noqa: E402
from app.models.recruitment import Application  # noqa: E402

SYNTHETIC_KEY = "sk-synthetic-hard-stop-key-000003"


def record_state(state_file: Path, payload: dict) -> None:
    # Publish a complete marker: the parent polls concurrently while this worker
    # moves from preflight to the requested phase. Never expose truncated JSON.
    pending = state_file.with_suffix(state_file.suffix + ".pending")
    pending.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    pending.replace(state_file)


def validate_config(config):
    """Reject foreign destinations and invalid windows before DB/model access."""
    chain = config.get("chain", "verification")
    if chain not in {"verification", "matching"}:
        raise ValueError("Unsupported owned hard-stop chain")
    if config.get("phase") not in {
        "send_intent_committed", "response_observed", "receipt_committed", "ledger_committed",
    }:
        raise ValueError("Unsupported owned hard-stop phase")
    if not re.fullmatch(r"cp_test_[0-9a-f]{32}", config.get("schema", "")):
        raise ValueError("The hard-stop worker requires a dedicated cp_test schema")
    url = make_url(config["database_url"])
    if (url.drivername != "postgresql+asyncpg" or url.host not in {"localhost", "127.0.0.1"}
            or url.database != "careerproof"):
        raise ValueError("The hard-stop worker only accepts the local careerproof test database")
    maximum = config.get("input_limit", 40000)
    if type(maximum) is not int or not 1000 <= maximum <= 100000:
        raise ValueError("Invalid hard-stop input bound")
    if chain == "matching":
        storage = Path(config.get("storage_base_dir", "")).resolve()
        test_root = Path(config["state_file"]).resolve().parent
        if not storage.is_relative_to(BACKEND_ROOT):
            raise ValueError("Matching storage must stay in this repository's test directory")
        relative = storage.relative_to(BACKEND_ROOT)
        if (not relative.parts or not relative.parts[0].startswith(".tmp-")
                or storage not in {test_root, test_root / "materials"}):
            raise ValueError("Matching storage must belong to this hard-stop test's materials")
    UUID(config["task_id"])
    return chain


async def run(config: dict) -> None:
    chain = validate_config(config)
    schema = config["schema"]
    database_url = config["database_url"]
    state_file = Path(config["state_file"])
    counter_file = Path(config["counter_file"])
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("The hard-stop worker only accepts postgresql+asyncpg test URLs")
    if not re.fullmatch(r"cp_test_[0-9a-f]{32}", schema):
        raise ValueError("The hard-stop worker only accepts a dedicated cp_test schema")

    # Safety interlock before anything else: even if the parent environment carries
    # external AI settings, the child must never be able to reach a real provider.
    settings.ai_external_enabled = False
    settings.deepseek_api_key = None
    settings.ai_per_report_input_token_limit = config.get("input_limit", 40000)
    if chain == "matching":
        settings.storage_base_dir = Path(config["storage_base_dir"]).resolve()
    settings.semantic_retrieval_enabled = False
    settings.ai_max_retrieval_calls = 0

    engine = create_async_engine(database_url, connect_args={
        "server_settings": {"search_path": f"{schema},public"},
    })
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # No data access of any kind before current_schema and every resolved table
    # namespace are proven to live in this child's own cp_test schema. The parent
    # fixture creates every metadata table except knowledge_chunks, which the
    # shared development database only ever keeps in public.
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT current_schema()")) == schema
        for table in sorted(Base.metadata.tables):
            if table == "knowledge_chunks":
                continue
            namespace = await connection.scalar(text(
                "SELECT n.nspname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE c.oid=to_regclass(:table)"
            ), {"table": table})
            assert namespace == schema, f"{table} resolved to {namespace}"
    record_state(state_file, {
        "event": "preflight_ok", "pid": os.getpid(), "nonce": config["nonce"],
        "schema": schema, "task_id": config["task_id"],
    })

    from app.agents import evidence_workflow
    from app.services import analysis as matching
    from app.services import application_verification as verification
    from app.services.ai_request_attempts import AttemptService
    from app.tests.test_application_verification import completion, model_answer

    async with factory() as session:
        task = await session.get(AnalysisTask, UUID(config["task_id"]))
        if chain == "verification":
            application = await session.get(
                Application, UUID(task.input_snapshot["applicationId"])
            )
            snapshot = application.report_snapshot

    http_count = {"value": 0}

    def count_http() -> int:
        http_count["value"] += 1
        # The counter file only proves how many physical sends happened; the parent
        # never reads a receipt or usage back from it.
        counter_file.write_text(str(http_count["value"]), encoding="utf-8")
        return http_count["value"]

    async def handler(request):
        count_http()
        if chain == "matching":
            from app.tests.test_durable_matching_review import valid_response
            return valid_response(request, inputs=123, outputs=45)
        return completion(model_answer(snapshot))

    provider = DeepSeekProvider(
        api_key=SYNTHETIC_KEY,
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=5,
        max_attempts=1,
        transport=httpx.MockTransport(handler),
    )
    verification.get_ai_provider = lambda: provider
    evidence_workflow.get_ai_provider = lambda: provider
    matching.async_session_factory = factory
    # The parent created the task under a DeepSeek identity; keep the binding
    # cacheKey continuous while the external interlock above stays off.
    verification._identity = lambda: ("deepseek", "deepseek-flash")
    if chain == "matching":
        # Only after both factories are fixed to this MockTransport provider.
        settings.ai_external_enabled = True
        settings.ai_provider = "deepseek"

    original_phase = AttemptService._phase

    async def hanging_phase(self, name, attempt_id):
        await original_phase(self, name, attempt_id)
        if name == config["phase"]:
            record_state(state_file, {
                "event": "hanging", "phase": name, "pid": os.getpid(),
                "nonce": config["nonce"], "schema": schema,
                "task_id": config["task_id"], "attempt_id": str(attempt_id),
                "http_count": http_count["value"],
            })
            await asyncio.Event().wait()  # the real hard stop happens in the parent

    AttemptService._phase = hanging_phase
    try:
        if chain == "verification":
            await verification.execute_application_verification_task(
                UUID(config["task_id"]), session_factory=factory,
            )
        else:
            await matching.execute_match_task(UUID(config["task_id"]))
    finally:
        AttemptService._phase = original_phase
    record_state(state_file, {
        "event": "child_returned", "pid": os.getpid(), "phase": config["phase"],
        "nonce": config["nonce"], "http_count": http_count["value"],
    })
    await engine.dispose()


def main() -> int:
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    state_file = Path(config["state_file"])
    try:
        asyncio.run(run(config))
        return 0
    except BaseException:
        record_state(state_file, {
            "event": "child_error", "pid": os.getpid(), "phase": config["phase"],
            "nonce": config["nonce"], "traceback": traceback.format_exc(),
        })
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
