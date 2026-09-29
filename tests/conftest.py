"""Shared pytest fixtures.

Design goal: tests must run reliably in CI with no manually-started
services. The Alarm Management API is exercised entirely in-process via
httpx's ASGITransport (no socket). Only the MCP server needs a real socket,
because the `mcp` Python client SDK's streamable-HTTP transport requires
real HTTP -- so we start it on an ephemeral localhost port in a background
thread for the duration of each test that needs it, and point its internal
Alarm Management API connector at the in-process ASGI app too (so the whole
test suite never depends on any externally-running process).
"""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from app.main import app as alarm_api_app  # apps/alarm-api, via pytest.ini pythonpath

from connectors.alarm_api.client import AlarmApiClient
from connectors.alarm_api.config import AlarmApiConfig


@pytest.fixture()
def alarm_api_asgi_transport() -> httpx.ASGITransport:
    return httpx.ASGITransport(app=alarm_api_app)


@pytest.fixture()
def alarm_api_client(alarm_api_asgi_transport) -> AlarmApiClient:
    """An AlarmApiClient talking to the alarm-api ASGI app in-process."""
    config = AlarmApiConfig(base_url="http://alarm-api.test", token="demo-token", max_retries=1)
    return AlarmApiClient(config, transport=alarm_api_asgi_transport)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def mcp_server_url():
    """Starts the real alarm-management MCP server (streamable-HTTP) on an
    ephemeral port, once for the whole test session, with its Alarm
    Management API connector pointed at the in-process alarm-api ASGI app.
    Yields the server's /mcp URL.

    Session scope is required: FastMCP's underlying StreamableHTTP session
    manager can only run its lifespan once per process, so the server is
    started a single time and shared by every test that needs it.
    """
    import server.app as mcp_app_module  # mcp-servers/alarm-management, via pythonpath

    test_client = AlarmApiClient(
        AlarmApiConfig(base_url="http://alarm-api.test", token="demo-token", max_retries=1),
        transport=httpx.ASGITransport(app=alarm_api_app),
    )
    mcp_app_module._client = test_client

    port = _free_port()
    config = uvicorn.Config(mcp_app_module.mcp.streamable_http_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)

    yield f"http://127.0.0.1:{port}/mcp"

    server.should_exit = True
    thread.join(timeout=5)
