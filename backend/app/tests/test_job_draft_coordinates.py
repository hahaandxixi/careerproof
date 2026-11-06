import pytest
from pydantic import ValidationError

from app.schemas.jobs import JobDraftRequest, JobRequirementCreate
from app.services.job_drafting import validate_draft

PROSE = "负责开发企业业务接口并编写测试，能够使用Python分析数据和维护服务。"
QUOTE = "能够使用Python分析数据和维护服务"


@pytest.mark.parametrize("prefix,quote", [("  ", QUOTE), ("🚀", QUOTE),
                                           ("", QUOTE.replace("Python", "🚀Python"))])
def test_response_binds_quotes_to_canonical_codepoint_text(prefix, quote):
    text = PROSE.replace(QUOTE, quote)
    request = JobDraftRequest(description=prefix + text + " \n")
    result = validate_draft({"requirements": [{"raw_text": quote, "skill_name": "Python",
        "weight": 3, "is_required": True, "source_quote": quote}]},
        request.description, "synthetic", None)
    body = result.model_dump(by_alias=True)
    assert body["normalizedDescription"] == request.description
    item = body["requirements"][0]
    assert request.description[item["sourceStart"]:item["sourceEnd"]] == quote


@pytest.mark.parametrize("bad", [-1, 0.5, True, "1"])
def test_source_offset_is_a_strict_nonnegative_integer(bad):
    with pytest.raises(ValidationError):
        JobRequirementCreate(raw_text="test", skill_name="Python", source_quote="abc",
                             source_start=bad, source_end=3)


def test_server_retains_bom_canonical_text_through_create_and_update():
    from app.schemas.jobs import JobCreate, JobUpdate
    from app.services.jobs import JobService

    request = JobDraftRequest(description="\ufeff" + PROSE)
    assert request.description.startswith("\ufeff")
    result = validate_draft({"requirements": [{"raw_text": QUOTE, "skill_name": "Python",
        "weight": 3, "is_required": True, "source_quote": QUOTE}]},
        request.description, "synthetic", None)
    rows = [JobRequirementCreate(**result.requirements[0].model_dump())]
    for payload in (
        JobCreate(title="test", company_name="synthetic", description=result.normalized_description,
                  requirements=rows),
        JobUpdate(description=result.normalized_description, requirements=rows),
    ):
        assert payload.description == request.description
        JobService._validate_requirement_sources(payload.description, rows)
