from uuid import uuid4

import pytest

from app.tools.code_analyzer import ProjectFileSnapshot, find_evidence
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate


@pytest.mark.parametrize(
    "skill,path,source",
    [
        ("Shell", "health.sh", 'curl --fail "$URL"'),
        ("CI/CD", ".github/workflows/check.yml", "steps:\n  - run: bash -n health.sh"),
        ("监控告警", "alerts.yml", "- alert: TargetDown\n  expr: up == 0"),
        ("索引优化", "index.sql", "CREATE INDEX tasks_owner ON tasks(owner_id);"),
        ("备份恢复", "backup.sh", 'pg_dump --file="$OUT" "$DATABASE_URL"'),
        ("权限管理", "roles.sql", "GRANT SELECT ON tasks TO reader;"),
        ("数据库监控", "monitor.sql", "SELECT state FROM pg_stat_activity;"),
    ],
)
def test_static_ops_evidence_is_partial_and_source_exact(skill, path, source):
    files = [ProjectFileSnapshot(path, source)]
    result = enrich_evidence(
        match_candidate([RequirementInput(uuid4(), skill, skill, 5)], [], files), files
    )
    item = result.items[0]
    assert item.verdict == "partial"
    assert item.evidence_list
    for evidence in item.evidence_list:
        assert evidence.snippet == "\n".join(
            source.splitlines()[evidence.line_start - 1 : evidence.line_end]
        )
    assert not find_evidence([ProjectFileSnapshot("README.txt", source)], skill)
    comment = "-- " if path.endswith(".sql") else "# "
    assert not find_evidence(
        [ProjectFileSnapshot(path, "\n".join(comment + line for line in source.splitlines()))],
        skill,
    )


def test_list_archive_is_not_claimed_as_successful_restore():
    evidence = find_evidence(
        [ProjectFileSnapshot("restore.sh", 'pg_restore --list "$FILE"')], "备份恢复"
    )
    assert evidence and "列目录不等于实际恢复" in evidence[0].explanation


def test_quoted_command_is_not_an_implementation():
    assert not find_evidence([ProjectFileSnapshot("fake.sh", 'echo "pg_dump test"')], "备份恢复")
