"""Source text must not imply verified candidate ability."""

from uuid import uuid4

import pytest

from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.matcher import RequirementInput, match_candidate


def evaluate(skill, title, *files):
    return match_candidate([RequirementInput(uuid4(), title, skill, 5)], [], list(files))


@pytest.mark.parametrize(
    ("skill", "expected_line", "expected_snippet"),
    [
        ("FastAPI", 1, "fastapi==0.116.1"),
        ("PostgreSQL", 3, "psycopg[binary]==3.2.9"),
        ("pytest", 4, "pytest==8.4.2"),
    ],
)
def test_dependency_match_points_to_its_own_line(skill, expected_line, expected_snippet):
    content = "fastapi==0.116.1\npydantic==2.11.7\npsycopg[binary]==3.2.9\npytest==8.4.2\n"
    result = evaluate(skill, f"使用{skill}", ProjectFileSnapshot("requirements.txt", content))
    evidence = result.items[0].evidence
    assert evidence is not None
    assert evidence.line_start == expected_line
    assert evidence.snippet == expected_snippet


def test_pytest_match_skips_leading_blank_lines():
    content = (
        "from fastapi.testclient import TestClient\n\n"
        "client = TestClient(app)\n\n\n"
        "def test_health_endpoint():\n"
        "    response = client.get('/health')\n"
        "    assert response.status_code == 200\n"
    )
    result = evaluate("pytest", "编写 pytest 测试", ProjectFileSnapshot("test_app.py", content))
    evidence = result.items[0].evidence
    assert evidence is not None
    assert evidence.line_start == 6
    assert evidence.snippet == "def test_health_endpoint():"


@pytest.mark.parametrize("skill", ["SQL", "MySQL"])
def test_readme_todo_schema_is_not_implementation(skill):
    result = evaluate(
        skill,
        "数据库开发",
        ProjectFileSnapshot(
            "README.md",
            "TODO: add CREATE TABLE later\nmysql.connector\nSELECT * FROM users;",
        ),
    )
    assert result.overall_score == 0
    assert result.items[0].verdict == "gap"
    assert result.items[0].evidence is None


@pytest.mark.parametrize(
    "content",
    [
        "# import os\n# def plan(): return 1\n",
        '"""\nimport os\ndef example():\n    return 1\n"""\n',
    ],
)
def test_python_comments_and_docstrings_are_not_code(content):
    result = evaluate("Python", "Python开发", ProjectFileSnapshot("main.py", content))
    assert result.overall_score == 0
    assert result.items[0].evidence is None


def test_python_example_inside_assigned_string_is_not_imported_code():
    source = 'example = """\nimport os\ndef demo():\n    return 1\n"""\n'
    result = evaluate("Python", "Python开发", ProjectFileSnapshot("example.py", source))
    assert result.overall_score == 0
    assert result.items[0].evidence is None


@pytest.mark.parametrize(
    "prefix",
    [
        "def stub():\n    pass\n\n",
        'def stub():\n    """A planned function without implementation."""\n\n',
        'example = """\ndef pretend():\n    return 42\n"""\n\n',
        "def stub():\n    import math\n\n",
        "def stub():\n    if True:\n        pass\n\n",
    ],
)
def test_python_evidence_points_to_implemented_function_not_earlier_stub(prefix):
    content = prefix + "def add(a, b):\n    return a + b\n"
    result = evaluate("Python", "Python开发", ProjectFileSnapshot("main.py", content))
    evidence = result.items[0].evidence
    assert evidence is not None
    assert evidence.line_start == len(prefix.splitlines()) + 1
    assert evidence.snippet == "def add(a, b):"


@pytest.mark.parametrize(
    "content",
    [
        "def stub():\n    import math\n",
        "def stub():\n    if True:\n        pass\n",
        "def stub():\n    raise NotImplementedError\n",
        "def stub():\n    return None\n",
    ],
)
def test_python_placeholder_body_is_not_implementation(content):
    result = evaluate("Python", "Python开发", ProjectFileSnapshot("main.py", content))
    assert result.items[0].evidence is None


@pytest.mark.parametrize(
    "skill,path,content",
    [
        ("Python", "requirements.txt", "fastapi==0.116.1"),
        ("Redis", "requirements.txt", "redis==5.0.0"),
        ("Redis", "package.json", '{"dependencies":{"redis":"5.0.0"}}'),
        ("Spring Boot", "pom.xml", "<dependency>spring-boot-starter-web</dependency>"),
    ],
)
def test_dependency_only_stays_low_confidence(skill, path, content):
    result = evaluate(skill, "基础开发", ProjectFileSnapshot(path, content))
    assert result.items[0].verdict == "partial"
    assert result.overall_score <= 15
    assert result.items[0].evidence.strength == "low"


@pytest.mark.parametrize(
    "skill,path,content,evidence_type,expected_score",
    [
        (
            "FastAPI",
            "app.py",
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "@app.get('/health')\n"
            "def health():\n"
            "    return {'status': 'ok'}\n",
            "fastapi_route",
            65,
        ),
        (
            "PostgreSQL",
            "database.py",
            "import psycopg\n\n"
            "def load(connection: psycopg.Connection):\n"
            "    return connection.execute('SELECT 1').fetchone()\n",
            "postgres_usage",
            40,
        ),
        (
            "pytest",
            "test_app.py",
            "def test_health():\n"
            "    response = {'status': 'ok'}\n"
            "    assert response['status'] == 'ok'\n",
            "pytest_test",
            65,
        ),
    ],
)
def test_demo_backend_skills_have_traceable_implementation_evidence(
    skill, path, content, evidence_type, expected_score
):
    result = evaluate(skill, f"使用{skill}完成后端开发", ProjectFileSnapshot(path, content))
    assert result.overall_score == expected_score
    assert result.items[0].evidence.evidence_type == evidence_type
    assert result.items[0].evidence.file_path == path


