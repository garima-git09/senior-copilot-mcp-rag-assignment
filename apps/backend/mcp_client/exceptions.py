"""Typed exceptions for the copilot's MCP client layer."""

from __future__ import annotations


class McpClientError(Exception):
    """Base class for all MCP-client-side errors."""


class McpServerUnavailableError(McpClientError):
    """The MCP server could not be reached (connection refused/timeout)."""


class McpToolNotFoundError(McpClientError):
    """The requested tool is not in the server's discovered tool list."""


class McpInvalidArgumentsError(McpClientError):
    """The server rejected the call due to schema/validation failure."""


class McpToolExecutionError(McpClientError):
    """The tool ran but failed (e.g. underlying API returned an error)."""
