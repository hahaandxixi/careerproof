# -*- coding: utf-8 -*-
"""E2E-03-PROTOCOL offline probes: compare_views semantics for the
requirement-change contract (docs/task-cards/20261005-E2E-requirement-change-design.md).

In-memory synthetic objects only. No database, no browser, no build, no
service, no network, no real model. Run from backend/ with the project venv.

Exit 0 = all contract guarantees reproduced as expected; 1 = mismatch.
"""
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

sys.stdout.reconfigure(encoding="utf-8")

from app.core.exceptions import AppError
from app.schemas.analysis import MatchCreate, ReportMaterial
from app.services.report_comparison import compare_views

ROWS = []


def record(pid, desc, expected, actual, ok):
    ROWS.append(ok)
    print(f"[{'MATCH' if ok else 'COUNTEREXAMPLE'}] {pid}: {desc}")
    print(f"  预期: {expected}")
    print(f"  实际: {actual}")
    print()


def make_report(job_id, candidate_id="student-1", job_title="原岗位", items=(), materials=None):
    return SimpleNamespace(
        id=uuid4(),
        job_id=job_id,
        job_title=job_title,
        job_category="dev",
        candidate_id=candidate_id,
        candidate_name="学生",
        overall_score=70.0,
        summary="s",
        analysis_mode="rules",
        ai_model=None,
        ai_fallback_used=False,
        evidence_context_version="v1",
        created_at=datetime.now(timezone.utc),
        materials=materials or [],
        items=list(items),
    )


def make_item(req_id, title, level=2):
    return SimpleNamespace(
        requirement_id=req_id,
        requirement_title=title,
        evidence_list=[],
        evidence_level=level,
        ai_status="none",
        confirmation_status="pending",
        reviewer_note=None,
        formula_version="f1",
        evidence_level_version="e1",
    )


def make_materials(version):
    return [ReportMaterial(
        kind="resume", id=uuid4(), title="简历", version_number=version,
        content_hash="hash-old",
    )]


JOB_A, JOB_B = uuid4(), uuid4()
REQ_A1, REQ_A2, REQ_B1 = uuid4(), uuid4(), uuid4()
BASE_SNAP = {"requirements": [
    {"id": str(REQ_A1), "title": "原岗位要求：SQL 统计", "skill": "SQL"},
    {"id": str(REQ_A2), "title": "原岗位要求：缓存读写", "skill": "Redis"},
]}
TARGET_SNAP = {"requirements": [
    {"id": str(REQ_B1), "title": "新岗位要求：订单查询", "skill": "SQL"},
]}

SAME_MATERIALS = make_materials(1)  # 同一版本实例：同 id 同 hash，即真实“材料相同”
base = make_report(JOB_A, items=[make_item(REQ_A1, "SQL 统计"), make_item(REQ_A2, "缓存读写")],
                   materials=SAME_MATERIALS)

# ---- 1. 默认跨岗位比较仍拒绝（allow_job_change 缺省 False） ----------------
try:
    compare_views(base, make_report(JOB_B, materials=SAME_MATERIALS),
                  BASE_SNAP, TARGET_SNAP)
    record("P1", "默认 compare_views 不同岗位", "AppError 4097 拒绝", "未拒绝", False)
except AppError as error:
    record("P1", "默认 compare_views 不同岗位", "AppError 4097 拒绝",
           f"AppError code={error.code}: {error}", error.code == 4097)

# ---- 2. 同一 candidate 校验始终保留（跨岗位许可也不放开） ------------------
try:
    compare_views(base, make_report(JOB_A, candidate_id="student-2",
                                    materials=make_materials(1)),
                  BASE_SNAP, TARGET_SNAP, allow_job_change=True)
    record("P2", "allow_job_change=True 下不同 candidate", "AppError 4097 拒绝", "未拒绝", False)
except AppError as error:
    record("P2", "allow_job_change=True 下不同 candidate", "AppError 4097 拒绝",
           f"AppError code={error.code}: {error}", error.code == 4097)

