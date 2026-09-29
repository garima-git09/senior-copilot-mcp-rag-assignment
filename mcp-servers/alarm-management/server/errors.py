"""Maps connector-level exceptions to MCP tool errors.

MCP tools signal failure by raising `McpError`, which the client sees as a
structured JSON-RPC error rather than a stack trace. This module is the one
place that performs that mapping, so every tool behaves consistently:
callers get a clear category (auth, not_found, validation, timeout,
unavailable) instead of a generic 500-style failure.
"""

from __future__ import annotations

from mcp import McpError
from mcp.types import ErrorData

from connectors.alarm_api.exceptions import (
    AlarmApiAuthError,
    AlarmApiError,
    AlarmApiNotFoundError,
    AlarmApiTimeoutError,
    AlarmApiUnavailableError,
    AlarmApiValidationError,
)

# JSON-RPC-ish custom error codes (negative range reserved for application errors).
CODE_AUTH = -32001
CODE_NOT_FOUND = -32002
CODE_VALIDATION = -32003
CODE_TIMEOUT = -32004
CODE_UNAVAILABLE = -32005
CODE_UNKNOWN = -32000


def to_mcp_error(exc: Exception) -> McpError:
    """Convert a connector exception into an `McpError` with a stable code
    and a message that never includes secrets (the connector never puts the
    bearer token into an exception message in the first place).
    """
    if isinstance(exc, AlarmApiAuthError):
        return McpError(ErrorData(code=CODE_AUTH, message=f"Alarm Management API authentication failed: {exc}"))
    if isinstance(exc, AlarmApiNotFoundError):
        return McpError(ErrorData(code=CODE_NOT_FOUND, message=str(exc)))
    if isinstance(exc, AlarmApiValidationError):
        return McpError(ErrorData(code=CODE_VALIDATION, message=str(exc)))
    if isinstance(exc, AlarmApiTimeoutError):
        return McpError(ErrorData(code=CODE_TIMEOUT, message=f"Alarm Management API timed out: {exc}"))
    if isinstance(exc, AlarmApiUnavailableError):
        return McpError(ErrorData(code=CODE_UNAVAILABLE, message=f"Alarm Management API unavailable: {exc}"))
    if isinstance(exc, AlarmApiError):
        return McpError(ErrorData(code=CODE_UNKNOWN, message=str(exc)))
    # Should not normally happen -- guard against leaking internals.
    return McpError(ErrorData(code=CODE_UNKNOWN, message="Unexpected error calling the Alarm Management API"))
