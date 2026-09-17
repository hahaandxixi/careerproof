from uuid import uuid4

import pytest

from app.agents.match_agent import MatchAgent
from app.tools.matcher import RequirementInput


class FailingProvider:
    name = "failing-test-provider"

    async def summarize_match(self, **_kwargs):
        raise RuntimeError("provider unavailable")


@pytest.mark.asyncio
async def test_rule_result_survives_ai_provider_failure() -> None:
    output = await MatchAgent(FailingProvider()).run(
        requirements=[RequirementInput(uuid4(), "掌握Redis", "Redis", 5)],
        resume_text="熟悉Redis缓存",
        files=[],
        job_title="后端工程师",
        candidate_name="测试学生",
    )

    assert output.result.overall_score == 10
    assert output.result.items[0].verdict == "claimed_only"
    assert output.steps[-1].payload["fallbackUsed"] is True