# ---- 3. 跨岗位许可放行且要求按 identity 分别新增/移除，不按技能合并 --------
result = compare_views(base, make_report(JOB_B, job_title="新岗位",
                                         items=[make_item(REQ_B1, "订单查询", level=3)],
                                         materials=SAME_MATERIALS),
                       BASE_SNAP, TARGET_SNAP, allow_job_change=True)
merged = [i for i in result.items if i.status == "existing"]
added = [i for i in result.items if i.status == "added"]
removed = [i for i in result.items if i.status == "removed"]
sql_pair = [i for i in result.items if i.title == "订单查询" and i.status == "existing"]
record("P3", "跨岗位放行：items 按 requirementId 新增/移除",
       "SQL 技能相似但 requirementId 不同 → 0 existing（不合并），1 added + 2 removed",
       f"existing={len(merged)} added={len(added)} removed={len(removed)} 同技能误合并={len(sql_pair)}",
       len(merged) == 0 and len(added) == 1 and len(removed) == 2)
record("P3b", "context_changes 含 job 与 requirements",
       "['job', 'materials' 缺席（同材料）, 'requirements']",
       f"{result.context_changes}",
       result.context_changes == ["job", "requirements"])
record("P3c", "报告携带 base/target 岗位身份",
       "base_job_id=JOB_A, target_job_id=JOB_B, titles 分别为 原/新 岗位",
       f"base={result.base_job_id == JOB_A} target={result.target_job_id == JOB_B} "
       f"titles={result.base_job_title}/{result.target_job_title}",
       result.base_job_id == JOB_A and result.target_job_id == JOB_B
       and result.base_job_title == "原岗位" and result.target_job_title == "新岗位")
record("P3d", "同一材料（同版本id+hash）不标 materials 变化",
       "materials 不在 context_changes", f"{result.context_changes}",
       "materials" not in result.context_changes)

# ---- 3e. attach 与 compare 的材料键定义差异（设计备注用） ------------------
new_version_materials = [ReportMaterial(
    kind="resume", id=uuid4(), title="简历", version_number=2, content_hash="hash-old",
)]
result2 = compare_views(base, make_report(JOB_B, job_title="新岗位",
                                          items=[make_item(REQ_B1, "订单查询", level=3)],
                                          materials=new_version_materials),
                        BASE_SNAP, TARGET_SNAP, allow_job_change=True)
record("P3e", "同内容新版本（attach 视为未变材料，compare 计入材料版本变化）",
       "compare 的 context 含 materials（版本id不同）——两处 material_key 定义不一致，非缺陷，供展示层裁决",
       f"{result2.context_changes}",
       "materials" in result2.context_changes)

# ---- 4. growth 限制语索引耦合现状 ------------------------------------------
record("P4", "limitations[3] 当前内容（growth view 按 [3] 覆写复核状态语）",
       "仍为复核状态说明行（索引耦合今天成立，属脆弱设计）",
       f"{result.limitations[3]}",
       result.limitations[3].startswith("复核状态"))

# ---- 5. MatchCreate 序列化键名为 jobId（growth view 的 input_snapshot 校验）--
dumped = MatchCreate(
    job_id=JOB_B, resume_version_id=uuid4(), project_version_ids=[uuid4()],
    external_ai_consent=False, use_previous_report=False,
).model_dump(mode="json", by_alias=True)
record("P5", "MatchCreate by_alias 序列化键", "包含 jobId（与 evidence_growth.view L250 的 get('jobId') 一致）",
       f"keys={sorted(dumped)}",
       "jobId" in dumped and "job_id" not in dumped)

# ---- 6. 自我比较拒绝 ------------------------------------------------------
try:
    compare_views(base, base, BASE_SNAP, BASE_SNAP, allow_job_change=True)
    record("P6", "base==target 自我比较", "AppError 4097 拒绝", "未拒绝", False)
except AppError as error:
    record("P6", "base==target 自我比较", "AppError 4097 拒绝",
           f"AppError code={error.code}: {error}", error.code == 4097)

print("=" * 72)
fails = ROWS.count(False)
print(f"探针 {len(ROWS)} 项，符合 {len(ROWS) - fails}，不符合 {fails}")
sys.exit(1 if fails else 0)
