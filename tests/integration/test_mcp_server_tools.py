"""Integration tests for the alarm-management MCP server.

Covers: tool registration/discovery, schema validation, pagination,
API error mapping, and trace propagation -- run against a real MCP server
started on an ephemeral port (see tests/conftest.py::mcp_server_url), with
its Alarm Management API connector pointed at the alarm-api ASGI app
in-process (no externally running services required).
"""

from __future__ import annotations

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

pytestmark = pytest.mark.integration


async def _open_session(url: str):
    return streamablehttp_client(url)


@pytest.mark.asyncio
async def test_tool_discovery_lists_all_expected_tools(mcp_server_url):
    async with streamablehttp_client(mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}

    expected = {
        "search_assets",
        "get_asset_metadata",
        "get_alarms",
        "get_alarm_by_id",
        "get_alarm_summary",
        "get_alarm_trends",
        "correlate_alarms",
        "analyze_alarm_flood",
        "get_rationalization_candidates",
        "score_alarm_priority",
        "get_operator_recommendations",
        "generate_calculation",
        "execute_calculation",
        "get_kpi_definitions",
    }
    assert expected.issubset(names)
    # Every tool must carry a non-empty description (meaningful tool descriptions requirement).
    for t in tools.tools:
        assert t.description


@pytest.mark.asyncio
async def test_search_assets_and_pagination(mcp_server_url):
    async with streamablehttp_client(mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            search = await session.call_tool("search_assets", {"query": "Boiler Feed Pump 101"})
            assert not search.isError
            asset_id = search.structuredContent["results"][0]["asset_id"]

            page1 = await session.call_tool("get_alarms", {"asset_id": asset_id, "page": 1, "page_size": 2})
            assert not page1.isError
            assert page1.structuredContent["pagination"]["page"] == 1
            assert page1.structuredContent["pagination"]["page_size"] == 2
            assert len(page1.structuredContent["data"]) <= 2


@pytest.mark.asyncio
async def test_schema_validation_rejects_bad_arguments(mcp_server_url):
    async with streamablehttp_client(mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("correlate_alarms", {"asset_ids": [], "time_range": {"start_time": "x", "end_time": "y"}})
            assert result.isError
            assert "validation error" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_not_found_is_mapped_to_execution_error(mcp_server_url):
    async with streamablehttp_client(mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_asset_metadata", {"asset_id": "AST-does-not-exist"})
            assert result.isError
            assert "not found" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_unknown_tool_is_reported_as_error(mcp_server_url):
    async with streamablehttp_client(mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("not_a_real_tool", {})
            assert result.isError


@pytest.mark.asyncio
async def test_trace_id_is_propagated_in_tool_output(mcp_server_url):
    async with streamablehttp_client(mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("search_assets", {"query": "compressor"})
            assert not result.isError
            assert result.structuredContent["trace_id"].startswith("trace-mcp-")


@pytest.mark.asyncio
async def test_multi_step_chaining_asset_to_priority(mcp_server_url):
    """Mirrors the reference Postman chaining flow: search -> alarms -> priority score."""
    async with streamablehttp_client(mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            search = await session.call_tool("search_assets", {"query": "Boiler Feed Pump 101"})
            asset_id = search.structuredContent["results"][0]["asset_id"]

            alarms = await session.call_tool("get_alarms", {"asset_id": asset_id, "page": 1, "page_size": 1, "sort_by": "start_time", "sort_order": "desc"})
            assert alarms.structuredContent["data"], "expected at least one alarm for this asset"
            alarm_id = alarms.structuredContent["data"][0]["alarm_id"]

            priority = await session.call_tool("score_alarm_priority", {"alarm_id": alarm_id})
            assert not priority.isError
            assert 0 <= priority.structuredContent["priority_score"] <= 100
