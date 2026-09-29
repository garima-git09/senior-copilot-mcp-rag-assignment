"""Typed exceptions raised by the Alarm Management API connector.

The MCP server catches these and maps them to well-defined MCP tool errors,
so no raw HTTP/transport exception ever leaks across the MCP boundary.
"""

from __future__ import annotations


class AlarmApiError(Exception):
    """Base class for all connector errors."""


class AlarmApiAuthError(AlarmApiError):
    """401/403 from the Alarm Management API."""


class AlarmApiNotFoundError(AlarmApiError):
    """404 from the Alarm Management API."""


class AlarmApiValidationError(AlarmApiError):
    """422/400 from the Alarm Management API (bad request payload)."""


class AlarmApiTimeoutError(AlarmApiError):
    """Request exceeded the configured timeout, even after retries."""


class AlarmApiUnavailableError(AlarmApiError):
    """Connection refused / 5xx after exhausting retries."""
