"""Deterministic technical knowledge retrieval and idempotent seeding.

This scope is global and curated; it never reads or widens the owner-scoped
material index in ``retrieval.py``. Ranking is lexical and deterministic so the
same rows answer the same way in tests and production.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.technical_seed import TECHNICAL_KNOWLEDGE, TOPIC_ALIASES, content_digest
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

WORD = re.compile(r"[a-z][a-z0-9_.+#-]*")
BACKGROUND_WORDS = {*SKILL_FAMILIES, "清洗", "聚合", "分组", "异常"}


def _phrase_match(phrase: str, query: str) -> bool:
    phrase = phrase.casefold()
    if phrase.isascii() and phrase[-1].isalnum():
        return bool(re.search(r"(?<![a-z0-9_.])" + re.escape(phrase) + r"(?![a-z0-9_.])", query))
    return phrase in query


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
    """Rank explicit topics before lexical matches, with family as a tie-break."""
    family = skill_family(skill)
    query = text.casefold()
    terms = set(WORD.findall(query)) - BACKGROUND_WORDS
    scored: list[tuple[int, int, bool, str, TechnicalKnowledgeEntry]] = []
    for entry in entries:
        topics = sum(
            _phrase_match(phrase, query) for phrase in TOPIC_ALIASES.get(entry.knowledge_id, ())
        )
        haystack = f"{entry.title} {entry.summary} {' '.join(entry.tags or [])}".casefold()
        words = terms.intersection(WORD.findall(haystack))
        tags = {tag.casefold() for tag in entry.tags or []} - BACKGROUND_WORDS
        lexical = len(words | {tag for tag in tags if _phrase_match(tag, query)})
        if topics or lexical:
            scored.append(
                (-topics, -lexical, entry_family(entry) != family, entry.knowledge_id, entry)
            )
    scored.sort(key=lambda item: item[:4])
    explicit = [item for item in scored if item[0] < 0]
    return [item[-1] for item in (explicit or scored)[:limit]]


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
        values = {key: value for key, value in item.items() if key != "knowledge_id"}
        values["content_hash"] = digest
        if row is None:
            session.add(TechnicalKnowledgeEntry(knowledge_id=item["knowledge_id"], **values))
            changed += 1
        elif any(getattr(row, key) != value for key, value in values.items()):
            for key, value in values.items():
                setattr(row, key, value)
            changed += 1
    return changed
