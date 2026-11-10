"""Deterministic technical knowledge retrieval and idempotent seeding.

This scope is global and curated; it never reads or widens the owner-scoped
material index in ``retrieval.py``. Ranking is lexical and deterministic so the
same rows answer the same way in tests and production.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.technical_seed import TECHNICAL_KNOWLEDGE, content_digest
from app.models.knowledge import TechnicalKnowledgeEntry

SKILL_FAMILIES = {
    "python": "python",
    "pandas": "python",
    "numpy": "python",
    "sql": "sql",
    "mysql": "sql",
    "postgresql": "sql",
    "postgres": "sql",
    "sqlite": "sql",
    "pytest": "pytest",
    "unittest": "pytest",
    "测试": "pytest",
    "单元测试": "pytest",
}

TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.+#-]*|[\u4e00-\u9fff]{2,}")


@dataclass(frozen=True)
class RankedEntry:
    entry: TechnicalKnowledgeEntry
    score: int


def skill_family(skill: str) -> str:
    value = (skill or "").strip().casefold()
    if not value:
        return ""
    for alias, family in SKILL_FAMILIES.items():
        if alias in value:
            return family
    return value


def entry_family(entry: TechnicalKnowledgeEntry) -> str:
    return skill_family(f"{entry.skill} {entry.topic}")


def rank_entries(
    entries: list[TechnicalKnowledgeEntry],
    *,
    skill: str,
    text: str = "",
    limit: int = 3,
) -> list[TechnicalKnowledgeEntry]:
    """Prefer the requirement's skill family, then lexical overlap.

    Ties fall back to the stable knowledge id so repeated calls are identical.
    """
    family = skill_family(skill)
    terms = {token.casefold() for token in TOKEN_PATTERN.findall(text or "")}
    scored: list[tuple[int, str, TechnicalKnowledgeEntry]] = []
    for entry in entries:
        score = 0
        if family and entry_family(entry) == family:
            score += 6
        haystack = f"{entry.title} {entry.summary} {' '.join(entry.tags or [])}".casefold()
        score += sum(1 for term in terms if term and term in haystack)
        if score <= 0:
            continue
        scored.append((-score, entry.knowledge_id, entry))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [entry for _score, _key, entry in scored[:limit]]


async def load_entries(session: AsyncSession) -> list[TechnicalKnowledgeEntry]:
    return list(
        await session.scalars(
            select(TechnicalKnowledgeEntry).order_by(TechnicalKnowledgeEntry.knowledge_id)
        )
    )


async def search_technical_knowledge(
    session: AsyncSession, *, skill: str, text: str = "", limit: int = 3
) -> list[TechnicalKnowledgeEntry]:
    entries = await load_entries(session)
    return rank_entries(entries, skill=skill, text=text, limit=limit)


async def seed_technical_knowledge(session: AsyncSession) -> int:
    """Insert missing cards and refresh changed ones without duplicating rows."""
    existing = {row.knowledge_id: row for row in await load_entries(session)}
    changed = 0
    for item in TECHNICAL_KNOWLEDGE:
        digest = content_digest(item)
        row = existing.get(item["knowledge_id"])
        values = {
            key: value
            for key, value in item.items()
            if key != "knowledge_id"
        }
        values["content_hash"] = digest
        if row is None:
            session.add(TechnicalKnowledgeEntry(knowledge_id=item["knowledge_id"], **values))
            changed += 1
        elif row.content_hash != digest:
            for key, value in values.items():
                setattr(row, key, value)
            changed += 1
    return changed
