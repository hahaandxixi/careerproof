"""Optional SDK transport and adapter checks; no paid API."""

from uuid import uuid4

import httpx
import pytest

pytest.importorskip("mcp")
from app.mcp_server import ReadOnlyBridge, create_server, validate_base_url  # noqa: E402


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://127.0.0.1@evil.test",
        "http://127.0.0.1/redirect",
        "http://localhost?token=secret",
    ],
)
def test_bridge_rejects_nonlocal_or_redirecting_base(url):
    with pytest.raises(ValueError):
        validate_base_url(url)


async def test_sdk_exposes_exactly_read_tools_and_safe_errors():
    def handler(request):
        assert request.headers["authorization"] == "Bearer synthetic-token"
        return httpx.Response(401, text="sensitive-upstream-detail")

    bridge = ReadOnlyBridge(
        "http://127.0.0.1:8000", "synthetic-token", httpx.MockTransport(handler)
    )
    server = create_server(bridge)
    tools = await server.list_tools()
    assert {t.name for t in tools} == {"search_evidence", "compare_reports", "get_report_summary"}
    assert all(t.annotations.readOnlyHint and not t.annotations.destructiveHint for t in tools)
    with pytest.raises(ValueError, match="HTTP 401") as error:
        await bridge.invoke("get_report_summary", {"report_id": str(uuid4())})
    assert "synthetic-token" not in str(error.value)
    assert "sensitive-upstream-detail" not in str(error.value)