@pytest.mark.parametrize(
    "skill,content",
    [
        ("FastAPI", "fastapi==0.116.1"),
        ("PostgreSQL", "psycopg[binary]==3.2.9"),
        ("pytest", "pytest==8.4.2"),
    ],
)
def test_new_backend_skill_dependency_does_not_claim_implementation(skill, content):
    result = evaluate(
        skill,
        f"使用{skill}完成后端开发",
        ProjectFileSnapshot("requirements.txt", content),
    )
    assert result.overall_score == 15
    assert result.items[0].verdict == "partial"
    assert result.items[0].evidence.strength == "low"


def test_schema_does_not_prove_query_optimization():
    result = evaluate(
        "SQL",
        "具备SQL查询优化能力",
        ProjectFileSnapshot(
            "schema.sql",
            "CREATE TABLE users (id INTEGER PRIMARY KEY);",
        ),
    )
    assert result.items[0].verdict == "partial"
    assert result.overall_score <= 30
    assert "不能证明" in result.items[0].explanation


def test_commented_mysql_marker_does_not_turn_generic_sql_into_mysql_evidence():
    result = evaluate(
        "MySQL",
        "MySQL数据库开发",
        ProjectFileSnapshot("schema.sql", "CREATE TABLE users (id INTEGER PRIMARY KEY);"),
        ProjectFileSnapshot("example.py", "# mysql.connector is planned but not implemented\n"),
    )
    assert result.overall_score == 0
    assert result.items[0].evidence is None


def test_unknown_discipline_is_unassessed_and_excluded_from_denominator():
    unknown = RequirementInput(uuid4(), "财务审计", "财务审计", 100)
    only_unknown = match_candidate([unknown], [], [])
    assert only_unknown.overall_score is None
    assert only_unknown.items[0].final_score is None
    assert only_unknown.items[0].verdict == "unsupported"
    assert only_unknown.gaps == []
    known = RequirementInput(uuid4(), "Python开发", "Python", 5)
    source = [ProjectFileSnapshot("main.py", "def add(a, b):\n    return a + b\n")]
    mixed = match_candidate([known, unknown], [], source)
    baseline = match_candidate([known], [], source)
    assert mixed.overall_score == baseline.overall_score
    assert mixed.items[1].final_score is None


def test_concrete_operations_document_is_support_not_verified_execution():
    content = (
        "活动目标：在四周内帮助新生了解校园社团，提高实际报名参与人数。\n"
        "目标人群：大一新生与尚未加入社团的在校本科生，计划邀请三百人。\n"
        "预算费用：物料一千元、场地五百元、志愿者餐饮三百元，共计一千八百元。\n"
        "执行计划：第一周发布招募公告，第二周确定参加社团，第三周彩排，第四周举办。\n"
        "时间安排：活动当天九点开始签到，十点介绍社团，下午进行成果展示。"
    )
    result = evaluate("活动策划", "校园活动策划", ProjectFileSnapshot("document.txt", content))
    item = result.items[0]
    assert item.verdict == "partial"
    assert result.overall_score == 40
    assert item.evidence.evidence_type == "document_structure"
    assert "人工核查" in item.explanation
    for evidence in item.evidence_list:
        assert evidence.snippet == content.splitlines()[evidence.line_start - 1][:240]
    assert len({evidence.line_start for evidence in item.evidence_list}) == len(item.evidence_list)


@pytest.mark.parametrize("line_count", [1, 2, 4])
def test_operations_keyword_line_cannot_count_as_several_rubric_elements(line_count):
    # The same line, even repeated, describes no independent evaluation elements.
    line = (
        "活动目标、目标人群、预算费用与执行计划都将在校园活动推进过程中由团队共同负责，"
        "相关人员需要按照实际场地情况进行讨论，并在开展之前确保参与者能够了解全部安排，"
        "届时将根据报名情况与社团负责人沟通后决定最终实施方式，以便保障所有参与学生获得"
        "充分的信息并按时到场参加活动。"
    )
    content = "\n".join([line] * line_count)
    result = evaluate("活动策划", "活动策划", ProjectFileSnapshot("document.txt", content))
    assert result.items[0].evidence is None


def test_operations_overlapping_rubric_uses_another_distinct_line_when_available():
    content = (
        "活动目标与目标人群：重点服务大一新生，帮助尚未加入社团的学生找到合适社团并了解报名方式。\n"
        "活动目的：通过现场体验与负责人介绍，让参加者能够在活动当天作出是否报名参加社团的决定。\n"
        "预算费用：场地使用五百元，物料打印六百元，工作人员饮水二百元，总支出不得超过一千三百元。"
    )
    result = evaluate("活动策划", "活动策划", ProjectFileSnapshot("document.txt", content))
    assert result.overall_score == 40
    assert len(result.items[0].evidence_list) == 3


def test_operations_template_placeholders_do_not_count_as_evidence():
    content = "\n".join(
        [
            "模板：活动目标待填写，后续需要补充具体行动方案和实际指标。",
            "模板：目标人群待填写，后续需要补充具体行动方案和实际指标。",
            "模板：预算费用待填写，后续需要补充具体行动方案和实际指标。",
            "模板：执行计划待填写，后续需要补充具体行动方案和实际指标。",
        ]
    )
    result = evaluate("活动策划", "活动策划", ProjectFileSnapshot("document.txt", content))
    assert result.overall_score == 0
    assert result.items[0].evidence is None
