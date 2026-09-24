from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.identity import User
from app.models.recruitment import Job, JobRequirement
from app.schemas.analysis import (
    JobRecommendationRequest,
    JobRecommendationResult,
    JobRecommendationView,
    RecommendationEvidence,
    RecommendationRequirement,
    ReportMaterial,
)
from app.services.matching_materials import analyze_materials, resolve_materials
from app.services.task_runner import run_isolated
from app.tools.matcher import RequirementInput

MAX_RECOMMENDATION_JOBS = 100


async def recommend_jobs(
    session: AsyncSession,
    request: JobRecommendationRequest,
    user: User,
) -> JobRecommendationResult:
    """Rank published jobs from one bounded scan of the student's saved materials."""
    materials = await resolve_materials(session, request, user)
    job_rows = list(
        await session.scalars(
            select(Job)
            .where(Job.status == "published")
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(MAX_RECOMMENDATION_JOBS)
        )
    )
    jobs = []
    seen_jobs: set[tuple[str, str, str, str, str]] = set()
    for job in job_rows:
        identity = (
            job.title.strip().casefold(),
            job.company_name.strip().casefold(),
            job.category,
            job.city.strip().casefold(),
            job.employment_type,
        )
        if identity in seen_jobs:
            continue
        seen_jobs.add(identity)
        jobs.append(job)
    if not jobs:
        return JobRecommendationResult(
            summary="当前没有已发布岗位，暂时无法生成职业推荐。",
            materials=[ReportMaterial.model_validate(item) for item in materials.snapshots],
        )

    requirements = list(
        await session.scalars(
            select(JobRequirement)
            .where(JobRequirement.job_id.in_([job.id for job in jobs]))
            .order_by(JobRequirement.created_at, JobRequirement.id)
        )
    )
    if not requirements:
        return JobRecommendationResult(
            summary="当前已发布岗位尚未填写可分析要求，暂时无法生成职业推荐。",
            materials=[ReportMaterial.model_validate(item) for item in materials.snapshots],
        )

    result = await run_isolated(
        analyze_materials,
        [
            RequirementInput(item.id, item.raw_text, item.skill_name, item.weight)
            for item in requirements
        ],
        materials,
        settings.storage_base_dir,
        False,
    )
    analyzed = {item.requirement_id: item for item in result.items}
    by_job: dict = defaultdict(list)
    for requirement in requirements:
        by_job[requirement.job_id].append(requirement)

    ranked: list[tuple[float, JobRecommendationView]] = []
    for job in jobs:
        job_requirements = by_job.get(job.id, [])
        items = [analyzed[item.id] for item in job_requirements if item.id in analyzed]
        assessed = [item for item in items if item.verdict != "unsupported"]
        supported = [item for item in assessed if item.verdict in {"supported", "partial"}]
        claimed = [item for item in assessed if item.verdict == "claimed_only"]
        total_weight = sum(item.weight for item in assessed)
        evidence_fit = (
            sum(item.rule_base_score * item.weight for item in assessed)
            / (0.65 * total_weight)
            * 100
            if total_weight
            else 0.0
        )
        rule_coverage = len(assessed) / len(items) if items else 0.0
        ranking_score = evidence_fit * (0.75 + 0.25 * rule_coverage)
        priority = (
            "high"
            if ranking_score >= 70 and len(supported) >= 2
            else "medium"
            if ranking_score >= 30 and supported
            else "explore"
        )
        matched_skills = list(dict.fromkeys(item.skill for item in [*supported, *claimed]))[:6]
        gaps = list(
            dict.fromkeys(
                (
                    f"{item.skill}：当前仅见简历声明，缺少可定位项目证据"
                    if item.verdict == "claimed_only" else item.requirement_title
                )
                for item in assessed
                if item.verdict in {"gap", "claimed_only"}
            )
        )[:3]
        evidence = [
            RecommendationEvidence(
                citation_id=f"J{len(ranked) + 1}-E{index}",
                skill=item.skill,
                file_path=item.evidence.file_path,
                line_start=item.evidence.line_start,
                line_end=item.evidence.line_end,
                strength=item.evidence.strength,
                explanation=item.evidence.explanation,
                snippet=item.evidence.snippet[:900],
            )
            for index, item in enumerate(supported, 1)
            if item.evidence is not None
        ][:3]
        ranked.append(
            (
                ranking_score,
                JobRecommendationView(
                    job_id=job.id,
                    job_title=job.title,
                    company_name=job.company_name,
                    category=job.category,
                    city=job.city,
                    employment_type=job.employment_type,
                    priority=priority,
                    assessed_count=len(assessed),
                    requirement_count=len(items),
                    supported_count=len(supported),
                    claimed_count=len(claimed),
                    matched_skills=matched_skills,
                    gaps=gaps,
                    requirements=[
                        RecommendationRequirement(
                            text=requirement.raw_text,
                            skill=requirement.skill_name,
                            weight=requirement.weight,
                            is_required=requirement.is_required,
                            rule_verdict=(
                                analyzed[requirement.id].verdict
                                if requirement.id in analyzed else "not_evaluated"
                            ),
                        )
                        for requirement in sorted(
                            job_requirements,
                            key=lambda requirement: (
                                requirement.is_required, requirement.weight
                            ),
                            reverse=True,
                        )[:12]
                    ],
                    evidence=evidence,
                ),
            )
        )

    priority_order = {"high": 3, "medium": 2, "explore": 1}
    ranked.sort(
        key=lambda entry: (
            priority_order[entry[1].priority],
            entry[0],
            entry[1].supported_count,
            entry[1].claimed_count,
            entry[1].job_title,
        ),
        reverse=True,
    )
    recommendations = [entry[1] for entry in ranked[: request.limit]]
    evidence_jobs = sum(item.supported_count > 0 for item in recommendations)
    summary = (
        f"已用所选材料检索 {len(jobs)} 个已发布岗位；前 {len(recommendations)} 个结果中，"
        f"{evidence_jobs} 个岗位找到了项目证据。推荐顺序只表示当前材料与岗位要求的证据贴合度，"
        "不代表能力认证或录用概率。"
    )
    return JobRecommendationResult(
        primary_direction=recommendations[0].category if recommendations else None,
        summary=summary,
        materials=[ReportMaterial.model_validate(item) for item in materials.snapshots],
        recommendations=recommendations,
    )
