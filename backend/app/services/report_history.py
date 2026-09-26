"""Read bounded, owner-scoped historical context, never current evidence."""

import re
from uuid import UUID

from sqlalchemy import select

from app.models.analysis import AnalysisTask, MatchItem, MatchReport


def _owner_history_query(owner_id, job_id):
    return select(MatchReport).join(
        AnalysisTask, AnalysisTask.id == MatchReport.analysis_task_id
    ).where(
        AnalysisTask.created_by == owner_id,
        MatchReport.job_id == UUID(str(job_id)),
        MatchReport.candidate_ref == str(owner_id),
    )


async def select_history_report_id(session, owner_id, job_id):
    report = await session.scalar(_owner_history_query(owner_id, job_id)
                                  .order_by(MatchReport.created_at.desc(), MatchReport.id.desc())
                                  .limit(1))
    return str(report.id) if report else None


async def prepare_history_tool(session, task, current_requirements):
    query = _owner_history_query(task.created_by, task.input_snapshot["jobId"]).where(
        MatchReport.created_at < task.created_at)
    # New tasks freeze the source when submitted; old snapshots retain bounded lookup.
    if "previousReportId" in task.input_snapshot:
        previous_id = task.input_snapshot["previousReportId"]
        if previous_id is None:
            return None
        query = query.where(MatchReport.id == UUID(previous_id))
    report = await session.scalar(query.order_by(MatchReport.created_at.desc(),
                                                MatchReport.id.desc()).limit(1))
    if report is None:
        return None
    old_requirements = {
        str(r["id"]): r for r in (report.job_snapshot or {}).get("requirements", [])
    }
    current = {str(r["id"]): r for r in current_requirements}
    previous_materials = [
        {key: material.get(key) for key in ("kind", "id", "versionNumber", "contentHash")}
        for material in (report.materials_snapshot or [])[:11]
    ]

    def historical_text(text, limit):
        return re.sub(r"R\d+-E\d+", "[历史引用]", text or "")[:limit]

    async def read(requirement_id):
        if requirement_id not in current:
            raise ValueError("History tool targeted an unknown current requirement")
        row = await session.scalar(select(MatchItem).where(
            MatchItem.report_id == report.id, MatchItem.requirement_id == UUID(requirement_id),
        ))
        snapshot = (row.evidence_snapshot or {}) if row else {}
        ai = snapshot.get("ai") or {}
        # Historical citation IDs are deliberately excluded, including rating criteria.
        return {
            "scope": "same-owner-same-job-before-current-task",
            "historicalOnly": True,
            "previousReportId": str(report.id),
            "previousCreatedAt": report.created_at.isoformat(),
            "requirementId": requirement_id,
            "requirementChanged": old_requirements.get(requirement_id) != current[requirement_id],
            "previousRequirement": old_requirements.get(requirement_id),
            "previousExplanation": historical_text(
                ai.get("explanation") or (row.explanation if row else ""), 400
            ),
            "previousGap": historical_text(ai.get("informationGap"), 250),
            "previousSuggestion": historical_text(ai.get("suggestion"), 250),
            "savedAiLevel": (ai.get("rating") or {}).get("level"),
            "previousAiStatus": ai.get("status"),
            "formulaVersion": row.formula_version if row else None,
            "retrievalVersion": (report.analysis_metadata or {}).get("evidenceContextVersion"),
            "previousMaterials": previous_materials,
            "previousEvidence": [
                {"historicalReference": f"history-{index}",
                 "file": evidence.get("filePath", evidence.get("file_path", "")),
                 "snippet": evidence.get("snippet", "")[:180]}
                for index, evidence in enumerate(snapshot.get("evidenceList", [])[:2], 1)
            ],
            "boundary": "历史判断可能错误；旧片段不是本轮引用，不能支持当前评级或证明提升。",
        }

    read.planning_hint = {
        "requirementsChanged": any(old_requirements.get(key) != value
                                   for key, value in current.items()),
        "historicalOnly": True,
        "materialsChanged": ((report.materials_snapshot or [])
                             != task.input_snapshot.get("materials", [])),
    }
    return read
