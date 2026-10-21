"""One bounded real DeepSeek Agent run on the fixed V2 campus project.

Run from the isolated temporary backend copy with PYTHONPATH set to that copy.
No normal database or normal site is touched. Never retries the report.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).parent
BASE = EVIDENCE.parent
SRC = ROOT / "backend/.tmp/agent-live-20261021/backend"
RUN = ROOT / "backend/.tmp/complete-project-20261021"
STATE = json.loads((RUN / "careerproof-state.json").read_text(encoding="utf-8"))
V2 = json.loads((BASE / "growth-runtime/v2-manifest.json").read_text(encoding="utf-8"))
CREDS = json.loads((RUN / "credentials.json").read_text(encoding="utf-8"))
PRICE = json.loads((EVIDENCE / "prices-20261021.json").read_text(encoding="utf-8"))
REPORT = json.loads((BASE / "growth-runtime/report-after.json").read_text(encoding="utf-8"))
CLAIM = ROOT / "backend/.tmp/agent-live-20261021/run-claim.json"
OUT = EVIDENCE / "live-result.json"
REPORT_OUT = EVIDENCE / "report-after.json"
ATTEMPTS_OUT = EVIDENCE / "attempts.json"
USAGE_OUT = EVIDENCE / "usage.json"
CONTAINER = "careerproof-agent-display-20261021"
DATABASE = "cp_agent_display_20261021"
MAX_INPUT = 60_000
MAX_OUTPUT = 4_000
MAX_REQUESTS = 12
MAX_COST = Decimal("5")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message: str, **extra) -> None:
    payload = {"status": "stopped", "reason": message, **extra}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    raise SystemExit(1)


def env_dict() -> dict[str, str]:
    values = {}
    for line in (SRC / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    return values


def sql(query: str) -> str:
    return subprocess.check_output(
        ["docker", "exec", CONTAINER, "psql", "-U", "cp_agent", "-d", DATABASE,
         "-At", "-v", "ON_ERROR_STOP=1", "-c", query],
        encoding="utf-8",
    ).strip()


def main() -> None:
    if CLAIM.exists():
        fail("run claim already exists; refusing a second run")
    if OUT.exists() or REPORT_OUT.exists():
        fail("output already exists; refusing to overwrite a prior run")
    if sha(Path(V2["zip"])) != V2["sha256"]:
        fail("V2 material ZIP changed")
    if PRICE.get("verifiedDate") != "2026-10-21" or PRICE.get("model") != "deepseek-flash":
        fail("price snapshot is not the reviewed snapshot")
    env = env_dict()
    checks = {
        "AI_EXTERNAL_ENABLED": "true",
        "AI_PROVIDER": "deepseek",
        "DEEPSEEK_MODEL": "deepseek-flash",
        "DEEPSEEK_MAX_ATTEMPTS": "1",
        "AI_PER_REPORT_INPUT_TOKEN_LIMIT": str(MAX_INPUT),
        "AI_PER_REPORT_OUTPUT_TOKEN_LIMIT": str(MAX_OUTPUT),
        "AI_CONTEXT_EVIDENCE_LIMIT": "3",
    }
    for key, expected in checks.items():
        if env.get(key, "").lower() != expected.lower():
            fail(f"isolated setting mismatch: {key}")
    if "cp_agent_display_20261021" not in env.get("DATABASE_URL", "") or "55442" not in env.get("DATABASE_URL", ""):
        fail("database is not the isolated database")
    info = json.loads(subprocess.check_output(["docker", "inspect", CONTAINER]))[0]
    if not info["State"]["Running"] or info["Config"]["Labels"].get("careerproof.scope") != "agent-display-20261021":
        fail("isolated container ownership check failed")

    # Offline preflight using the same saved V2 evidence and current provider estimator.
    from app.agents.evidence_workflow import build_evidence_contexts
    from app.agents.provider import DeepSeekProvider
    from app.tools.code_analyzer import CodeEvidence
    from app.tools.matcher import MatchItemResult, MatchResult

    names = {field.name for field in CodeEvidence.__dataclass_fields__.values()}
    aliases = {"evidence_type": "evidenceType", "file_path": "filePath", "line_start": "lineStart",
               "line_end": "lineEnd", "content_hash": "contentHash", "context_complete": "contextComplete",
               "context_note": "contextNote", "function_line_start": "functionLineStart",
               "function_line_end": "functionLineEnd", "source_line_count": "sourceLineCount"}
    def evidence(row, skill):
        values = {name: row[aliases.get(name, name)] for name in names if aliases.get(name, name) in row}
        return CodeEvidence(**{**values, "skill": skill})
    items = []
    for item in REPORT["items"]:
        rows = [evidence(row, item["skill"]) for row in item["evidenceList"]]
        items.append(MatchItemResult(
            requirement_id=UUID(item["requirementId"]), requirement_title=item["requirementTitle"],
            skill=item["skill"], claimed=item["claimed"], claim_text=item["claimText"],
            evidence=rows[0] if rows else None, evidence_list=rows, verdict=item["verdict"],
            ai_confidence=item["aiConfidence"], rule_base_score=item["ruleBaseScore"],
            weight=item["weight"], final_score=item["finalScore"], explanation=item["explanation"],
            formula_version=item["formulaVersion"],
        ))
    result = MatchResult(REPORT.get("overallScore"), items, REPORT["gaps"], REPORT["claimedOnly"], REPORT["summary"])
    contexts = build_evidence_contexts(result, max_evidence=3)
    provider = DeepSeekProvider(api_key="offline-estimation-not-real", base_url="https://api.deepseek.com",
                                model="deepseek-flash", timeout_seconds=1, max_attempts=1)
    input_estimate = provider.estimate_evidence_input(contexts)
    if input_estimate > MAX_INPUT:
        fail("complete five-requirement input exceeds 60000", inputEstimate=input_estimate)

    CLAIM.parent.mkdir(parents=True, exist_ok=True)
    with CLAIM.open("x", encoding="utf-8") as stream:
        json.dump({"batch": "complete-project-agent-20261021", "status": "claimed_before_send"}, stream)
    evidence_ids = [e.citation_id for c in contexts for e in c.evidence]
    preflight = {
        "materialZipSha256": V2["sha256"],
        "sourceHashes": {
            rel: sha(SRC / rel) for rel in (
                "app/core/config.py", "app/agents/evidence_workflow.py",
                "app/tools/code_analyzer.py", "app/tools/matcher.py",
            )
        },
        "inputEstimate": input_estimate,
        "requirements": len(contexts),
        "evidence": len(evidence_ids),
        "maxInput": MAX_INPUT,
        "maxOutput": MAX_OUTPUT,
        "maxRequests": MAX_REQUESTS,
        "maxCostYuan": str(MAX_COST),
        "price": PRICE,
        "oldReportId": STATE["reportId"],
        "v2ReportId": "5960cf5d-0f6a-4564-b7ca-037e17d743e3",
        "claim": str(CLAIM),
        "oldAuthorizationApplicable": False,
    }
    (EVIDENCE / "preflight.json").write_text(json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if input_estimate > MAX_INPUT:
        fail("preflight did not fit")

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = (EVIDENCE / "api.raw.out").open("wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port),
         "--no-proxy-headers"],
        cwd=SRC,
        env={**os.environ, "PYTHONPATH": str(SRC), "PYTHONIOENCODING": "utf-8"},
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        base = f"http://127.0.0.1:{port}/api/v1"
        for _ in range(150):
            if proc.poll() is not None:
                fail("isolated API process exited before health")
            try:
                if httpx.get(base + "/health", trust_env=False, timeout=2).status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(.1)
        else:
            fail("isolated API did not become healthy")

        with httpx.Client(base_url=base, timeout=120, trust_env=False) as client:
            def data(method, path, **kwargs):
                response = client.request(method, path, **kwargs)
                response.raise_for_status()
                body = response.json()
                if body.get("code") != 0:
                    fail("API error", path=path, body=body)
                return body["data"]

            data("POST", "/auth/login", json={"email": CREDS["studentEmail"], "password": CREDS["password"]})
            old_before = data("GET", "/match-reports/" + STATE["reportId"])
            v2_before = data("GET", "/match-reports/5960cf5d-0f6a-4564-b7ca-037e17d743e3")
            started = data("POST", "/matches", json={
                "jobId": "33d0b1e1-1b45-4ef9-a0fc-c44da1ba1fd0",
                "resumeVersionId": "5ecb752b-770b-4280-afb4-70ccbd1ae4b0",
                "projectVersionIds": ["6db170c9-ea2b-4036-84d1-47260c687014"],
                "externalAiConsent": True,
            })
            task_id = started["taskId"]
            for _ in range(600):
                task = data("GET", "/analysis-tasks/" + task_id)
                if task["status"] == "completed":
                    break
                if task["status"] in {"failed", "cancelled"}:
                    fail("Agent task did not complete", taskStatus=task["status"])
                time.sleep(.5)
            else:
                fail("Agent task timed out")
            report = data("GET", "/match-reports/" + task["reportId"])
            old_after = data("GET", "/match-reports/" + STATE["reportId"])
            v2_after = data("GET", "/match-reports/5960cf5d-0f6a-4564-b7ca-037e17d743e3")
            if old_after != old_before or v2_after != v2_before:
                fail("historical report changed")

            attempts_raw = sql(
                f"SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.id)::text,'[]') "
                f"FROM ai_request_attempts t WHERE t.analysis_task_id = '{task_id}'"
            )
            usage_raw = sql(
                f"SELECT COALESCE(jsonb_agg(to_jsonb(u) ORDER BY u.id)::text,'[]') "
                f"FROM ai_usage_logs u WHERE u.analysis_task_id = '{task_id}'"
            )
            attempts = json.loads(attempts_raw)
            usage = json.loads(usage_raw)
            if not usage:
                fail("no trusted usage rows; refusing to treat as success")
            input_tokens = sum(int(row.get("input_tokens") or 0) for row in usage)
            output_tokens = sum(int(row.get("output_tokens") or 0) for row in usage)
            cost = (Decimal(input_tokens) * Decimal("2") + Decimal(output_tokens) * Decimal("8")) / Decimal(1_000_000)
            if len(attempts) > MAX_REQUESTS:
                fail("physical request limit exceeded", attempts=len(attempts))
            if cost > MAX_COST:
                fail("cost limit exceeded", costYuan=str(cost))
            if report.get("analysisMode") == "rules":
                fail("Agent fell back to rules", report=report.get("id"))
            if not report.get("items") or len(report["items"]) != 5:
                fail("report does not contain five items", count=len(report.get("items", [])))
            python_item = next(item for item in report["items"] if item["skill"] == "Python")
            ai_citations = python_item.get("aiCitationIds") or []
            evidence_paths = {(e.get("filePath"), e.get("lineStart"), e.get("lineEnd"))
                              for e in python_item.get("evidenceList", [])}
            required = {
                ("6db170c9-ea2b-4036-84d1-47260c687014/campus_signup/service.py", 25, 54),
                ("6db170c9-ea2b-4036-84d1-47260c687014/campus_signup/service.py", 56, 77),
            }
            if not required.issubset(evidence_paths):
                fail("Python business evidence missing", pythonEvidence=sorted(evidence_paths))
            REPORT_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            ATTEMPTS_OUT.write_text(json.dumps(attempts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            USAGE_OUT.write_text(json.dumps(usage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result = {
                "status": "completed",
                "taskId": task_id,
                "reportId": report["id"],
                "analysisMode": report.get("analysisMode"),
                "aiProvider": report.get("aiProvider"),
                "itemCount": len(report["items"]),
                "pythonCitationIds": ai_citations,
                "pythonEvidence": sorted([list(x) for x in evidence_paths]),
                "physicalRequests": len(attempts),
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "costYuanAtPeak": str(cost),
                "inputEstimate": input_estimate,
                "oldReportsUnchanged": True,
                "realRequests": len(attempts),
                "sourceHashes": preflight["sourceHashes"],
                "materialZipSha256": V2["sha256"],
                "price": PRICE,
                "scope": "one isolated full five-item Agent report; no page; no normal DB",
            }
            OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result, ensure_ascii=False))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


if __name__ == "__main__":
    main()
