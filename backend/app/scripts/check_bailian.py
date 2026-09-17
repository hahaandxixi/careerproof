"""Make one synthetic Bailian request without printing credentials or model output."""

import asyncio

from app.agents.contracts import (
    EvidenceCandidate,
    RequirementEvidenceContext,
    validate_grounded_analysis,
)
from app.agents.provider import BailianProvider
from app.core.config import settings


async def main() -> None:
    if settings.dashscope_api_key is None:
        raise SystemExit("Bailian check failed: DASHSCOPE_API_KEY is not configured")
    provider = BailianProvider(
        api_key=settings.dashscope_api_key.get_secret_value(),
        base_url=settings.bailian_base_url,
        model=settings.bailian_model,
        timeout_seconds=settings.bailian_timeout_seconds,
    )
    contexts = [
        RequirementEvidenceContext(
            requirement_id="synthetic-fastapi",
            requirement_title="有 FastAPI 接口开发实践",
            skill="FastAPI",
            verdict="supported",
            rule_score=0.65,
            claimed=True,
            evidence=[
                EvidenceCandidate(
                    citation_id="R1-E1",
                    file_path="synthetic/app.py",
                    line_start=3,
                    line_end=4,
                    evidence_type="fastapi_route",
                    strength="high",
                    snippet='@app.get("/health")\ndef health(): return {"ok": True}',
                )
            ],
        ),
        RequirementEvidenceContext(
            requirement_id="synthetic-redis",
            requirement_title="实现 Redis 缓存读写",
            skill="Redis",
            verdict="gap",
            rule_score=0,
            claimed=False,
            evidence=[],
        ),
    ]
    result = await provider.analyze_evidence(
        contexts=contexts,
    )
    validate_grounded_analysis(contexts, result)
    print(
        "Bailian connectivity OK; "
        f"model={result.model}; requirements={len(result.items)}; "
        f"citations={sum(len(item.citation_ids) for item in result.items)}; "
        f"inputTokens={result.usage.input_tokens}; outputTokens={result.usage.output_tokens}; "
        f"latencyMs={result.usage.latency_ms}"
    )


if __name__ == "__main__":
    asyncio.run(main())
