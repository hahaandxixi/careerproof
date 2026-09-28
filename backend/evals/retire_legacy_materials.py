"""Opt-in local archival of known synthetic fixtures; never delete files or reports."""

import argparse
import asyncio
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.analysis import MatchReport
from app.models.audit import AuditLog
from app.models.portfolio import Project, ProjectVersion, Resume, ResumeVersion

ROOT = Path(__file__).resolve().parents[2]
RESUME_PATTERN = re.compile(
    r"^(?:历史难例合成简历$|历史验收简历 \d{8}|历史完整报告.*合成简历|"
    r"(?:数据库工程师 DBA|自动化运维工程师)验收简历\d{4}$|"
    r"Function Calling 合成简历 ?\d{8}|AI完整报告合成简历 ?\d{8}|"
    r"浏览器(?:全链路|完整链路)(?:合成)?简历[- ]?\d{8}|"
    r"OCR合成烟测[- ]?\d{8}|开源归属回归[:：])"
)
PROJECT_PATTERN = re.compile(
    r"^(?:历史验收项目 \d{8}|视觉(?:与代码组合)?合成验收 \d{8}|"
    r"Function Calling 合成项目 ?\d{8}|AI完整报告合成项目 ?\d{8}|"
    r"浏览器(?:全链路|完整链路)(?:合成)?项目[- ]?\d{8}|"
    r"历史完整报告 |合成视觉并发 |开源归属回归[:：])"
)
KNOWN_FILES = {
    "synthetic-resume.txt",
    "synthetic-history.zip",
    "synthetic-concurrency.png",
    "synthetic-vision-panel.png",
    "evidence-function-call.zip",
    "resume-ui.txt",
    "project-ui.zip",
    "resume.txt",
    "student-resume.txt",
    "project.zip",
    "flask-qa.txt",
    "ocr-smoke-20260917.png",
}


def is_legacy(kind, title, filenames):
    if not filenames or title.startswith("CP"):
        return False
    pattern = RESUME_PATTERN if kind == "resume" else PROJECT_PATTERN
    return bool(pattern.match(title)) and all(
        name in KNOWN_FILES or (name or "").startswith("ocr-smoke-") for name in filenames
    )


def report_digest(reports):
    frozen = [
        {
            "id": str(r.id),
            "job": r.job_snapshot,
            "materials": r.materials_snapshot,
            "metadata": r.analysis_metadata,
            "summary": r.summary,
        }
        for r in reports
    ]
    return hashlib.sha256(
        json.dumps(frozen, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


async def run(apply):
    async with async_session_factory() as session:
        report_rows = list(await session.scalars(select(MatchReport).order_by(MatchReport.id)))
        before = report_digest(report_rows)
        targets = []
        for kind, model, version_model, fk, title_key in (
            ("resume", Resume, ResumeVersion, ResumeVersion.resume_id, "title"),
            ("project", Project, ProjectVersion, ProjectVersion.project_id, "name"),
        ):
            for item in await session.scalars(
                select(model).where(model.is_archived.is_(False)).with_for_update()
            ):
                filenames = list(
                    await session.scalars(
                        select(version_model.original_filename).where(fk == item.id)
                    )
                )
                if is_legacy(kind, getattr(item, title_key), filenames):
                    targets.append({"kind": kind, "id": str(item.id)})
                    if apply:
                        item.is_archived = True
                        item.version += 1
                        session.add(
                            AuditLog(
                                actor_id=None,
                                action="material.archive",
                                resource_type=kind,
                                resource_id=str(item.id),
                                details={
                                    "reason": "known-synthetic-fixture-retirement-v1",
                                    "recoverable": True,
                                },
                            )
                        )
        if report_digest(report_rows) != before:
            raise RuntimeError("Report snapshots changed; abort archival")
        if apply:
            await session.commit()
        else:
            await session.rollback()
        after = report_digest(
            list(await session.scalars(select(MatchReport).order_by(MatchReport.id)))
        )
        result = {
            "applied": apply,
            "targets": targets,
            "reportCount": len(report_rows),
            "reportsUnchanged": before == after,
            "modelCalls": 0,
            "filesDeleted": 0,
        }
        path = (
            ROOT
            / "backend/.tmp"
            / f"legacy-material-archive-{datetime.now():%Y%m%d-%H%M%S-%f}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
        print(
            json.dumps(
                {
                    "applied": apply,
                    "archivedCount": len(targets),
                    "reportsUnchanged": before == after,
                    "output": path.name,
                    "modelCalls": 0,
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args().apply))
