"""Typed input and output schemas for every MCP tool exposed by the
alarm-management server. Pydantic models double as the MCP tool's JSON
Schema (input) and structured-content schema (output), and as validators
that run before any call reaches the Alarm Management API.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TimeRangeArgs(BaseModel):
    start_time: str = Field(..., description="ISO-8601 start of the window, e.g. 2026-05-01T00:00:00Z")
    end_time: str = Field(..., description="ISO-8601 end of the window, e.g. 2026-07-01T00:00:00Z")


# --------------------------------------------------------------------------- #
# search_assets
# --------------------------------------------------------------------------- #
class SearchAssetsInput(BaseModel):
    query: str = Field(..., min_length=1, description="Free-text asset name or keyword, e.g. 'Boiler Feed Pump 101' or 'compressor'")
    unit: str | None = Field(default=None, description="Optional unit filter, e.g. 'Unit 2'")
    site: str | None = Field(default=None, description="Optional site filter, e.g. 'EastRefinery'")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of matches to return")


class AssetSummary(BaseModel):
    asset_id: str
    asset_name: str
    asset_type: str
    site: str
    unit: str
    criticality: str


class SearchAssetsOutput(BaseModel):
    query: str
    count: int
    results: list[AssetSummary]


# --------------------------------------------------------------------------- #
# get_asset_metadata
# --------------------------------------------------------------------------- #
class GetAssetMetadataInput(BaseModel):
    asset_id: str = Field(..., min_length=1, description="Asset identifier returned by search_assets, e.g. AST-1234567890")


class GetAssetMetadataOutput(BaseModel):
    asset_id: str
    asset_name: str
    asset_type: str
    site: str
    unit: str
    criticality: str
    manufacturer: str
    installed_on: str
    related_assets: list[str]
    tags: list[str]


# --------------------------------------------------------------------------- #
# get_alarms
# --------------------------------------------------------------------------- #
class GetAlarmsInput(BaseModel):
    asset_id: str | None = Field(default=None, description="Filter by asset identifier")
    site: str | None = Field(default=None, description="Filter by site name")
    unit: str | None = Field(default=None, description="Filter by unit name")
    status: Literal["active", "cleared"] | None = Field(default=None, description="Filter by alarm status")
    start_time: str | None = Field(default=None, description="ISO-8601 lower bound on alarm start_time")
    end_time: str | None = Field(default=None, description="ISO-8601 upper bound on alarm start_time")
    page: int = Field(default=1, ge=1, description="1-based page number")
    page_size: int = Field(default=50, ge=1, le=500, description="Number of alarms per page")
    sort_by: str = Field(default="start_time", description="Field to sort by")
    sort_order: Literal["asc", "desc"] = Field(default="desc")


class AlarmRecord(BaseModel):
    alarm_id: str
    asset_id: str
    asset_name: str
    site: str
    unit: str
    alarm_name: str
    alarm_type: str
    severity: str
    status: str
    start_time: str
    cleared_time: str | None = None
    acknowledged_time: str
    ack_delay_minutes: float
    value: float
    threshold: float


class Pagination(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class GetAlarmsOutput(BaseModel):
    data: list[AlarmRecord]
    pagination: Pagination


# --------------------------------------------------------------------------- #
# get_alarm_by_id
# --------------------------------------------------------------------------- #
class GetAlarmByIdInput(BaseModel):
    alarm_id: str = Field(..., min_length=1)


# --------------------------------------------------------------------------- #
# get_alarm_summary
# --------------------------------------------------------------------------- #
class GetAlarmSummaryInput(BaseModel):
    asset_ids: list[str] | None = Field(default=None, description="Restrict to these asset identifiers")
    site: str | None = None
    unit: str | None = None
    time_range: TimeRangeArgs
    severity: list[str] | None = Field(default=None, description="e.g. ['high', 'critical']")
    alarm_types: list[str] | None = None
    group_by: list[str] = Field(default_factory=lambda: ["alarm_name"])
    kpis: list[str] = Field(default_factory=lambda: ["alarm_count", "recurring_rate", "avg_ack_delay"])


class GetAlarmSummaryOutput(BaseModel):
    time_range: dict[str, str]
    group_by: list[str]
    kpis: list[str]
    total_alarms: int
    groups: list[dict[str, Any]]


# --------------------------------------------------------------------------- #
# get_alarm_trends
# --------------------------------------------------------------------------- #
class GetAlarmTrendsInput(BaseModel):
    asset_ids: list[str] | None = None
    site: str | None = None
    unit: str | None = None
    time_range: TimeRangeArgs
    bucket: Literal["hourly", "daily", "weekly"] = "daily"
    metrics: list[str] = Field(default_factory=lambda: ["alarm_count", "avg_ack_delay"])


# --------------------------------------------------------------------------- #
# correlate_alarms
# --------------------------------------------------------------------------- #
class CorrelateAlarmsInput(BaseModel):
    asset_ids: list[str] = Field(..., min_length=1, description="Two or more asset identifiers to correlate alarms across")
    time_range: TimeRangeArgs
    correlation_method: Literal["cooccurrence"] = "cooccurrence"
    lag_window_minutes: int = Field(default=15, ge=1, le=1440)
    severity_threshold: str = Field(default="medium")
    min_support: int = Field(default=1, ge=1)


# --------------------------------------------------------------------------- #
# analyze_alarm_flood
# --------------------------------------------------------------------------- #
class AnalyzeAlarmFloodInput(BaseModel):
    unit: str | None = None
    site: str | None = None
    time_range: TimeRangeArgs
    threshold_count: int = Field(default=10, ge=1)
    rolling_window_minutes: int = Field(default=10, ge=1)


# --------------------------------------------------------------------------- #
# get_rationalization_candidates
# --------------------------------------------------------------------------- #
class GetRationalizationCandidatesInput(BaseModel):
    asset_ids: list[str] | None = None
    site: str | None = None
    unit: str | None = None
    time_range: TimeRangeArgs
    recurrence_threshold: int = Field(default=5, ge=1)
    stale_minutes_threshold: int = Field(default=180, ge=1)


# --------------------------------------------------------------------------- #
# score_alarm_priority
# --------------------------------------------------------------------------- #
class ScoreAlarmPriorityInput(BaseModel):
    alarm_id: str = Field(..., min_length=1)


class ScoreAlarmPriorityOutput(BaseModel):
    alarm_id: str
    asset_id: str
    priority_score: float
    priority_band: str
    components: dict[str, float]


# --------------------------------------------------------------------------- #
# get_operator_recommendations
# --------------------------------------------------------------------------- #
class GetOperatorRecommendationsInput(BaseModel):
    alarm_id: str = Field(..., min_length=1)
    include_related: bool = True
    include_asset_context: bool = False
    include_historical_pattern: bool = False


# --------------------------------------------------------------------------- #
# generate_calculation / execute_calculation (two-step KPI chaining)
# --------------------------------------------------------------------------- #
class GenerateCalculationInput(BaseModel):
    calculation_type: Literal[
        "alarm_flood_index",
        "critical_alarm_density",
        "operator_response_efficiency",
        "nuisance_alarm_score",
    ]
    filters: dict[str, Any] = Field(default_factory=dict)


class ExecuteCalculationInput(BaseModel):
    calculation_id: str = Field(..., min_length=1, description="Identifier returned by generate_calculation")
    filters: dict[str, Any] = Field(default_factory=dict)


class GetKpiDefinitionsInput(BaseModel):
    pass
