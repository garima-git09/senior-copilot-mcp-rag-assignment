"""Async HTTP connector for the Alarm Management API simulator.

This is the *only* place that speaks raw HTTP to the Alarm Management API.
It is deliberately reusable: the alarm-management MCP server is the sole
caller in this system, but the connector itself has no MCP-specific code,
so it could back a second MCP server or a batch job unchanged.

Responsibilities:
    - Bearer authentication
    - Correlation/trace header propagation (trace_id, x-client-id, x-metadata-tag)
    - Timeout + retry with exponential backoff on transient failures
    - Mapping transport/HTTP failures into typed exceptions
    - Never logging the bearer token
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import httpx

from connectors.alarm_api.config import AlarmApiConfig
from connectors.alarm_api.exceptions import (
    AlarmApiAuthError,
    AlarmApiError,
    AlarmApiNotFoundError,
    AlarmApiTimeoutError,
    AlarmApiUnavailableError,
    AlarmApiValidationError,
)

logger = logging.getLogger("connectors.alarm_api")

_RETRYABLE_STATUS_CODES = {502, 503, 504}


class AlarmApiClient:
    def __init__(
        self,
        config: AlarmApiConfig | None = None,
        client_id: str = "alarm-mcp-server",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config or AlarmApiConfig()
        self.client_id = client_id
        # `transport` is only set in tests, to point at an in-process ASGI app
        # (httpx.ASGITransport) instead of opening a real socket. Production
        # code never sets it, so runtime behavior is unchanged.
        self._transport = transport

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        trace_id = trace_id or f"trace-{uuid.uuid4().hex[:12]}"
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "trace_id": trace_id,
            "x-client-id": self.client_id,
            "x-metadata-tag": "alarm-mcp-server",
        }

        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(base_url=self.config.base_url, timeout=self.config.timeout_seconds, transport=self._transport) as client:
                    response = await client.request(method, path, params=params, json=json_body, headers=headers)
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning("alarm_api_timeout path=%s attempt=%s trace_id=%s", path, attempt, trace_id)
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_backoff_seconds * attempt)
                    continue
                raise AlarmApiTimeoutError(f"Timed out calling {path} after {attempt} attempt(s)") from exc
            except httpx.ConnectError as exc:
                last_error = exc
                logger.warning("alarm_api_unreachable path=%s attempt=%s trace_id=%s", path, attempt, trace_id)
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_backoff_seconds * attempt)
                    continue
                raise AlarmApiUnavailableError(f"Alarm Management API unreachable at {self.config.base_url}") from exc

            if response.status_code in _RETRYABLE_STATUS_CODES and attempt < self.config.max_retries:
                logger.warning(
                    "alarm_api_retryable_status path=%s status=%s attempt=%s trace_id=%s",
                    path,
                    response.status_code,
                    attempt,
                    trace_id,
                )
                await asyncio.sleep(self.config.retry_backoff_seconds * attempt)
                continue

            return self._handle_response(response, path)

        raise AlarmApiUnavailableError(f"Exhausted retries calling {path}") from last_error

    @staticmethod
    def _handle_response(response: httpx.Response, path: str) -> dict[str, Any]:
        if response.status_code in (401, 403):
            raise AlarmApiAuthError(f"Authentication failed calling {path} (status {response.status_code})")
        if response.status_code == 404:
            raise AlarmApiNotFoundError(f"Resource not found at {path}")
        if response.status_code in (400, 422):
            detail = _safe_detail(response)
            raise AlarmApiValidationError(f"Invalid request to {path}: {detail}")
        if response.status_code >= 500:
            raise AlarmApiUnavailableError(f"Alarm Management API error {response.status_code} calling {path}")
        if response.status_code >= 400:
            raise AlarmApiError(f"Unexpected status {response.status_code} calling {path}")
        return response.json()

    # ------------------------------------------------------------------ #
    # Typed operations (one per Alarm Management API capability used by
    # the MCP server's tools)
    # ------------------------------------------------------------------ #
    async def search_assets(self, query: str, unit: str | None = None, site: str | None = None, limit: int = 10, trace_id: str | None = None) -> dict:
        params: dict[str, Any] = {"query": query, "limit": limit}
        if unit:
            params["unit"] = unit
        if site:
            params["site"] = site
        return await self._request("GET", "/assets/search", params=params, trace_id=trace_id)

    async def get_asset_metadata(self, asset_id: str, trace_id: str | None = None) -> dict:
        return await self._request("GET", f"/assets/{asset_id}/metadata", trace_id=trace_id)

    async def list_alarms(
        self,
        asset_id: str | None = None,
        site: str | None = None,
        unit: str | None = None,
        status: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "start_time",
        sort_order: str = "desc",
        trace_id: str | None = None,
    ) -> dict:
        params = {
            "asset_id": asset_id,
            "site": site,
            "unit": unit,
            "status": status,
            "start_time": start_time,
            "end_time": end_time,
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        params = {k: v for k, v in params.items() if v is not None}
        return await self._request("GET", "/alarms", params=params, trace_id=trace_id)

    async def get_alarm(self, alarm_id: str, trace_id: str | None = None) -> dict:
        return await self._request("GET", f"/alarms/{alarm_id}", trace_id=trace_id)

    async def alarm_summary(self, body: dict[str, Any], trace_id: str | None = None) -> dict:
        return await self._request("POST", "/alarms/summary", json_body=body, trace_id=trace_id)

    async def alarm_trends(self, body: dict[str, Any], trace_id: str | None = None) -> dict:
        return await self._request("POST", "/alarms/trends", json_body=body, trace_id=trace_id)

    async def alarm_correlation(self, body: dict[str, Any], trace_id: str | None = None) -> dict:
        return await self._request("POST", "/alarms/correlation", json_body=body, trace_id=trace_id)

    async def flood_analysis(self, body: dict[str, Any], trace_id: str | None = None) -> dict:
        return await self._request("POST", "/alarms/flood-analysis", json_body=body, trace_id=trace_id)

    async def rationalization_candidates(self, body: dict[str, Any], trace_id: str | None = None) -> dict:
        return await self._request("POST", "/alarms/rationalization-candidates", json_body=body, trace_id=trace_id)

    async def priority_score(self, alarm_id: str, trace_id: str | None = None) -> dict:
        return await self._request("POST", "/alarms/priority-score", json_body={"alarm_id": alarm_id}, trace_id=trace_id)

    async def operator_recommendations(self, body: dict[str, Any], trace_id: str | None = None) -> dict:
        return await self._request("POST", "/recommendations/operator-actions", json_body=body, trace_id=trace_id)

    async def generate_calculation(self, body: dict[str, Any], trace_id: str | None = None) -> dict:
        return await self._request("POST", "/calculation-code/generate", json_body=body, trace_id=trace_id)

    async def execute_calculation(self, body: dict[str, Any], trace_id: str | None = None) -> dict:
        return await self._request("POST", "/calculation-code/execute", json_body=body, trace_id=trace_id)

    async def kpi_definitions(self, trace_id: str | None = None) -> dict:
        return await self._request("GET", "/analytics/kpi-definitions", trace_id=trace_id)


def _safe_detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("message", response.text))[:300]
    except Exception:
        return response.text[:300]
