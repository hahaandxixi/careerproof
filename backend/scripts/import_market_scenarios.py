"""Plan (default) or explicitly apply the three fictional experience scenarios.

DATABASE_URL from app settings is deliberately NOT used. Supply --database-url.
Apply also requires --enterprise-id and --confirm. Legacy curation is separate:
--legacy-enterprise-id only considers exact catalog content owned by that enterprise's
unique active owner. Unrecognized postings are preserved and reported.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.enums import MembershipRole, UserRole
from app.models.identity import Enterprise, EnterpriseMembership, User
from app.models.recruitment import Job, JobRequirement

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "demo" / "market-scenarios.json"
LEGACY_CATALOG = ROOT / "demo" / "jobs.json"
LEGACY_COMPANY = "CareerProof 合成演示企业"
LEGACY_DESCRIPTION = "合成测试岗位，不是实际招聘。请以材料证据核验要求；缺少材料不代表没有能力。"


def load_scenarios() -> dict:
    return json.loads(SCENARIOS.read_text(encoding="utf-8"))


def legacy_titles() -> set[str]:
    return {item["title"] for item in json.loads(LEGACY_CATALOG.read_text(encoding="utf-8"))}


async def _rows(session, statement):
    return list((await session.scalars(statement)).all())


async def _enterprise_owner(session: AsyncSession, enterprise_id: UUID) -> UUID:
    owners = await _rows(
        session,
        select(User.id)
        .join(EnterpriseMembership, EnterpriseMembership.user_id == User.id)
        .where(
            EnterpriseMembership.enterprise_id == enterprise_id,
            EnterpriseMembership.role == MembershipRole.OWNER,
            EnterpriseMembership.is_active.is_(True),
            User.is_active.is_(True),
            User.role.in_([UserRole.ENTERPRISE, UserRole.ADMIN]),
        ),
    )
    if len(owners) != 1:
        raise ValueError("Expected exactly one active enterprise owner; nothing changed")
    return owners[0]


def _requirements(spec):
    return sorted(
        (r["rawText"], r["skillName"], r["weight"], r["isRequired"]) for r in spec["requirements"]
    )


async def _matches(session, job, spec):
    requirements = await _rows(
        session, select(JobRequirement).where(JobRequirement.job_id == job.id)
    )
    return sorted(
        (r.raw_text, r.skill_name, r.weight, r.is_required) for r in requirements
    ) == _requirements(spec)


async def _inspect(session, payload, enterprise_id, legacy_enterprise_id):
    enterprise = await session.get(Enterprise, enterprise_id)
    if enterprise is None or enterprise.name != payload["companyName"]:
        raise ValueError("Target enterprise does not match the fictional scenario company")
    owner = await _enterprise_owner(session, enterprise_id)
    scenarios = []
    for spec in payload["scenarios"]:
        jobs = await _rows(
            session,
            select(Job).where(Job.enterprise_id == enterprise_id, Job.title == spec["title"]),
        )
        if len(jobs) > 1:
            raise ValueError("Ambiguous scenario title; no posting will be overwritten")
        job = jobs[0] if jobs else None
        if job is not None and not (
            job.is_demo
            and job.created_by == owner
            and job.company_name == payload["companyName"]
            and job.description == spec["description"]
            and job.category == spec["category"]
            and job.city == spec["city"]
            and job.employment_type == spec["employmentType"]
            and await _matches(session, job, spec)
        ):
            raise ValueError("Existing title is not an unchanged curated sample; preserved")
        scenarios.append((spec, job))
    legacy, preserved = await legacy_candidates(session, owner, legacy_enterprise_id)
    return owner, scenarios, legacy, preserved


async def legacy_candidates(session, owner, legacy_enterprise_id):
    legacy, preserved = [], []
    if legacy_enterprise_id is not None:
        old = await session.get(Enterprise, legacy_enterprise_id)
        if old is None or old.name != LEGACY_COMPANY:
            raise ValueError("Legacy enterprise is not the confirmed legacy demo company")
        old_owner = await _enterprise_owner(session, legacy_enterprise_id)
        if old_owner != owner:
            raise ValueError("Scenario and legacy enterprises must share the confirmed owner")
        catalog = {s["title"]: s for s in json.loads(LEGACY_CATALOG.read_text(encoding="utf-8"))}
        for job in await _rows(
            session,
            select(Job).where(Job.enterprise_id == legacy_enterprise_id, Job.title.in_(catalog)),
        ):
            if (
                job.created_by == old_owner
                and job.company_name == LEGACY_COMPANY
                and job.description == LEGACY_DESCRIPTION
                and job.category == catalog[job.title]["category"]
                and await _matches(session, job, catalog[job.title])
            ):
                legacy.append(job)
            else:
                preserved.append(str(job.id))
    return legacy, preserved


async def build_plan(session, payload, enterprise_id, legacy_enterprise_id=None):
    plan = {
        "version": payload["version"],
        "companyName": payload["companyName"],
        "notice": payload["notice"],
        "targetEnterprise": None,
        "scenarios": [],
        "legacyToHide": [],
        "preservedUnproven": [],
        "ambiguities": [],
    }
    if session is None or enterprise_id is None:
        plan["ambiguities"] = ["Explicit database and target enterprise are required to apply"]
        plan["scenarios"] = [
            {"title": s["title"], "action": "unresolved"} for s in payload["scenarios"]
        ]
        return plan
    owner, scenarios, legacy, preserved = await _inspect(
        session, payload, enterprise_id, legacy_enterprise_id
    )
    plan["targetEnterprise"] = {
        "id": str(enterprise_id),
        "name": payload["companyName"],
        "ownerId": str(owner),
        "resolved": True,
    }
    plan["scenarios"] = [
        {
            "title": s["title"],
            "action": "preserve" if j else "create",
            "jobId": str(j.id) if j else None,
            "status": j.status if j else "published",
        }
        for s, j in scenarios
    ]
    plan["legacyToHide"] = [
        {
            "jobId": str(j.id),
            "title": j.title,
            "status": j.status,
            "alreadyHidden": not j.discovery_visible,
            "evidence": "explicit legacy enterprise + active owner + exact catalog content",
        }
        for j in legacy
    ]
    plan["preservedUnproven"] = preserved
    return plan


async def apply_plan(session, payload, enterprise_id, legacy_enterprise_id=None):
    # Lock both enterprises in deterministic order, serializing concurrent PG imports.
    ids = sorted({enterprise_id, legacy_enterprise_id} - {None}, key=str)
    await _rows(
        session,
        select(Enterprise).where(Enterprise.id.in_(ids)).order_by(Enterprise.id).with_for_update(),
    )
    owner, scenarios, legacy, preserved = await _inspect(
        session, payload, enterprise_id, legacy_enterprise_id
    )
    created, hidden = [], []
    for spec, existing in scenarios:
        if existing is not None:
            continue  # Preserve status, visibility, requirements and timestamps on replay.
        job = Job(
            enterprise_id=enterprise_id,
            created_by=owner,
            title=spec["title"],
            company_name=payload["companyName"],
            description=spec["description"],
            category=spec["category"],
            city=spec["city"],
            employment_type=spec["employmentType"],
            status="published",
            is_demo=True,
            discovery_visible=True,
        )
        session.add(job)
        await session.flush()
        session.add_all(
            [
                JobRequirement(
                    job_id=job.id,
                    raw_text=r["rawText"],
                    skill_name=r["skillName"],
                    weight=r["weight"],
                    is_required=r["isRequired"],
                    normalized_status="pending",
                )
                for r in spec["requirements"]
            ]
        )
        created.append(str(job.id))
    for job in legacy:
        if job.discovery_visible:
            job.discovery_visible = False
            job.is_demo = True
            hidden.append(str(job.id))
    await session.commit()
    return {"created": created, "updated": [], "hidden": hidden, "preservedUnproven": preserved}


async def enable_read_only(session):
    if session.bind.dialect.name == "postgresql":
        await session.execute(text("SET TRANSACTION READ ONLY"))
    elif session.bind.dialect.name == "sqlite":
        await session.execute(text("PRAGMA query_only=ON"))
    else:
        raise ValueError("Unsupported plan database")


async def seed_scenarios(session, owner_id):
    """Called only by the explicit development demo seeder, never by startup/migration."""
    owner = await session.scalar(select(User).where(User.id == owner_id).with_for_update())
    if owner is None or not owner.is_active or owner.role != UserRole.ENTERPRISE:
        raise ValueError("Demo seed requires an active enterprise identity")
    payload = load_scenarios()
    organizations = await _rows(
        session,
        select(Enterprise)
        .join(EnterpriseMembership, EnterpriseMembership.enterprise_id == Enterprise.id)
        .where(
            EnterpriseMembership.user_id == owner_id,
            EnterpriseMembership.role == MembershipRole.OWNER,
            EnterpriseMembership.is_active.is_(True),
        ),
    )
    targets = [e for e in organizations if e.name == payload["companyName"]]
    legacy = [e for e in organizations if e.name == LEGACY_COMPANY]
    if len(targets) > 1 or len(legacy) > 1:
        raise ValueError("Ambiguous demo enterprise; existing organizations preserved")
    if not targets:
        target = Enterprise(name=payload["companyName"], description=payload["notice"])
        session.add(target)
        await session.flush()
        session.add(
            EnterpriseMembership(
                enterprise_id=target.id, user_id=owner_id, role=MembershipRole.OWNER, is_active=True
            )
        )
        await session.flush()
    else:
        target = targets[0]
    return await apply_plan(session, payload, target.id, legacy[0].id if legacy else None)


def validate_local_url(value):
    url = make_url(value)
    if url.drivername == "sqlite+aiosqlite":
        return
    if url.drivername != "postgresql+asyncpg" or url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Only explicit local PostgreSQL or temporary SQLite targets are supported")


async def run(args):
    payload = load_scenarios()
    if args.apply and (not args.database_url or not args.enterprise_id or not args.confirm):
        raise ValueError("Apply requires --database-url, --enterprise-id and --confirm")
    if not args.database_url:
        print(json.dumps(await build_plan(None, payload, None), ensure_ascii=False, indent=2))
        return 0
    validate_local_url(args.database_url)
    engine = create_async_engine(args.database_url, hide_parameters=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            enterprise_id = UUID(args.enterprise_id) if args.enterprise_id else None
            legacy_id = UUID(args.legacy_enterprise_id) if args.legacy_enterprise_id else None
            if not args.apply:
                await enable_read_only(session)
                result = await build_plan(session, payload, enterprise_id, legacy_id)
            else:
                result = await apply_plan(session, payload, enterprise_id, legacy_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
    finally:
        await engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url")
    parser.add_argument("--enterprise-id")
    parser.add_argument("--legacy-enterprise-id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    return asyncio.run(run(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
