"""Real SDK stdio client acceptance using existing synthetic local reports; no model calls."""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from evals.demo_credentials import get_demo_credentials


def data(response):
    response.raise_for_status()
    return response.json()["data"]


def content(result):
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-id", type=UUID, required=True)
    parser.add_argument("--target-id", type=UUID, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Acceptance record must not overwrite an existing file")
    api = "http://127.0.0.1:8000"
    ids = [str(args.base_id), str(args.target_id)]
    async with httpx.AsyncClient(base_url=api + "/api/v1", timeout=20, trust_env=False) as client:
        data(await client.post("/auth/login", json=get_demo_credentials("student")))
        # Only user-specified existing synthetic reports; no new model evaluation.
        for report_id in ids:
            data(await client.get(f"/match-reports/{report_id}"))
        grant = data(
            await client.post(
                "/mcp-tools/grants", json={"report_ids": ids, "external_client_consent": True}
            )
        )
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "transport": "stdio",
            "client": "official-python-sdk",
            "reports": ids,
            "grantId": grant["grantId"],
            "paidModelCalls": 0,
        }
        safe_env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
        }
        safe_env.update(
            {"CAREERPROOF_API_URL": api, "CAREERPROOF_MCP_TOKEN": grant["token"], "PYTHONUTF8": "1"}
        )
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
            env=safe_env,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        try:
            async with asyncio.timeout(60):
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        record["tools"] = [tool.name for tool in tools.tools]
                        summary = await session.call_tool(
                            "get_report_summary", {"report_id": ids[1]}
                        )
                        record["summarySucceeded"] = not summary.isError
                        found = await session.call_tool(
                            "search_evidence", {"report_id": ids[1], "query": "FastAPI", "limit": 2}
                        )
                        record["searchSucceeded"] = not found.isError
                        record["searchResults"] = content(found) if not found.isError else None
                        comparison = await session.call_tool(
                            "compare_reports", {"base_id": ids[0], "target_id": ids[1]}
                        )
                        record["comparisonSucceeded"] = not comparison.isError
                        record["comparison"] = (
                            content(comparison) if not comparison.isError else None
                        )
                        denied = await session.call_tool(
                            "get_report_summary", {"report_id": str(uuid4())}
                        )
                        record["unscopedRejected"] = bool(denied.isError)
                        data(await client.delete(f"/mcp-tools/grants/{grant['grantId']}"))
                        revoked = await session.call_tool(
                            "get_report_summary", {"report_id": ids[1]}
                        )
                        record["revokedRejected"] = bool(revoked.isError)
        finally:
            await client.delete(f"/mcp-tools/grants/{grant['grantId']}")
        record["passed"] = set(record["tools"]) == {
            "get_report_summary",
            "search_evidence",
            "compare_reports",
        } and all(
            record.get(key)
            for key in (
                "summarySucceeded",
                "searchSucceeded",
                "comparisonSucceeded",
                "unscopedRejected",
                "revokedRejected",
            )
        )
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(record, output, ensure_ascii=False, indent=2)
        print(
            json.dumps({"passed": record["passed"], "output": str(args.output)}, ensure_ascii=False)
        )
        if not record["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
