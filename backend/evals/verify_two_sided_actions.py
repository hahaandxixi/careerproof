"""Two bounded real-model calls on synthetic job and portfolio data; opt in with --live."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.agents.provider import get_ai_provider
from app.schemas.analysis import CareerPlanAnalysis, JobRecommendationView
from app.services.career_planning import PLAN_PROMPT, _planning_input, validate_plan
from app.services.job_drafting import DRAFT_PROMPT, validate_draft


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    description = ("后端实习岗位：要求使用 Python 和 FastAPI 实现数据查询接口，"
                   "提供异常处理与接口测试；熟悉 SQL 查询优先。")
    source = "def get_item(item_id):\n    return {'id': item_id}\n"
    job = JobRecommendationView(
        job_id=uuid5(NAMESPACE_URL, "careerproof-actions-eval"),
        job_title="后端实习生", company_name="合成演示企业", category="software",
        city="广州", employment_type="internship", priority="medium", assessed_count=1,
        requirement_count=1, supported_count=1, claimed_count=0,
        gaps=["未展示异常处理与接口断言"],
        requirements=[{"text": "使用 Python 实现接口及异常处理与测试", "skill": "Python",
                       "weight": 5, "is_required": True, "rule_verdict": "supported"}],
        evidence=[{"citation_id": "R1-E1", "skill": "Python", "file_path": "app.py",
                   "line_start": 1, "line_end": 2, "strength": "medium",
                   "explanation": "仅可见返回数据的函数", "snippet": source.rstrip()}],
    )
    if not args.live:
        print("Synthetic employer draft and student action plan; --live makes two model calls.")
        return 0
    records = []
    for side, prompt, data in (
        ("enterprise", DRAFT_PROMPT, {"description": description}),
        ("student", PLAN_PROMPT, _planning_input([job], [])),
    ):
        provider = get_ai_provider()
        record = {"side": side, "input": data, "model": provider.model}
        try:
            async with asyncio.timeout(90):
                raw = await provider.generate_bounded_json(
                    system=prompt, data=data, max_tokens=1600,
                )
            record["output"] = raw
            if side == "enterprise":
                result = validate_draft(raw, description, provider.model, None)
                assert all(r.evidence_request and r.verification_question and r.weight_reason
                           for r in result.requirements), "Missing verification guidance"
            else:
                result = CareerPlanAnalysis.model_validate(raw)
                validate_plan(result, [job])
                assert all(r.task_plan for r in result.advice), "Missing action plan"
            record["validation"] = "passed"
        except Exception as exc:
            record["validation"] = "failed"
            record["errorType"] = type(exc).__name__
        usage = provider.combined_usage()
        record["usage"] = usage.model_dump() if usage else None
        records.append(record)
    path = Path(__file__).parent / f"two-sided-actions-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps({"generatedAt": datetime.now(UTC).isoformat(),
                               "scope": "Synthetic service-level checks, not browser or DB",
                               "humanSemanticReview": "pending", "billingVerified": False,
                               "records": records}, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"output": str(path), "checks": [
        {"side": r["side"], "validation": r["validation"], "usage": r["usage"]}
        for r in records]}, ensure_ascii=False))
    return 0 if all(r["validation"] == "passed" for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
