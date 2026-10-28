"""One-off V1 consolidation into a separately restored, empty PostgreSQL schema.

The local manifest contains source connection credentials and storage roots. Keep it
outside Git. Sources are read-only. Existing target rows must match exactly; only
semantically identical skill dictionary entries are mapped to a canonical ID.
Historical JSON, timestamps, business identities and authorization are untouched.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path

import asyncpg


def quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def skill_signature(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in {"id", "created_at", "updated_at", "version"}}


def file_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def merge_files(sources: list[dict], destination: Path, apply: bool) -> dict:
    files: dict[str, tuple[Path, str, int]] = {}
    target = destination.resolve()
    for source in sources:
        root = Path(source["storage"]).resolve()
        if root == target or root in target.parents or target in root.parents:
            raise ValueError("Target storage must be separate from every source")
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("Source storage contains an external link")
            relative = path.relative_to(root).as_posix()
            digest = file_digest(path)
            if relative in files and files[relative][1] != digest:
                raise ValueError(f"Conflicting storage content: {relative}")
            files[relative] = (path, digest, path.stat().st_size)
    for relative, (path, digest, _) in files.items():
        output = target / relative
        if output.exists() and file_digest(output) != digest:
            raise ValueError(f"Target file differs: {relative}")
        if apply and not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, output)
        if apply and file_digest(output) != digest:
            raise ValueError(f"Copy verification failed: {relative}")
    return {
        "files": len(files),
        "bytes": sum(item[2] for item in files.values()),
        "manifestSha256": hashlib.sha256(
            json.dumps({key: value[1] for key, value in sorted(files.items())}).encode()
        ).hexdigest(),
    }


async def connect(config: dict):
    return await asyncpg.connect(
        host=config.get("host", "127.0.0.1"),
        port=config["port"],
        database=config["database"],
        user=config["user"],
        password=config["password"],
    )


async def consolidate(sources: list[dict], target: dict, storage: Path, apply: bool) -> dict:
    def identity(item):
        return (item.get("host", "127.0.0.1"), item["port"], item["database"])

    if identity(target) in {identity(source) for source in sources}:
        raise ValueError("Refusing a source database as target")
    destination = await connect(target)
    try:
        tables = [
            r[0]
            for r in await destination.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            )
            if r[0] != "alembic_version"
        ]
        if not tables:
            raise ValueError("Restore schema from a source backup before consolidation")
        revision = await destination.fetchval("SELECT version_num FROM alembic_version")
        foreign = await destination.fetch("""
            SELECT child.relname AS child, parent.relname AS parent, ca.attname AS column
            FROM pg_constraint c JOIN pg_class child ON child.oid=c.conrelid
            JOIN pg_class parent ON parent.oid=c.confrelid
            JOIN LATERAL unnest(c.conkey) WITH ORDINALITY k(attnum,ord) ON true
            JOIN pg_attribute ca ON ca.attrelid=child.oid AND ca.attnum=k.attnum
            WHERE c.contype='f' AND c.connamespace='public'::regnamespace
        """)
        dependencies = {
            table: {r["parent"] for r in foreign if r["child"] == table and r["parent"] != table}
            for table in tables
        }
        ordered = []
        while dependencies:
            ready = sorted(table for table, parents in dependencies.items() if not parents)
            if not ready:
                raise ValueError("Cyclic dependencies require explicit review")
            ordered.extend(ready)
            dependencies = {
                table: parents.difference(ready)
                for table, parents in dependencies.items()
                if table not in ready
            }
        primary = {}
        for table in tables:
            primary[table] = [
                r[0]
                for r in await destination.fetch(
                    """
                SELECT a.attname FROM pg_index i
                JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum,ord) ON true
                JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum
                WHERE i.indrelid=$1::regclass AND i.indisprimary ORDER BY k.ord
            """,
                    table,
                )
            ]
            if not primary[table]:
                raise ValueError(f"No primary key: {table}")
        union = defaultdict(dict)
        before = {}
        canonical = {}
        skill_map = {}
        for source in sources:
            connection = await connect(source)
            try:
                async with connection.transaction(isolation="repeatable_read", readonly=True):
                    if (
                        await connection.fetchval("SELECT version_num FROM alembic_version")
                        != revision
                    ):
                        raise ValueError("Source migration revision differs")
                    before[source["tag"]] = {}
                    for table in ordered:
                        rows = [
                            dict(r)
                            for r in await connection.fetch(f"SELECT * FROM {quoted(table)}")
                        ]
                        before[source["tag"]][table] = len(rows)
                        if table == "skills":
                            for row in rows:
                                name = row["name"]
                                if name in canonical:
                                    old = canonical[name]
                                    if skill_signature(old) != skill_signature(row):
                                        raise ValueError(f"Skill dictionary differs: {name}")
                                    skill_map[row["id"]] = old["id"]
                                else:
                                    canonical[name] = row
                                    skill_map[row["id"]] = row["id"]
                        for row in rows:
                            for fk in foreign:
                                if (
                                    fk["child"] == table
                                    and fk["parent"] == "skills"
                                    and row[fk["column"]] is not None
                                ):
                                    row[fk["column"]] = skill_map[row[fk["column"]]]
                            if table == "skills" and skill_map[row["id"]] != row["id"]:
                                continue
                            key = tuple(row[column] for column in primary[table])
                            if key in union[table] and union[table][key] != row:
                                raise ValueError(f"Conflicting business identity: {table} {key}")
                            union[table][key] = row
            finally:
                await connection.close()
        file_result = merge_files(sources, storage, apply)
        # Check every original/parsed material reference before writing any target rows.
        missing = []
        for table, rows in union.items():
            for row in rows.values():
                for column, value in row.items():
                    if "storage_key" in column and value:
                        relative = Path(value)
                        if relative.is_absolute() or ".." in relative.parts:
                            raise ValueError("Unsafe material storage key")
                        if not any((Path(s["storage"]) / relative).is_file() for s in sources):
                            missing.append((table, str(row.get("id")), column))
        if missing:
            raise ValueError(f"Missing material references: {missing}")
        inserted = {}
        async with destination.transaction():
            await destination.execute("SELECT pg_advisory_xact_lock(20261028, 1)")
            for table in ordered:
                existing = {
                    tuple(r[column] for column in primary[table]): dict(r)
                    for r in await destination.fetch(f"SELECT * FROM {quoted(table)}")
                }
                pending = []
                for key, row in union[table].items():
                    if key in existing:
                        if existing[key] != row:
                            raise ValueError(f"Target row differs: {table} {key}")
                    else:
                        pending.append(row)
                inserted[table] = len(pending)
                if apply and pending:
                    columns = list(pending[0])
                    names = ",".join(map(quoted, columns))
                    placeholders = ",".join("$" + str(i + 1) for i in range(len(columns)))
                    statement = f"INSERT INTO {quoted(table)} ({names}) VALUES ({placeholders})"
                    await destination.executemany(
                        statement, [tuple(row[k] for k in columns) for row in pending]
                    )
            after = {
                table: await destination.fetchval(f"SELECT count(*) FROM {quoted(table)}")
                for table in ordered
            }
        return {
            "applied": apply,
            "migration": revision,
            "before": before,
            "expectedUnion": {table: len(union[table]) for table in ordered},
            "inserted": inserted,
            "after": after,
            "storage": file_result,
            "skillIdMap": {str(k): str(v) for k, v in skill_map.items() if k != v},
            "missingFiles": missing,
        }
    finally:
        await destination.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = await consolidate(
        manifest["sources"], manifest["target"], Path(manifest["storage"]), args.apply
    )
    args.result.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "applied": args.apply,
                "inserted": sum(result["inserted"].values()),
                "files": result["storage"]["files"],
                "missingFiles": len(result["missingFiles"]),
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
