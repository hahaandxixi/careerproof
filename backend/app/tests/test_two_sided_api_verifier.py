"""Offline gates and full synthetic routes for the paid two-sided verifier."""

import copy
import json
from contextlib import asynccontextmanager

import httpx
import pytest

from app.agents.provider import DeepSeekProvider
from app.services.job_drafting import validate_draft
from app.tests.test_real_matching import matching_db  # noqa: F401
from evals.verify_two_sided_api import CODE, SYNTHETIC_SECRET, main, plan_sources_exact, run_case


@pytest.mark.parametrize("mode", ["plan", "missing_paid", "existing_output"])
def test_paid_verifier_gates_before_side_effects(monkeypatch, tmp_path, mode):
    output = tmp_path / "new.json"

    async def forbidden(record):
        pytest.fail("Model/database side effects must not begin")

    monkeypatch.setattr("evals.verify_two_sided_api.run_case", forbidden)
    flags = []
    if mode == "missing_paid":
        flags = ["--live"]
    elif mode == "existing_output":
        flags = ["--live", "--allow-paid"]
        output.write_text("original", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["verify", "--output", str(output), *flags])
    if mode == "plan":
        assert main() == 0 and not output.exists()
    else:
        with pytest.raises(SystemExit) as error:
            main()
        assert error.value.code == 2
        assert not output.exists() or output.read_text(encoding="utf-8") == "original"


def test_paid_failure_preserves_cleanup_and_usage_not_transport_text(monkeypatch, tmp_path):
    async def fail(record):
        record.update(
            stage="student_plan",
            usage=[{"inputTokens": 12, "outputTokens": 5}],
            temporarySchemaRemoved=True,
        )
        raise RuntimeError("synthetic private transport text")

    monkeypatch.setattr("evals.verify_two_sided_api.run_case", fail)
    output = tmp_path / "failed.json"
    monkeypatch.setattr("sys.argv", ["verify", "--live", "--allow-paid", "--output", str(output)])
    assert main() == 1
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["usage"][0]["inputTokens"] == 12 and saved["temporarySchemaRemoved"]
    assert saved["errorType"] == "RuntimeError" and saved["passed"] is False
    assert "synthetic private transport text" not in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("fault", ["old_version", "wrong_hash", "invalid_bounds", "altered_text"])
def test_plan_source_check_rejects_forged_citations(fault):
    import hashlib

    evidence = {
        "filePath": "version/app.py",
        "projectVersionId": "version",
        "contentHash": hashlib.sha256(CODE.encode()).hexdigest(),
        "lineStart": 1,
        "lineEnd": len(CODE.splitlines()),
        "snippet": CODE.rstrip("\n"),
    }
    plan = {"recommendations": [{"evidence": [evidence]}]}
    assert plan_sources_exact(plan, "version")
    broken = copy.deepcopy(plan)
    item = broken["recommendations"][0]["evidence"][0]
    if fault == "old_version":
        item["projectVersionId"] = "old"
    elif fault == "wrong_hash":
        item["contentHash"] = "other"
    elif fault == "invalid_bounds":
        item["lineStart"] = 0
    else:
        item["snippet"] += " forged"
    assert not plan_sources_exact(broken, "version")


