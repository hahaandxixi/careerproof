"""补充探针：09fb4e82f3 来源可见时契约是否仍接受共用账号矛盾。

用 match_candidate 的 semantic_candidates 参数（生产 semantic_retrieval.py:169 的
真实输出形状 semantic_document_candidate）把 group_report.md 的共用账号行注入
上下文，再走真实 build_evidence_contexts + validate_grounded_analysis。
"""
from __future__ import annotations

import json
import sys
import uuid
from dataclasses import replace
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from probe import (  # noqa: E402
    EXPLANATION,
    GAP,
    SUMMARY,
    SUGGESTION,
    build_analysis,
    guard_breakdown,
    case_to_plan,
)
from app.agents.contracts import EvidenceAnalysis, AIRequirementAnalysis, ModelUsage  # noqa: E402
from app.agents.evidence_workflow import build_evidence_contexts  # noqa: E402
from app.tools.code_analyzer import CodeEvidence, ProjectFileSnapshot  # noqa: E402
from app.tools.matcher import RequirementInput, SkillClaim, match_candidate  # noqa: E402

INPUT = BACKEND / "evals" / "quality-blind-plan-review-input.json"
case = next(c for c in json.loads(INPUT.read_text(encoding="utf-8"))["cases"]
            if c["id"] == "09fb4e82f3")

req_id = uuid.uuid5(uuid.NAMESPACE_URL, "plan-audit-30/09fb4e82f3")
requirement = RequirementInput(
    id=req_id, title=case["requirement"]["title"],
    skill=case["requirement"]["skill"], weight=case["requirement"]["weight"],
)
claims = [SkillClaim(skill=case["requirement"]["skill"], claim_text=case["resume"])]
files = [ProjectFileSnapshot(path=f["path"], content=f["content"])
         for f in case["personalFiles"]]

# semantic_retrieval.py:169 同形状：文档行级候选，evidence_type=semantic_document_candidate
report = files[0]
lines = report.content.splitlines()
shared_line_number = next(
    i for i, line in enumerate(lines, 1) if "共用账号" in line
)
candidate = CodeEvidence(
    skill="Python",
    evidence_type="semantic_document_candidate",
    file_path=report.path,
    line_start=shared_line_number,
    line_end=shared_line_number,
    snippet=lines[shared_line_number - 1].strip()[:240],
    strength="low",
    explanation="文档包含具体评价要素，仅证明材料有相关内容；执行效果和作者贡献需人工核查。",
    content_hash="probe",
)

result = match_candidate([requirement], claims, files,
                         semantic_candidates={req_id: [candidate]})
item = result.items[0]
contexts = build_evidence_contexts(result)
context = contexts[0]

out = {
    "verdict": item.verdict,
    "context_evidence": [
        {"evidence_type": e.evidence_type, "provenance": e.provenance,
         "file_path": e.file_path, "line_start": e.line_start, "snippet": e.snippet}
        for e in context.evidence
    ],
    "rating_ceiling": context.rating_ceiling,
}
analysis = build_analysis(context, case["draft"])
try:
    from app.agents.contracts import validate_grounded_analysis
    validate_grounded_analysis(contexts, analysis)
    out["validate"] = {"accepted": True, "error": None}
except Exception as exc:  # noqa: BLE001
    out["validate"] = {"accepted": False, "error": f"{type(exc).__name__}: {exc}"}
out["guards"] = guard_breakdown(context, case_to_plan(case["draft"]))
print(json.dumps(out, ensure_ascii=False, indent=2))
