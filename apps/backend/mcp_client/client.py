"""MCP client used by the copilot orchestrator to talk to the
alarm-management MCP server (and any additional MCP server added later).

Responsibilities:
    - Connect over streamable-HTTP and discover tools (name, description,
      input schema) at runtime -- nothing about the tool surface is
      hard-coded in the orchestrator.
    - Invoke tools with schema-aware arguments.
    - Distinguish "tool not found" (unavailable tool), "invalid arguments"
      (schema/validation failure surfaced by the server), "tool execution
      failure" (the tool ran but the underlying API call failed), and
      "server unavailable" (transport-level failure) as distinct, typed
      client exceptions the orchestrator can handle differently.
    - Record every call (tool name, arguments, duration, outcome, trace id)
      into an execution trace that the GUI can render.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from apps.backend.mcp_client.exceptions import (
    McpClientError,
    McpInvalidArgumentsError,
    McpServerUnavailableError,
    McpToolExecutionError,
    McpToolNotFoundError,
)

logger = logging.getLogger("mcp_client")


@dataclass
class ToolDescriptor:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None


@dataclass
class ToolCallRecord:
    """One entry in the MCP execution trace shown in the GUI."""

    tool_name: str
    arguments: dict[str, Any]
    started_at: float
    duration_ms: float
    outcome: str  # "success" | "invalid_arguments" | "tool_not_found" | "execution_error" | "unavailable"
    trace_id: str | None = None
    result_preview: Any = None
    error: str | None = None


class AlarmMcpClient:
    """A short-lived client: each call opens a fresh session against the
    configured MCP server. This keeps the copilot backend stateless and
    resilient to the MCP server restarting between requests, at a small
    per-call connection cost that is acceptable for an interactive copilot.
    """

    def __init__(self, server_url: str, timeout_seconds: float = 20.0) -> None:
        self.server_url = server_url
        self.timeout_seconds = timeout_seconds
        self.call_log: list[ToolCallRecord] = []

    @asynccontextmanager
    async def _session(self):
        try:
            async with streamablehttp_client(self.server_url, timeout=self.timeout_seconds) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        except McpClientError:
            raise
        except BaseException as exc:
            # Any transport/handshake failure (connection refused, DNS error,
            # timeout, or an ExceptionGroup wrapping one of these from the
            # underlying anyio task group) is surfaced uniformly as
            # "MCP server unavailable" -- the orchestrator only needs to know
            # the server could not be reached, not the transport internals.
            raise McpServerUnavailableError(f"Could not reach MCP server at {self.server_url}: {exc}") from exc

    async def discover_tools(self) -> list[ToolDescriptor]:
        async with self._session() as session:
            result = await session.list_tools()
            return [
                ToolDescriptor(
                    name=t.name,
                    description=t.description or "",
                    input_schema=t.inputSchema,
                    output_schema=t.outputSchema,
                )
                for t in result.tools
            ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Invoke a tool by name. Raises a typed McpClientError subclass on
        any failure; on success returns the tool's structured content
        (a dict, matching the server's typed output schema).
        """
        started = time.perf_counter()
        record = ToolCallRecord(tool_name=name, arguments=arguments, started_at=started, duration_ms=0.0, outcome="success")
        try:
            async with self._session() as session:
                result = await session.call_tool(name, arguments)
        except McpServerUnavailableError as exc:
            record.outcome = "unavailable"
            record.error = str(exc)
            record.duration_ms = round((time.perf_counter() - started) * 1000, 2)
            self.call_log.append(record)
            raise

        record.duration_ms = round((time.perf_counter() - started) * 1000, 2)

        if result.isError:
            message = _first_text(result.content)
            if message.startswith("Unknown tool"):
                record.outcome = "tool_not_found"
                record.error = message
                self.call_log.append(record)
                raise McpToolNotFoundError(message)
            if "validation error" in message.lower():
                record.outcome = "invalid_arguments"
                record.error = message
                self.call_log.append(record)
                raise McpInvalidArgumentsError(message)
            record.outcome = "execution_error"
            record.error = message
            self.call_log.append(record)
            raise McpToolExecutionError(message)

        structured = result.structuredContent
        if isinstance(structured, dict):
            record.trace_id = structured.get("trace_id")
        record.result_preview = _preview(structured)
        self.call_log.append(record)
        return structured

    def reset_log(self) -> None:
        self.call_log = []


def _first_text(content: list[Any]) -> str:
    for item in content:
        text = getattr(item, "text", None)
        if text:
            return text
    return "Unknown MCP tool error"


def _preview(value: Any, max_list_items: int = 5, max_chars: int = 1500) -> Any:
    """Produce a GUI-safe preview of a tool result.

    Shrinks any oversized list field in place (most commonly `data` from a
    paginated Alarm API response) so the preview stays a real, valid
    JSON-serializable object -- never a hand-truncated string. A previous
    version used ``str(value)[:max_len]``, which (a) produced Python's
    single-quoted repr instead of valid JSON and (b) could cut off mid-token,
    both of which broke the GUI's ``st.json()`` renderer (it re-parses the
    text as JSON). Returning a real dict/list here sidesteps both problems;
    only a pathologically large non-list value falls back to a truncated
    string, which the GUI must render as text, not st.json.
    """
    if isinstance(value, dict):
        shrunk: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, list) and len(item) > max_list_items:
                shrunk[key] = item[:max_list_items]
                shrunk[f"{key}_note"] = f"showing first {max_list_items} of {len(item)} items"
            else:
                shrunk[key] = item
        value = shrunk

    try:
        text = json.dumps(value, default=str)
    except TypeError:
        return str(value)[:max_chars]

    return value if len(text) <= max_chars else text[:max_chars] + "...(truncated)"