@pytest.mark.parametrize("replay", [False, True])
@pytest.mark.parametrize("conflict", [False, True])
async def test_full_two_sided_api_verifier_uses_real_routes_and_synthetic_transport(
    matching_db,  # noqa: F811
    monkeypatch,
    conflict,
    replay,
):
    app, factory = matching_db

    @asynccontextmanager
    async def isolated(record):
        try:
            yield app, factory
        finally:
            # The unit fixture itself removes SQLite; this flag exercises the
            # verifier's completion contract, not a PostgreSQL cleanup claim.
            record["temporarySchemaRemoved"] = True

    monkeypatch.setattr("evals.verify_two_sided_api.isolated_api", isolated)
    calls = []

    async def handler(request):
        body = json.loads(request.content)
        assert SYNTHETIC_SECRET not in json.dumps(body)
        supplied = json.loads(body["messages"][1]["content"])
        if "description" in supplied:
            calls.append("enterprise")
            quote = "使用 Python 和 FastAPI 编写查询接口"
            answer = {
                "requirements": [
                    {
                        "raw_text": "使用" + skill + "编写查询接口",
                        "skill_name": skill,
                        "weight": 4,
                        "is_required": True,
                        "source_quote": quote,
                        "evidence_request": "提供对应源码片段与请求记录",
                        "verification_question": "异常输入如何返回响应？",
                        "weight_reason": "原文明确要求接口实现",
                    }
                    for skill in ("Python", "FastAPI")
                ]
            }
        else:
            calls.append("student")
            jobs = supplied["jobs"]
            assert len(jobs) == 1
            answer = {
                "comparison": (
                    f'输入校验与错误响应尚未展示 api_key="{SYNTHETIC_SECRET}"。'
                    if conflict
                    else "当前材料展示查询代码，运行结果与本人贡献仍待核验。"
                ),
                "focusJobId": jobs[0]["jobId"],
                "advice": [
                    {
                        "jobId": j["jobId"],
                        "reason": "材料包含可定位代码片段。",
                        "keyGap": "运行与贡献记录仍待补充。",
                        "nextTask": "提交正常与异常请求记录。",
                        "taskPlan": {
                            "deliverable": "请求记录",
                            "steps": ["记录正常与异常输入"],
                            "acceptanceChecks": ["记录含请求与对应响应"],
                        },
                        "citationIds": [e["citationId"] for e in j["evidence"]],
                    }
                    for j in jobs
                ],
            }
        return httpx.Response(
            200,
            json={
                "model": "deepseek-flash",
                "choices": [{"message": {"content": json.dumps(answer)}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    def synthetic_provider():
        return DeepSeekProvider(
            api_key="synthetic-key",
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout_seconds=5,
            max_attempts=1,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr("app.services.job_drafting.get_ai_provider", synthetic_provider)
    monkeypatch.setattr("app.services.career_planning.get_ai_provider", synthetic_provider)
    record = {}
    reused = (synthetic_reusable_draft(), "synthetic-frozen-digest") if replay else None
    await run_case(record, reused)
    assert calls == (["student"] if replay else ["enterprise", "student"])
    assert len(record["usage"]) == (1 if replay else 2)
    if replay:
        assert record["enterpriseGenerationThisRun"] == "not_run"
        assert record["draft"]["usage"] is None
        assert "exactlyTwoOfficialUsageRows" not in record["checks"]
        assert record["checks"]["exactlyOneOfficialStudentUsageRow"]
    if conflict:
        assert record["passed"] is False
        assert record["plan"]["aiFallbackUsed"] is True
        assert record["plan"]["aiStatus"] == "visible_code_fact_conflict"
        issues = record["plan"]["aiValidationIssues"]
        assert len(issues) == 1 and "尚未展示" in issues[0]["rejectedClaim"]
        assert SYNTHETIC_SECRET not in json.dumps(issues)
        assert (
            "已隐藏" in issues[0]["rejectedClaim"]
            or "redacted" in issues[0]["rejectedClaim"].lower()
        )
        assert set(issues[0]["citationIds"]).issubset(
            {e["citationId"] for e in record["plan"]["recommendations"][0]["evidence"]}
        )
        assert record["plan"]["aiPlan"] is None and record["plan"]["recommendations"]
        assert record["planReloaded"] == record["plan"]
    else:
        assert record["passed"] and all(record["checks"].values())


def synthetic_reusable_draft():
    from evals.verify_two_sided_api import DESCRIPTION

    quote = "使用 Python 和 FastAPI 编写查询接口"
    raw = {
        "requirements": [
            {
                "raw_text": "使用" + skill + "编写查询接口",
                "skill_name": skill,
                "weight": 4,
                "is_required": True,
                "source_quote": quote,
                "evidence_request": "提供对应源码片段与请求记录",
                "verification_question": "异常输入如何返回响应？",
                "weight_reason": "原文明确要求接口实现",
            }
            for skill in ("Python", "FastAPI")
        ]
    }
    return validate_draft(raw, DESCRIPTION, "deepseek-flash", None).model_dump(
        mode="json", by_alias=True
    )


@pytest.mark.parametrize("fault", [None, "unknown_hash", "different_source", "wrong_position"])
def test_reuse_accepts_only_frozen_synthetic_source_and_current_contract(
    tmp_path, monkeypatch, fault
):
    import hashlib

    from evals import verify_two_sided_api as verifier

    saved = {"draft": synthetic_reusable_draft(), "job": {"description": verifier.DESCRIPTION}}
    if fault == "different_source":
        saved["job"]["description"] = "Not the approved synthetic description"
    if fault == "wrong_position":
        saved["draft"]["requirements"][0]["sourceStart"] += 1
    content = json.dumps(saved).encode()
    digest = hashlib.sha256(content).hexdigest()
    path = tmp_path / "synthetic.json"
    path.write_bytes(content)
    # Synthetic unit fixture; production allowlist is not edited by the test.
    monkeypatch.setattr(
        verifier, "_APPROVED_DRAFT_RECORDS", set() if fault == "unknown_hash" else {digest}
    )
    if fault:
        with pytest.raises(ValueError):
            verifier.load_reusable_draft(path)
    else:
        draft, got_hash = verifier.load_reusable_draft(path)
        assert got_hash == digest and draft["usage"] is None
        assert draft["requirements"] == saved["draft"]["requirements"]


def test_invalid_reuse_record_is_archived_before_any_live_call(tmp_path, monkeypatch):
    from evals import verify_two_sided_api as verifier

    path = tmp_path / "invalid.json"
    path.write_text("{}")
    output = tmp_path / "result.json"
    calls = []

    async def unexpected(*args):
        calls.append(args)

    monkeypatch.setattr(verifier, "run_case", unexpected)
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify",
            "--live",
            "--allow-paid",
            "--output",
            str(output),
            "--reuse-draft-record",
            str(path),
        ],
    )
    assert verifier.main() == 1 and calls == []
    assert json.loads(output.read_text())["errorType"] == "ValueError"
