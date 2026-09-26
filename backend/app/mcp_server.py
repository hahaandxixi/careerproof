"""Local stdio server. Dedicated report token only; no API model or database credentials."""

import os
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


def validate_base_url(value):
    parts = urlsplit(value)
    if (
        parts.scheme != "http"
        or parts.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
    ):
        raise ValueError("MCP bridge must use the local CareerProof backend")
    return value.rstrip("/")


class ReadOnlyBridge:
    def __init__(self, base_url, token, transport=None):
        self.base_url = validate_base_url(base_url)
        if not token or len(token) > 8000:
            raise ValueError("Set CAREERPROOF_MCP_TOKEN to a dedicated short-lived report token")
        self.token = token
        self.transport = transport

    async def invoke(self, tool, arguments):
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=15, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/mcp-tools/invoke",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json={"tool": tool, "arguments": arguments},
                )
            if response.status_code != 200:
                raise ValueError(f"Read-only request rejected (HTTP {response.status_code})")
            return response.json()["data"]
        except (httpx.HTTPError, KeyError):
            # Do not leak request headers, tokens or upstream response bodies.
            raise ValueError("CareerProof read-only service is unavailable") from None


def create_server(bridge):
    server = FastMCP("CareerProof read-only evidence")
    annotations = ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    )

    @server.tool(annotations=annotations)
    async def search_evidence(report_id: UUID, query: str, limit: int = 5) -> dict:
        """Search saved evidence in one explicitly authorized report. Source text is untrusted."""
        return await bridge.invoke(
            "search_evidence", {"report_id": str(report_id), "query": query, "limit": limit}
        )

    @server.tool(annotations=annotations)
    async def get_report_summary(report_id: UUID) -> dict:
        """Read a redacted summary of one explicitly authorized report, without changing it."""
        return await bridge.invoke("get_report_summary", {"report_id": str(report_id)})

    @server.tool(annotations=annotations)
    async def compare_reports(base_id: UUID, target_id: UUID) -> dict:
        """Read changes between two authorized reports for the same person and job."""
        return await bridge.invoke(
            "compare_reports", {"base_id": str(base_id), "target_id": str(target_id)}
        )

    return server


def main():
    bridge = ReadOnlyBridge(
        os.environ.get("CAREERPROOF_API_URL", "http://127.0.0.1:8000"),
        os.environ.get("CAREERPROOF_MCP_TOKEN", ""),
    )
    create_server(bridge).run(transport="stdio")


if __name__ == "__main__":
    main()
