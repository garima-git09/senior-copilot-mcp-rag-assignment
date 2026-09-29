"""Unit tests for the Alarm Management API connector (connectors/alarm_api),
using an in-process ASGI transport so no real network/socket is involved.
"""

from __future__ import annotations

import pytest

from connectors.alarm_api.client import AlarmApiClient
from connectors.alarm_api.config import AlarmApiConfig
from connectors.alarm_api.exceptions import (
    AlarmApiAuthError,
    AlarmApiNotFoundError,
    AlarmApiTimeoutError,
    AlarmApiUnavailableError,
)


@pytest.mark.asyncio
async def test_search_assets_success(alarm_api_client: AlarmApiClient):
    result = await alarm_api_client.search_assets("Boiler Feed Pump 101")
    assert result["count"] >= 1


@pytest.mark.asyncio
async def test_wrong_token_raises_auth_error(alarm_api_asgi_transport):
    client = AlarmApiClient(AlarmApiConfig(base_url="http://alarm-api.test", token="wrong-token", max_retries=1), transport=alarm_api_asgi_transport)
    with pytest.raises(AlarmApiAuthError):
        await client.search_assets("pump")


@pytest.mark.asyncio
async def test_missing_asset_raises_not_found(alarm_api_client: AlarmApiClient):
    with pytest.raises(AlarmApiNotFoundError):
        await alarm_api_client.get_asset_metadata("AST-does-not-exist")


@pytest.mark.asyncio
async def test_connection_failure_raises_unavailable_after_retries():
    # No transport override -> real networking to an address nothing listens on.
    # On Linux, connecting to a loopback port with nothing listening usually
    # fails immediately with ECONNREFUSED, which the connector maps to
    # AlarmApiUnavailableError. On Windows, the same connection attempt often
    # does not refuse immediately -- it hangs until the configured timeout
    # elapses instead, which the connector correctly maps to
    # AlarmApiTimeoutError. Both are genuine, correctly-typed "the Alarm API
    # could not be reached after retries" outcomes; which one fires is a
    # platform-dependent TCP stack behavior, not something the connector
    # controls or should be expected to normalize away. This test accepts
    # either so it is reliable on both platforms.
    config = AlarmApiConfig(base_url="http://127.0.0.1:1", token="demo-token", max_retries=2, retry_backoff_seconds=0.01, timeout_seconds=1)
    client = AlarmApiClient(config)
    with pytest.raises((AlarmApiUnavailableError, AlarmApiTimeoutError)):
        await client.search_assets("pump")


@pytest.mark.asyncio
async def test_config_redacted_never_includes_token():
    config = AlarmApiConfig(token="super-secret-value")
    assert "super-secret-value" not in str(config.redacted())
    assert config.redacted()["token"] == "***redacted***"
