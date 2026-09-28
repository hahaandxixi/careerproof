"""Offline cross-role coverage audit; no model calls or execution of samples."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.tools.code_analyzer import ProjectFileSnapshot, canonical_skill
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".md").exists():
        parser.error("Use a new output path; preserve earlier evaluations")
    demo = Path(__file__).resolve().parents[2] / "demo"
    jobs = json.loads((demo / "jobs.json").read_text("utf-8"))
    samples = [
        (
            "backend",
            (demo / "student-resume.txt").read_text("utf-8"),
            [
                ProjectFileSnapshot(p.name, p.read_text("utf-8"))
                for p in sorted((demo / "evidence-api").iterdir())
                if p.is_file()
            ],
        )
    ]
    for folder in sorted((demo / "roles").iterdir()):
        if not folder.is_dir():
            continue
        samples.append(
            (
                folder.name,
                (folder / "resume.txt").read_text("utf-8"),
                (
                    [
                        ProjectFileSnapshot(
                            str(p.relative_to(folder / "project")).replace("\\", "/"),
                            p.read_text("utf-8"),
                        )
                        for p in sorted((folder / "project").rglob("*"))
                        if p.is_file()
                    ]
                    if (folder / "project").exists()
                    else [
                        ProjectFileSnapshot(
                            "project.txt", (folder / "project.txt").read_text("utf-8")
                        )
                    ]
                ),
            )
        )
    coverage = []
    rows = []
    for job in jobs:
        supported = [r["skillName"] for r in job["requirements"] if canonical_skill(r["skillName"])]
        unsupported = [
            r["skillName"] for r in job["requirements"] if not canonical_skill(r["skillName"])
        ]
        coverage.append(dict(job=job["title"], supported=supported, unsupported=unsupported))
        requirements = [
            RequirementInput(
                uuid5(NAMESPACE_URL, job["title"] + r["skillName"]),
                r["rawText"],
                r["skillName"],
                r["weight"],
            )
            for r in job["requirements"]
        ]
        for name, resume, files in samples:
            result = enrich_evidence(
                match_candidate(requirements, parse_resume(resume), files), files
            )
            exact = all(
                e.snippet
                == "\n".join(
                    next(f.content for f in files if f.path == e.file_path).splitlines()[
                        e.line_start - 1 : e.line_end
                    ]
                )
                for item in result.items
                for e in item.evidence_list
            )
            rows.append(
                dict(
                    sample=name,
                    job=job["title"],
                    score=result.overall_score,
                    citationSourceExact=exact,
                    items=[asdict(i) for i in result.items],
                )
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            dict(
                scope="Offline rules only; not browser, model, or human semantic acceptance",
                coverage=coverage,
                results=rows,
            ),
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        "utf-8",
    )
    lines = [
        "# 九岗位规则覆盖与交叉匹配",
        "",
        "固定九份材料 × 九个岗位，仅运行规则。分数不是职业适合度，不能跨覆盖范围排名。",
        "TXT 中代码片段不按代码工程识别；无引用时原文一致检查不构成语义证据。",
        "",
        "| 岗位 | 可评估项 | 不支持项 |",
        "| --- | --- | --- |",
    ]
    for c in coverage:
        lines.append(
            f"| {c['job']} | {len(c['supported'])}/5 | {', '.join(c['unsupported']) or '无'} |"
        )
    lines += [
        "",
        "## 材料支持度矩阵",
        "",
        "| 样例 | " + " | ".join(j["title"].replace("（合成演示）", "") for j in jobs) + " |",
        "| --- | " + " | ".join("---" for _ in jobs) + " |",
    ]
    for name, _, _ in samples:
        values = [
            next(r["score"] for r in rows if r["sample"] == name and r["job"] == j["title"])
            for j in jobs
        ]
        lines.append(
            "| "
            + name
            + " | "
            + " | ".join("不评分" if v is None else str(v) for v in values)
            + " |"
        )
    args.output.with_suffix(".md").write_text("\n".join(lines) + "\n", "utf-8")
    print(
        json.dumps(
            dict(
                pairs=len(rows),
                sourceChecksPassed=all(r["citationSourceExact"] for r in rows),
                coverage=[len(c["supported"]) for c in coverage],
            )
        )
    )


if __name__ == "__main__":
    main()
