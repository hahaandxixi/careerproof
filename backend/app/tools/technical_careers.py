"""Bounded navigation taxonomy; never a material/ability assessment or persisted category."""

from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import and_, case, exists, func, or_, select

from app.models.recruitment import Job, JobRequirement

TAXONOMY = json.loads(
    (Path(__file__).resolve().parents[1] / "data/technical-careers.json").read_text(
        encoding="utf-8"
    )
)
DIRECTIONS = {entry["id"]: entry for entry in TAXONOMY["directions"]}
LANGUAGES = {entry["id"]: entry for entry in TAXONOMY["languages"]}
# Specific title roles precede generic development roles. Plain software/operations/design
# categories do not certify a technical direction. Ambiguous framework-only jobs stay unknown.
TITLE_PRIORITY = ("product", "testing", "cloud", "ai", "data", "frontend", "backend")


def normalize_filters(direction=None, specialty=None, language=None):
    direction = direction if direction in DIRECTIONS else None
    allowed = {s["id"] for s in DIRECTIONS[direction]["specialties"]} if direction else set()
    return (
        direction,
        specialty if specialty in allowed else None,
        language if language in LANGUAGES else None,
    )


def term_pattern(terms):
    # A portable boundary for SQLite REGEXP and PostgreSQL ~; Java must not hit JavaScript.
    return "|".join(
        (r"(^|[^a-z0-9+#])" + re.escape(term.lower()) + r"([^a-z0-9+#]|$)")
        if term.isascii()
        else re.escape(term.lower())
        for term in terms
    )


def _matches(column, terms):
    return func.lower(column).regexp_match(term_pattern(terms))


def _skill_exists(terms, *, exact=False):
    predicate = (
        func.lower(JobRequirement.skill_name).in_([v.lower() for v in terms])
        if exact
        else _matches(JobRequirement.skill_name, terms)
    )
    return exists(select(1).where(JobRequirement.job_id == Job.id, predicate).correlate(Job))


def direction_expression():
    backend = _skill_exists(DIRECTIONS["backend"]["fallbackSkills"], exact=True)
    frontend = _skill_exists(DIRECTIONS["frontend"]["fallbackSkills"], exact=True)
    return case(
        *[(_matches(Job.title, DIRECTIONS[key]["titleTerms"]), key) for key in TITLE_PRIORITY],
        else_=case(
            (and_(backend, ~frontend), "backend"),
            (and_(frontend, ~backend), "frontend"),
            (Job.category == "data_analysis", "data"),
            else_=None,
        ),
    )


def keyword_condition(query):
    """Search explicit job identity, never incidental collaboration prose."""
    term = query.strip()
    for key, group in DIRECTIONS.items():
        if term.casefold() in {v.casefold() for v in [group["label"], *group["titleTerms"]]}:
            return direction_expression() == key
    return or_(
        _matches(Job.title, [term]),
        Job.company_name.icontains(term, autoescape=True),
        _skill_exists([term]),
    )


def discovery_conditions(direction=None, specialty=None, language=None):
    direction, specialty, language = normalize_filters(direction, specialty, language)
    conditions = []
    if direction:
        conditions.append(direction_expression() == direction)
    if specialty:
        terms = next(
            s["terms"] for s in DIRECTIONS[direction]["specialties"] if s["id"] == specialty
        )
        conditions.append(or_(_matches(Job.title, terms), _skill_exists(terms)))
    if language:
        terms = LANGUAGES[language]["terms"]
        conditions.append(or_(_matches(Job.title, terms), _skill_exists(terms)))
    return conditions


def classify_title(title, category, skills):
    for key in TITLE_PRIORITY:
        if re.search(term_pattern(DIRECTIONS[key]["titleTerms"]), title.lower()):
            return key
    lowered = {s.lower() for s in skills}
    fallback = [
        key
        for key in ("backend", "frontend")
        if lowered.intersection(s.lower() for s in DIRECTIONS[key]["fallbackSkills"])
    ]
    return fallback[0] if len(fallback) == 1 else "data" if category == "data_analysis" else None
