"""Unit tests for server/errors.py -- every connector exception must map to
a distinct, stable MCP error code.
"""

from __future__ import annotations

from server.errors import (
    CODE_AUTH,
    CODE_NOT_FOUND,
    CODE_TIMEOUT,
    CODE_UNAVAILABLE,
    CODE_UNKNOWN,
    CODE_VALIDATION,
    to_mcp_error,
)

from connectors.alarm_api.exceptions import (
    AlarmApiAuthError,
    AlarmApiError,
    AlarmApiNotFoundError,
    AlarmApiTimeoutError,
    AlarmApiUnavailableError,
    AlarmApiValidationError,
)


def test_auth_error_maps_to_auth_code():
    err = to_mcp_error(AlarmApiAuthError("bad token"))
    assert err.error.code == CODE_AUTH


def test_not_found_error_maps_to_not_found_code():
    err = to_mcp_error(AlarmApiNotFoundError("missing"))
    assert err.error.code == CODE_NOT_FOUND


def test_validation_error_maps_to_validation_code():
    err = to_mcp_error(AlarmApiValidationError("bad payload"))
    assert err.error.code == CODE_VALIDATION


def test_timeout_error_maps_to_timeout_code():
    err = to_mcp_error(AlarmApiTimeoutError("slow"))
    assert err.error.code == CODE_TIMEOUT


def test_unavailable_error_maps_to_unavailable_code():
    err = to_mcp_error(AlarmApiUnavailableError("down"))
    assert err.error.code == CODE_UNAVAILABLE


def test_generic_alarm_api_error_maps_to_unknown_code():
    err = to_mcp_error(AlarmApiError("something else"))
    assert err.error.code == CODE_UNKNOWN


def test_error_messages_never_contain_the_word_bearer_token_value():
    # Defensive: even though our exceptions never embed the token, guard
    # against a future regression leaking it into an error message.
    err = to_mcp_error(AlarmApiAuthError("Authentication failed calling /alarms (status 401)"))
    assert "demo-token" not in err.error.message
