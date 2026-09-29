"""Alarm Management MCP server.

Exposes a curated set of Alarm Management API capabilities as MCP tools:
asset search & metadata, alarm retrieval, summary/trend analytics, and the
advanced operations (correlation, flood analysis, rationalization,
priority scoring, operator recommendations, KPI calculation catalog).

Design notes
------------
- Every tool has a typed input schema (Pydantic models / typed parameters,
  see server/schemas.py) and a typed output schema (Pydantic output models
  where the shape is fixed; a documented `dict` passthrough where the shape
  is dynamic, e.g. group-by summaries).
- Every tool validates its inputs before calling the Alarm Management API
  (FastMCP performs this from the type annotations; we add explicit field
  constraints via `Field(...)`).
- Every tool call generates (or receives, via the MCP request context) a
  trace_id that is propagated to the Alarm Management API and returned to
  the caller, so a single investigation can be followed end-to-end.
- Every failure from the connector is mapped to a typed `McpError`
  (server/errors.py) -- callers never see a raw stack trace or an HTTP
  status code.
- The bearer token used to call the Alarm Management API lives only in the
  connector's config (from an environment variable) and is never included
  in a tool response or a log line.

Run standalone:
    python -m server.app
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from connectors.alarm_api.client import AlarmApiClient
from connectors.alarm_api.config import AlarmApiConfig
from connectors.alarm_api.exceptions import AlarmApiError
from server.config import settings
from server.errors import to_mcp_error
from server.schemas import (
    AlarmRecord,
    GetAlarmsOutput,
    GetAlarmSummaryOutput,
    GetAssetMetadataOutput,
    Pagination,
    ScoreAlarmPriorityOutput,
    TimeRangeArgs,
)

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("alarm_mcp_server")

mcp = FastMCP(
    name="alarm-management",
    instructions=(
        "Tools for investigating industrial plant alarms: resolve asset names to IDs, "
        "retrieve active/historical alarms, run correlation/priority/rationalization "
        "analytics, and get operator recommendations. Always resolve an asset name via "
        "search_assets before calling tools that require an asset_id."
    ),
    host=settings.host,
    port=settings.port,
)

_client = AlarmApiClient(AlarmApiConfig())


def _trace_id(ctx: Context | None) -> str:
    """Derive a trace id for this tool call. Reuses the MCP request id when
    available so a whole client session can be correlated, and always logs
    without ever including the Authorization header/token.
    """
    if ctx is not None:
        try:
            return f"trace-mcp-{ctx.request_id}"
        except Exception:  # pragma: no cover - defensive, ctx always has request_id in practice
            pass
    return f"trace-mcp-{uuid.uuid4().hex[:12]}"


async def _call(coro_factory, tool_name: str, trace_id: str):
    logger.info("tool_call_started tool=%s trace_id=%s", tool_name, trace_id)
    try:
        result = await coro_factory()
    except AlarmApiError as exc:
        logger.warning("tool_call_failed tool=%s trace_id=%s error=%s", tool_name, trace_id, exc)
        raise to_mcp_error(exc) from exc
    logger.info("tool_call_succeeded tool=%s trace_id=%s", tool_name, trace_id)
    return result


# --------------------------------------------------------------------------- #
# Asset search
# --------------------------------------------------------------------------- #
@mcp.tool(
    name="search_assets",
    description=(
        "Resolve a free-text asset name or keyword (e.g. 'Boiler Feed Pump 101', "
        "'compressor') to one or more asset identifiers. Always call this first "
        "when the user refers to an asset by name."
    ),
)
async def search_assets(
    query: Annotated[str, Field(min_length=1, description="Asset name or keyword to search for")],
    unit: Annotated[str | None, Field(default=None, description="Optional unit filter, e.g. 'Unit 2'")] = None,
    site: Annotated[str | None, Field(default=None, description="Optional site filter, e.g. 'EastRefinery'")] = None,
    limit: Annotated[int, Field(default=10, ge=1, le=100)] = 10,
    ctx: Context | None = None,
) -> dict[str, Any]:
    trace_id = _trace_id(ctx)
    result = await _call(lambda: _client.search_assets(query, unit, site, limit, trace_id), "search_assets", trace_id)
    result["trace_id"] = trace_id
    return result


# --------------------------------------------------------------------------- #
# Asset metadata
# --------------------------------------------------------------------------- #
@mcp.tool(
    name="get_asset_metadata",
    description="Fetch metadata for a resolved asset_id: type, site, unit, criticality, manufacturer, and related assets to inspect.",
)
async def get_asset_metadata(
    asset_id: Annotated[str, Field(min_length=1, description="Asset identifier from search_assets")],
    ctx: Context | None = None,
) -> GetAssetMetadataOutput:
    trace_id = _trace_id(ctx)
    data = await _call(lambda: _client.get_asset_metadata(asset_id, trace_id), "get_asset_metadata", trace_id)
    return GetAssetMetadataOutput(**data)


# --------------------------------------------------------------------------- #
# Alarm retrieval
# --------------------------------------------------------------------------- #
@mcp.tool(
    name="get_alarms",
    description="Retrieve active or historical alarms with filtering (asset, site, unit, status, time window) and pagination.",
)
async def get_alarms(
    asset_id: Annotated[str | None, Field(default=None)] = None,
    site: Annotated[str | None, Field(default=None)] = None,
    unit: Annotated[str | None, Field(default=None)] = None,
    status: Annotated[Literal["active", "cleared"] | None, Field(default=None)] = None,
    start_time: Annotated[str | None, Field(default=None, description="ISO-8601 lower bound")] = None,
    end_time: Annotated[str | None, Field(default=None, description="ISO-8601 upper bound")] = None,
    page: Annotated[int, Field(default=1, ge=1)] = 1,
    page_size: Annotated[int, Field(default=50, ge=1, le=500)] = 50,
    sort_by: Annotated[str, Field(default="start_time")] = "start_time",
    sort_order: Annotated[Literal["asc", "desc"], Field(default="desc")] = "desc",
    ctx: Context | None = None,
) -> GetAlarmsOutput:
    trace_id = _trace_id(ctx)
    data = await _call(
        lambda: _client.list_alarms(asset_id, site, unit, status, start_time, end_time, page, page_size, sort_by, sort_order, trace_id),
        "get_alarms",
        trace_id,
    )
    return GetAlarmsOutput(data=[AlarmRecord(**a) for a in data["data"]], pagination=Pagination(**data["pagination"]))


@mcp.tool(
    name="get_alarm_by_id",
    description="Fetch full detail for a single alarm by its alarm_id.",
)
async def get_alarm_by_id(
    alarm_id: Annotated[str, Field(min_length=1)],
    ctx: Context | None = None,
) -> AlarmRecord:
    trace_id = _trace_id(ctx)
    data = await _call(lambda: _client.get_alarm(alarm_id, trace_id), "get_alarm_by_id", trace_id)
    return AlarmRecord(**data)


# --------------------------------------------------------------------------- #
# Summary / trend analytics
# --------------------------------------------------------------------------- #
@mcp.tool(
    name="get_alarm_summary",
    description=(
        "Summarize alarms over a time window, grouped by fields such as alarm_name, "
        "asset_id, or severity, with KPIs such as alarm_count, recurring_rate, "
        "avg_ack_delay. Use this to identify which alarms are recurring most often."
    ),
)
async def get_alarm_summary(
    time_range: TimeRangeArgs,
    asset_ids: Annotated[list[str] | None, Field(default=None)] = None,
    site: Annotated[str | None, Field(default=None)] = None,
    unit: Annotated[str | None, Field(default=None)] = None,
    severity: Annotated[list[str] | None, Field(default=None, description="e.g. ['high', 'critical']")] = None,
    alarm_types: Annotated[list[str] | None, Field(default=None)] = None,
    group_by: list[str] = Field(default=["alarm_name"], description="Fields to group by, e.g. ['alarm_name'] or ['asset_id', 'severity']"),
    kpis: list[str] = Field(default=["alarm_count", "recurring_rate", "avg_ack_delay"], description="KPIs to compute per group"),
    ctx: Context | None = None,
) -> GetAlarmSummaryOutput:
    trace_id = _trace_id(ctx)
    body = {
        "asset_ids": asset_ids,
        "site": site,
        "unit": unit,
        "time_range": time_range.model_dump(),
        "severity": severity,
        "alarm_types": alarm_types,
        "group_by": list(group_by),
        "kpis": list(kpis),
    }
    data = await _call(lambda: _client.alarm_summary(body, trace_id), "get_alarm_summary", trace_id)
    return GetAlarmSummaryOutput(**data)


@mcp.tool(
    name="get_alarm_trends",
    description="Return a time-bucketed series (hourly/daily/weekly) of alarm metrics for trend analysis.",
)
async def get_alarm_trends(
    time_range: TimeRangeArgs,
    asset_ids: Annotated[list[str] | None, Field(default=None)] = None,
    site: Annotated[str | None, Field(default=None)] = None,
    unit: Annotated[str | None, Field(default=None)] = None,
    bucket: Annotated[Literal["hourly", "daily", "weekly"], Field(default="daily")] = "daily",
    metrics: list[str] = Field(default=["alarm_count", "avg_ack_delay"], description="Metrics to compute per bucket"),
    ctx: Context | None = None,
) -> dict[str, Any]:
    trace_id = _trace_id(ctx)
    body = {
        "asset_ids": asset_ids,
        "site": site,
        "unit": unit,
        "time_range": time_range.model_dump(),
        "bucket": bucket,
        "metrics": list(metrics),
    }
    data = await _call(lambda: _client.alarm_trends(body, trace_id), "get_alarm_trends", trace_id)
    data["trace_id"] = trace_id
    return data


# --------------------------------------------------------------------------- #
# Advanced operations
# --------------------------------------------------------------------------- #
@mcp.tool(
    name="correlate_alarms",
    description=(
        "Find alarms across a set of assets that co-occur within a lag window. Useful "
        "to identify likely contributing factors / related alarms for a root-cause "
        "investigation."
    ),
)
async def correlate_alarms(
    asset_ids: Annotated[list[str], Field(min_length=1, description="Two or more asset identifiers")],
    time_range: TimeRangeArgs,
    correlation_method: Annotated[Literal["cooccurrence"], Field(default="cooccurrence")] = "cooccurrence",
    lag_window_minutes: Annotated[int, Field(default=15, ge=1, le=1440)] = 15,
    severity_threshold: Annotated[str, Field(default="medium")] = "medium",
    min_support: Annotated[int, Field(default=1, ge=1)] = 1,
    ctx: Context | None = None,
) -> dict[str, Any]:
    trace_id = _trace_id(ctx)
    body = {
        "asset_ids": asset_ids,
        "time_range": time_range.model_dump(),
        "correlation_method": correlation_method,
        "lag_window_minutes": lag_window_minutes,
        "severity_threshold": severity_threshold,
        "min_support": min_support,
    }
    data = await _call(lambda: _client.alarm_correlation(body, trace_id), "correlate_alarms", trace_id)
    data["trace_id"] = trace_id
    return data


@mcp.tool(
    name="analyze_alarm_flood",
    description="Detect alarm-flood windows (bursts of alarms exceeding a threshold within a rolling window) for a unit or site.",
)
async def analyze_alarm_flood(
    time_range: TimeRangeArgs,
    unit: Annotated[str | None, Field(default=None)] = None,
    site: Annotated[str | None, Field(default=None)] = None,
    threshold_count: Annotated[int, Field(default=10, ge=1)] = 10,
    rolling_window_minutes: Annotated[int, Field(default=10, ge=1)] = 10,
    ctx: Context | None = None,
) -> dict[str, Any]:
    trace_id = _trace_id(ctx)
    body = {
        "unit": unit,
        "site": site,
        "time_range": time_range.model_dump(),
        "threshold_count": threshold_count,
        "rolling_window_minutes": rolling_window_minutes,
    }
    data = await _call(lambda: _client.flood_analysis(body, trace_id), "analyze_alarm_flood", trace_id)
    data["trace_id"] = trace_id
    return data


@mcp.tool(
    name="get_rationalization_candidates",
    description="Identify alarms that are candidates for rationalization (nuisance/high-recurrence or slow-to-acknowledge) over a time window.",
)
async def get_rationalization_candidates(
    time_range: TimeRangeArgs,
    asset_ids: Annotated[list[str] | None, Field(default=None)] = None,
    site: Annotated[str | None, Field(default=None)] = None,
    unit: Annotated[str | None, Field(default=None)] = None,
    recurrence_threshold: Annotated[int, Field(default=5, ge=1)] = 5,
    stale_minutes_threshold: Annotated[int, Field(default=180, ge=1)] = 180,
    ctx: Context | None = None,
) -> dict[str, Any]:
    trace_id = _trace_id(ctx)
    body = {
        "asset_ids": asset_ids,
        "site": site,
        "unit": unit,
        "time_range": time_range.model_dump(),
        "recurrence_threshold": recurrence_threshold,
        "stale_minutes_threshold": stale_minutes_threshold,
    }
    data = await _call(lambda: _client.rationalization_candidates(body, trace_id), "get_rationalization_candidates", trace_id)
    data["trace_id"] = trace_id
    return data


@mcp.tool(
    name="score_alarm_priority",
    description=(
        "Compute a 0-100 priority score and band (low/medium/high/critical) for a single alarm, "
        "combining severity, asset criticality, and acknowledgement delay."
    ),
)
async def score_alarm_priority(
    alarm_id: Annotated[str, Field(min_length=1)],
    ctx: Context | None = None,
) -> ScoreAlarmPriorityOutput:
    trace_id = _trace_id(ctx)
    data = await _call(lambda: _client.priority_score(alarm_id, trace_id), "score_alarm_priority", trace_id)
    return ScoreAlarmPriorityOutput(**data)


@mcp.tool(
    name="get_operator_recommendations",
    description="Get recommended operator actions for an alarm, optionally including related assets, asset context, and historical recurrence pattern.",
)
async def get_operator_recommendations(
    alarm_id: Annotated[str, Field(min_length=1)],
    include_related: Annotated[bool, Field(default=True)] = True,
    include_asset_context: Annotated[bool, Field(default=False)] = False,
    include_historical_pattern: Annotated[bool, Field(default=False)] = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    trace_id = _trace_id(ctx)
    body = {
        "alarm_id": alarm_id,
        "include_related": include_related,
        "include_asset_context": include_asset_context,
        "include_historical_pattern": include_historical_pattern,
    }
    data = await _call(lambda: _client.operator_recommendations(body, trace_id), "get_operator_recommendations", trace_id)
    data["trace_id"] = trace_id
    return data


@mcp.tool(
    name="generate_calculation",
    description="Step 1 of a two-step KPI calculation flow: register a calculation_type and filters, returns a calculation_id to pass to execute_calculation.",
)
async def generate_calculation(
    calculation_type: Annotated[
        Literal["alarm_flood_index", "critical_alarm_density", "operator_response_efficiency", "nuisance_alarm_score"],
        Field(...),
    ],
    filters: dict[str, Any] = Field(default={}, description="Additional/override filters"),
    ctx: Context | None = None,
) -> dict[str, Any]:
    trace_id = _trace_id(ctx)
    body = {"calculation_type": calculation_type, "filters": filters}
    data = await _call(lambda: _client.generate_calculation(body, trace_id), "generate_calculation", trace_id)
    data["trace_id"] = trace_id
    return data


@mcp.tool(
    name="execute_calculation",
    description="Step 2 of the KPI calculation flow: execute a calculation_id (from generate_calculation) with optional additional filters.",
)
async def execute_calculation(
    calculation_id: Annotated[str, Field(min_length=1, description="Value returned by generate_calculation")],
    filters: dict[str, Any] = Field(default={}, description="Additional/override filters"),
    ctx: Context | None = None,
) -> dict[str, Any]:
    trace_id = _trace_id(ctx)
    body = {"calculation_id": calculation_id, "filters": filters}
    data = await _call(lambda: _client.execute_calculation(body, trace_id), "execute_calculation", trace_id)
    data["trace_id"] = trace_id
    return data


@mcp.tool(
    name="get_kpi_definitions",
    description="List the KPI definitions supported by the Alarm Management API (alarm_count, recurring_rate, avg_ack_delay, etc.).",
)
async def get_kpi_definitions(ctx: Context | None = None) -> dict[str, Any]:
    trace_id = _trace_id(ctx)
    data = await _call(lambda: _client.kpi_definitions(trace_id), "get_kpi_definitions", trace_id)
    data["trace_id"] = trace_id
    return data


def main() -> None:
    mcp.run(transport=settings.transport)


if __name__ == "__main__":
    main()
