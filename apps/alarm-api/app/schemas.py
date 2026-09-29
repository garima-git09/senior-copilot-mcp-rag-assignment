"""Pydantic request schemas for the Alarm Management API simulator.

These mirror the JSON bodies used in the reference Postman collections
exactly (field names and nesting), so the simulator is a faithful
implementation of the documented contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    start_time: str
    end_time: str


class AlarmSummaryRequest(BaseModel):
    asset_ids: list[str] | None = None
    site: str | None = None
    unit: str | None = None
    time_range: TimeRange
    severity: list[str] | None = None
    alarm_types: list[str] | None = None
    group_by: list[str] = Field(default_factory=lambda: ["alarm_name"])
    kpis: list[str] = Field(default_factory=lambda: ["alarm_count"])


class AlarmTrendsRequest(BaseModel):
    asset_ids: list[str] | None = None
    site: str | None = None
    unit: str | None = None
    time_range: TimeRange
    bucket: Literal["hourly", "daily", "weekly"] = "daily"
    metrics: list[str] = Field(default_factory=lambda: ["alarm_count"])


class AlarmCorrelationRequest(BaseModel):
    asset_ids: list[str]
    time_range: TimeRange
    correlation_method: Literal["cooccurrence"] = "cooccurrence"
    lag_window_minutes: int = 15
    severity_threshold: str = "medium"
    min_support: int = 1


class FloodAnalysisRequest(BaseModel):
    unit: str | None = None
    site: str | None = None
    time_range: TimeRange
    threshold_count: int = 10
    rolling_window_minutes: int = 10


class RationalizationRequest(BaseModel):
    asset_ids: list[str] | None = None
    site: str | None = None
    unit: str | None = None
    time_range: TimeRange
    recurrence_threshold: int = 5
    stale_minutes_threshold: int = 180


class PriorityScoreRequest(BaseModel):
    alarm_id: str


class OperatorRecommendationsRequest(BaseModel):
    alarm_id: str
    include_related: bool = True
    include_asset_context: bool = False
    include_historical_pattern: bool = False


class CalculationGenerateRequest(BaseModel):
    calculation_type: Literal[
        "alarm_flood_index",
        "critical_alarm_density",
        "operator_response_efficiency",
        "nuisance_alarm_score",
    ]
    filters: dict = Field(default_factory=dict)


class CalculationExecuteRequest(BaseModel):
    calculation_id: str
    filters: dict = Field(default_factory=dict)
