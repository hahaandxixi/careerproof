"""Read-only comparison with the last pre-incident normal-database digest."""

import asyncio
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

OUT = Path(__file__).resolve().parent
BASELINE = OUT.parent / "20261019-postgres-skipped-coverage/normal-after.json"


async def main():
    url = make_url(settings.database_url)
    assert url.host in {"127.0.0.1", "localhost"} and url.port in {None, 5432}
    assert url.database == "careerproof"
    engine = create_async_engine(
        settings.database_url, hide_parameters=True, isolation_level="REPEATABLE READ"
    )
    try:
        async with engine.connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            tables = (await connection.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            ))).scalars().all()
            quote = connection.dialect.identifier_preparer.quote
            current, normalized = {}, {}
            for name in tables:
                source = quote(name)
                query = (
                    "SELECT count(*), md5(COALESCE(string_agg(row_to_json(t)::text, '' "
                    f"ORDER BY row_to_json(t)::text), '')) FROM {source} t"
                )
                row = (await connection.execute(text(query))).one()
                current[name] = {"rows": row[0], "digest": row[1]}
                normalized[name] = current[name]
                if name == "jobs":
                    columns = (await connection.execute(text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name='jobs' "
                        "AND column_name NOT IN ('is_demo','discovery_visible') "
                        "ORDER BY ordinal_position"
                    ))).scalars().all()
                    old_source = f"(SELECT {','.join(map(quote, columns))} FROM jobs)"
                    row = (await connection.execute(text(query.replace(source, old_source)))).one()
                    normalized[name] = {"rows": row[0], "digest": row[1]}
            flags = (await connection.execute(text(
                "SELECT count(*) AS total, count(*) FILTER (WHERE is_demo) AS demos, "
                "count(*) FILTER (WHERE NOT discovery_visible) AS hidden FROM jobs"
            ))).mappings().one()
            indexes = (await connection.execute(text(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' "
                "AND tablename='jobs' AND indexname IN "
                "('ix_jobs_is_demo','ix_jobs_discovery_visible') ORDER BY indexname"
            ))).mappings().all()
            baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
            changed = [name for name, value in normalized.items()
                       if value != baseline["tables"].get(name)]
            result = {
                "revision": revision, "tables": current,
                "legacyColumnNormalizedTables": normalized,
                "baseline": str(BASELINE.relative_to(OUT.parents[2])).replace("\\", "/"),
                "changedAfterExcludingOnlyNewJobColumns": changed,
                "jobFlags": dict(flags), "newIndexes": [dict(row) for row in indexes],
                "readOnly": True,
            }
            with (OUT / "normal-readonly-audit.json").open("x", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2)
            print(json.dumps({"revision": revision, "changedTables": changed,
                              "jobFlags": dict(flags)}, ensure_ascii=False))
    finally:
        await engine.dispose()


asyncio.run(main())
