"""Integration tests for the copilot's MCP client (apps/backend/mcp_client),
run against the real MCP server (session-scoped fixture in tests/conftest.py).

Covers: server connectivity, tool discovery, tool invocation, invalid
arguments, missing tools, and partial failure (server unreachable).
"""

from __future__ import annotations

import pytest

from apps.backend.mcp_client.client import AlarmMcpClient
from apps.backend.mcp_client.exceptions import (
    McpInvalidArgumentsError,
    McpServerUnavailableError,
    McpToolExecutionError,
    McpToolNotFoundError,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_discover_tools_returns_the_full_catalog(mcp_server_url):
    client = AlarmMcpClient(mcp_server_url)
    tools = await client.discover_tools()
    assert len(tools) == 14
    assert {t.name for t in tools} >= {"search_assets", "get_alarms", "correlate_alarms"}


@pytest.mark.asyncio
async def test_call_tool_success_records_trace(mcp_server_url):
    client = AlarmMcpClient(mcp_server_url)
    result = await client.call_tool("search_assets", {"query": "compressor"})
    assert result["count"] >= 1
    assert client.call_log[-1].outcome == "success"


@pytest.mark.asyncio
async def test_call_missing_tool_raises_typed_error(mcp_server_url):
    client = AlarmMcpClient(mcp_server_url)
    with pytest.raises(McpToolNotFoundError):
        await client.call_tool("not_a_real_tool", {})
    assert client.call_log[-1].outcome == "tool_not_found"


@pytest.mark.asyncio
async def test_call_tool_invalid_arguments_raises_typed_error(mcp_server_url):
    client = AlarmMcpClient(mcp_server_url)
    with pytest.raises(McpInvalidArgumentsError):
        await client.call_tool("correlate_alarms", {"asset_ids": [], "time_range": {"start_time": "x", "end_time": "y"}})
    assert client.call_log[-1].outcome == "invalid_arguments"


@pytest.mark.asyncio
async def test_call_tool_execution_error_raises_typed_error(mcp_server_url):
    client = AlarmMcpClient(mcp_server_url)
    with pytest.raises(McpToolExecutionError):
        await client.call_tool("get_asset_metadata", {"asset_id": "AST-does-not-exist"})


@pytest.mark.asyncio
async def test_unreachable_server_raises_unavailable_error():
    client = AlarmMcpClient("http://127.0.0.1:1/mcp", timeout_seconds=2)
    with pytest.raises(McpServerUnavailableError):
        await client.discover_tools()


@pytest.mark.asyncio
async def test_multi_step_chaining_via_client(mcp_server_url):
    client = AlarmMcpClient(mcp_server_url)
    search = await client.call_tool("search_assets", {"query": "Boiler Feed Pump 101"})
    asset_id = search["results"][0]["asset_id"]
    alarms = await client.call_tool("get_alarms", {"asset_id": asset_id, "page": 1, "page_size": 1})
    assert alarms["data"], "expected at least one alarm"
    alarm_id = alarms["data"][0]["alarm_id"]
    priority = await client.call_tool("score_alarm_priority", {"alarm_id": alarm_id})
    assert 0 <= priority["priority_score"] <= 100
    assert len(client.call_log) == 3
    assert [r.tool_name for r in client.call_log] == ["search_assets", "get_alarms", "score_alarm_priority"]
