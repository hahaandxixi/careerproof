from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkillClaim:
    skill: str
    claim_text: str


SKILL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "SQL": ("sql", "数据库设计"),
    "活动策划": ("活动策划", "运营策划"),
    "用户调研": ("用户调研", "用户研究"),
    "内容运营": ("内容运营",),
    "MySQL": ("mysql",),
    "Redis": ("redis", "缓存"),
    "Java": ("java",),
    "Spring Boot": ("spring boot", "springboot", "spring"),
    "React": ("react",),
    "Vue": ("vue",),
    "TypeScript": ("typescript", "ts"),
    "Node.js": ("node.js", "node"),
    "Python": ("python",),
    "FastAPI": ("fastapi", "fast api"),
    "PostgreSQL": ("postgresql", "postgres"),
    "pytest": ("pytest", "py.test"),
    "REST API": ("rest", "restful", "api", "接口"),
    "Docker": ("docker", "容器化"),
    "Git": ("git", "版本控制"),
    "Linux": ("linux",),
}

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
NEGATION_PATTERN = re.compile(
    r"(?:(?:没有|暂无|无|未|不)(?:实际)?(?:使用|接触|学习|掌握|了解|熟悉)?过?|no|without)\s*$",
    re.I,
)


def mask_resume_text(text: str) -> str:
    masked = EMAIL_PATTERN.sub("[邮箱已脱敏]", text)
    return PHONE_PATTERN.sub("[手机号已脱敏]", masked)


def _sentence_for(text: str, position: int) -> str:
    start_candidates = [text.rfind(mark, 0, position) for mark in ("。", "！", "？", "\n")]
    start = max(start_candidates) + 1
    end_candidates = [
        boundary
        for mark in ("。", "！", "？", "\n")
        if (boundary := text.find(mark, position)) >= 0
    ]
    end = min(end_candidates) + 1 if end_candidates else len(text)
    return text[start:end].strip()[:500]


def parse_resume(text: str) -> list[SkillClaim]:
    lower = text.lower()
    claims: list[SkillClaim] = []
    for skill, keywords in SKILL_KEYWORDS.items():
        positions = []
        for keyword in keywords:
            pattern = re.escape(keyword.lower())
            if keyword.isascii():
                pattern = rf"(?<![a-z0-9]){pattern}(?![a-z0-9])"
            match = next(
                (
                    candidate
                    for candidate in re.finditer(pattern, lower)
                    if not NEGATION_PATTERN.search(
                        lower[max(0, candidate.start() - 12) : candidate.start()]
                    )
                ),
                None,
            )
            positions.append(match.start() if match else -1)
        valid_positions = [position for position in positions if position >= 0]
        if valid_positions:
            position = min(valid_positions)
            claims.append(SkillClaim(skill=skill, claim_text=_sentence_for(text, position)))
    return claims
