"""Regression checks over recorded synthetic output; no external API use."""

import copy
import json
from pathlib import Path

import pytest

from app.schemas.analysis import CareerPlanAnalysis, JobRecommendationView
from app.services.career_planning import validate_plan
from app.services.job_drafting import validate_draft


def recorded():
    path = Path(__file__).parents[2] / "evals/two-sided-actions-20260926-130159.json"
    return json.loads(path.read_text("utf-8"))["records"]


def student_case():
    record = recorded()[1]
    source = record["input"]["jobs"][0]
    job = JobRecommendationView(
        job_id=source["jobId"], job_title=source["title"], company_name="合成企业",
        category="software", city="广州", employment_type="internship", priority="medium",
        assessed_count=1, requirement_count=1, supported_count=1, claimed_count=0,
        evidence=[{"citation_id": "R1-E1", "skill": "Python", "file_path": "app.py",
                   "line_start": 1, "line_end": 2, "strength": "medium",
                   "explanation": "可见函数"}],
    )
    return copy.deepcopy(record["output"]), job


def test_recorded_action_plan_and_verification_guidance():
    enterprise = recorded()[0]
    draft = validate_draft(enterprise["output"], enterprise["input"]["description"],
                           enterprise["model"], None)
    assert all(row.evidence_request and row.verification_question and row.weight_reason
               for row in draft.requirements)
    raw, job = student_case()
    plan = CareerPlanAnalysis.model_validate(raw)
    validate_plan(plan, [job])
    assert plan.advice[0].task_plan.acceptance_checks


@pytest.mark.parametrize("field", ["steps", "acceptanceChecks"])
def test_action_plan_rejects_empty_or_unbounded_checklists(field):
    raw, _job = student_case()
    for invalid in ([], ["步骤"] * 5):
        raw["advice"][0]["taskPlan"][field] = invalid
        with pytest.raises(ValueError):
            CareerPlanAnalysis.model_validate(raw)


def test_action_plan_cannot_smuggle_unknown_citation():
    raw, job = student_case()
    raw["advice"][0]["citationIds"] = ["R9-E9"]
    with pytest.raises(ValueError, match="unknown or cross-job"):
        validate_plan(CareerPlanAnalysis.model_validate(raw), [job])


def test_action_plan_rejects_blank_task_step():
    raw, job = student_case()
    raw["advice"][0]["taskPlan"]["steps"] = [" "]
    with pytest.raises(ValueError, match="empty or oversized"):
        validate_plan(CareerPlanAnalysis.model_validate(raw), [job])
