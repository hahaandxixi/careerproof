from app.tools.resume_parser import parse_resume


def test_demo_resume_recognizes_backend_stack_without_confusing_generic_api() -> None:
    claims = parse_resume(
        "使用 Python 和 FastAPI 开发接口，使用 PostgreSQL 保存数据，并用 pytest 编写测试。"
    )
    by_skill = {claim.skill: claim.claim_text for claim in claims}

    assert {"Python", "FastAPI", "PostgreSQL", "pytest"} <= by_skill.keys()
    assert "FastAPI" in by_skill["FastAPI"]
    assert "PostgreSQL" in by_skill["PostgreSQL"]


def test_resume_parser_ignores_negated_skill_claims() -> None:
    claims = {claim.skill for claim in parse_resume("暂无 Redis 经历，也没有使用过 MySQL。")}
    assert "Redis" not in claims
    assert "MySQL" not in claims
