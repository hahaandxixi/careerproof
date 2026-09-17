from __future__ import annotations

from dataclasses import dataclass

from app.agents.provider import AIProvider
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.matcher import MatchResult, RequirementInput, match_candidate
from app.tools.resume_parser import mask_resume_text, parse_resume


@dataclass(frozen=True, slots=True)
class PublicAgentStep:
    step: int
    event_type: str
    name: str
    detail: str
    payload: dict


@dataclass(frozen=True, slots=True)
class MatchAgentOutput:
    result: MatchResult
    steps: list[PublicAgentStep]


class MatchAgent:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def run(
        self,
        *,
        requirements: list[RequirementInput],
        resume_text: str,
        files: list[ProjectFileSnapshot],
        job_title: str,
        candidate_name: str,
    ) -> MatchAgentOutput:
        claims = parse_resume(mask_resume_text(resume_text))
        steps = [
            PublicAgentStep(
                1,
                "tool.completed",
                "解析简历",
                f"识别出{len(claims)}项技能声明",
                {"skills": [claim.skill for claim in claims]},
            ),
            PublicAgentStep(
                2,
                "tool.completed",
                "扫描项目",
                f"静态分析{len(files)}个文本文件，未执行任何用户代码",
                {"fileCount": len(files)},
            ),
        ]
        result = match_candidate(requirements, claims, files)
        steps.append(
            PublicAgentStep(
                3,
                "tool.completed",
                "可追溯匹配",
                f"完成{len(result.items)}项岗位要求匹配",
                {"overallScore": result.overall_score},
            )
        )
        fallback_used = False
        try:
            summary_text = (
                await self.provider.summarize_match(
                    deterministic_summary=result.summary,
                    job_title=job_title,
                    candidate_name=candidate_name,
                )
            ).summary
        except Exception:
            fallback_used = True
            summary_text = result.summary
        result = MatchResult(
            overall_score=result.overall_score,
            items=result.items,
            gaps=result.gaps,
            claimed_only=result.claimed_only,
            summary=summary_text,
        )
        steps.append(
            PublicAgentStep(
                4,
                "task.completed",
                "生成结论",
                summary_text,
                {"provider": self.provider.name, "fallbackUsed": fallback_used},
            )
        )
        return MatchAgentOutput(result=result, steps=steps)
