"""Query and analytics logic operating over the in-memory seed database.

Every function here is pure (dict/list in, dict/list out) which keeps the
FastAPI routers in main.py thin and keeps this module trivially unit
testable without spinning up HTTP.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from app.schemas import (
    AlarmCorrelationRequest,
    AlarmSummaryRequest,
    AlarmTrendsRequest,
    CalculationExecuteRequest,
    CalculationGenerateRequest,
    FloodAnalysisRequest,
    OperatorRecommendationsRequest,
    PriorityScoreRequest,
    RationalizationRequest,
)
from app.seed_data import DB, SEVERITY_RANK


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _in_range(alarm: dict[str, Any], start: datetime, end: datetime) -> bool:
    return start <= _parse(alarm["start_time"]) <= end


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Assets
# --------------------------------------------------------------------------- #
def search_assets(query: str, unit: str | None = None, site: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    q = query.lower().strip()
    results = []
    for asset in DB.assets.values():
        haystack = f"{asset['asset_name']} {asset['asset_type']}".lower()
        if q and q not in haystack:
            continue
        if unit and asset["unit"].lower() != unit.lower():
            continue
        if site and asset["site"].lower() != site.lower():
            continue
        results.append(asset)
    return results[:limit]


def get_asset_metadata(asset_id: str) -> dict[str, Any]:
    asset = DB.assets.get(asset_id)
    if asset is None:
        raise NotFoundError(f"Asset '{asset_id}' not found")
    return asset


# --------------------------------------------------------------------------- #
# Alarms - list / detail
# --------------------------------------------------------------------------- #
def list_alarms(
    asset_id: str | None,
    site: str | None,
    unit: str | None,
    status: str | None,
    start_time: str | None,
    end_time: str | None,
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: str,
) -> tuple[list[dict[str, Any]], int]:
    if page < 1:
        raise ValidationError("page must be >= 1")
    if not (1 <= page_size <= 500):
        raise ValidationError("page_size must be between 1 and 500")

    rows = list(DB.alarms.values())
    if asset_id:
        rows = [a for a in rows if a["asset_id"] == asset_id]
    if site:
        rows = [a for a in rows if a["site"].lower() == site.lower()]
    if unit:
        rows = [a for a in rows if a["unit"].lower() == unit.lower()]
    if status:
        rows = [a for a in rows if a["status"] == status]
    if start_time:
        start = _parse(start_time)
        rows = [a for a in rows if _parse(a["start_time"]) >= start]
    if end_time:
        end = _parse(end_time)
        rows = [a for a in rows if _parse(a["start_time"]) <= end]

    reverse = sort_order == "desc"
    rows.sort(key=lambda a: a.get(sort_by, a["start_time"]), reverse=reverse)

    total = len(rows)
    offset = (page - 1) * page_size
    page_rows = rows[offset : offset + page_size]
    return page_rows, total


def get_alarm(alarm_id: str) -> dict[str, Any]:
    alarm = DB.alarms.get(alarm_id)
    if alarm is None:
        raise NotFoundError(f"Alarm '{alarm_id}' not found")
    return alarm


# --------------------------------------------------------------------------- #
# Filtering helper shared by the analytics endpoints
# --------------------------------------------------------------------------- #
def _filtered_alarms(
    asset_ids: list[str] | None,
    site: str | None,
    unit: str | None,
    start: datetime,
    end: datetime,
    severity: list[str] | None = None,
    alarm_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    rows = [a for a in DB.alarms.values() if _in_range(a, start, end)]
    if asset_ids:
        rows = [a for a in rows if a["asset_id"] in asset_ids]
    if site:
        rows = [a for a in rows if a["site"].lower() == site.lower()]
    if unit:
        rows = [a for a in rows if a["unit"].lower() == unit.lower()]
    if severity:
        wanted = {s.lower() for s in severity}
        rows = [a for a in rows if a["severity"].lower() in wanted]
    if alarm_types:
        wanted_types = {t.lower() for t in alarm_types}
        rows = [a for a in rows if a["alarm_type"].lower() in wanted_types]
    return rows


# --------------------------------------------------------------------------- #
# Alarm summary
# --------------------------------------------------------------------------- #
def alarm_summary(req: AlarmSummaryRequest) -> dict[str, Any]:
    start, end = _parse(req.time_range.start_time), _parse(req.time_range.end_time)
    rows = _filtered_alarms(req.asset_ids, req.site, req.unit, start, end, req.severity, req.alarm_types)

    def group_key(alarm: dict[str, Any]) -> tuple:
        return tuple(alarm.get(field, "") for field in req.group_by)

    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for alarm in rows:
        groups[group_key(alarm)].append(alarm)

    results = []
    for key, members in groups.items():
        entry: dict[str, Any] = dict(zip(req.group_by, key, strict=True))
        if "alarm_count" in req.kpis:
            entry["alarm_count"] = len(members)
        if "recurring_rate" in req.kpis:
            names = Counter(m["alarm_name"] for m in members)
            recurring = sum(c for c in names.values() if c > 1)
            entry["recurring_rate"] = round(recurring / len(members), 3) if members else 0.0
        if "avg_ack_delay" in req.kpis:
            entry["avg_ack_delay"] = round(sum(m["ack_delay_minutes"] for m in members) / len(members), 2) if members else 0.0
        if "critical_count" in req.kpis:
            entry["critical_count"] = sum(1 for m in members if m["severity"] == "critical")
        if "suppression_candidate_rate" in req.kpis:
            stale = sum(1 for m in members if m["status"] == "active")
            entry["suppression_candidate_rate"] = round(stale / len(members), 3) if members else 0.0
        results.append(entry)

    results.sort(key=lambda e: e.get("alarm_count", 0), reverse=True)
    return {
        "time_range": {"start_time": req.time_range.start_time, "end_time": req.time_range.end_time},
        "group_by": req.group_by,
        "kpis": req.kpis,
        "total_alarms": len(rows),
        "groups": results,
    }


# --------------------------------------------------------------------------- #
# Alarm trends
# --------------------------------------------------------------------------- #
_BUCKET_DELTA = {"hourly": timedelta(hours=1), "daily": timedelta(days=1), "weekly": timedelta(weeks=1)}


def alarm_trends(req: AlarmTrendsRequest) -> dict[str, Any]:
    start, end = _parse(req.time_range.start_time), _parse(req.time_range.end_time)
    rows = _filtered_alarms(req.asset_ids, req.site, req.unit, start, end)

    delta = _BUCKET_DELTA[req.bucket]
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for alarm in rows:
        ts = _parse(alarm["start_time"])
        bucket_start = start + ((ts - start) // delta) * delta
        buckets[bucket_start.isoformat()].append(alarm)

    series = []
    for bucket_start in sorted(buckets):
        members = buckets[bucket_start]
        point: dict[str, Any] = {"bucket_start": bucket_start}
        if "alarm_count" in req.metrics:
            point["alarm_count"] = len(members)
        if "avg_ack_delay" in req.metrics:
            point["avg_ack_delay"] = round(sum(m["ack_delay_minutes"] for m in members) / len(members), 2) if members else 0.0
        series.append(point)

    return {"bucket": req.bucket, "metrics": req.metrics, "series": series}


# --------------------------------------------------------------------------- #
# Correlation (co-occurrence within a lag window)
# --------------------------------------------------------------------------- #
def alarm_correlation(req: AlarmCorrelationRequest) -> dict[str, Any]:
    start, end = _parse(req.time_range.start_time), _parse(req.time_range.end_time)
    threshold_rank = SEVERITY_RANK.get(req.severity_threshold.lower(), 1)
    rows = [a for a in _filtered_alarms(req.asset_ids, None, None, start, end) if SEVERITY_RANK.get(a["severity"], 1) >= threshold_rank]
    rows.sort(key=lambda a: a["start_time"])

    window = timedelta(minutes=req.lag_window_minutes)
    pair_counts: Counter[tuple[str, str]] = Counter()
    for i, a in enumerate(rows):
        a_time = _parse(a["start_time"])
        for b in rows[i + 1 :]:
            b_time = _parse(b["start_time"])
            if b_time - a_time > window:
                break
            if a["asset_id"] == b["asset_id"] and a["alarm_name"] == b["alarm_name"]:
                continue
            pair = tuple(sorted([f"{a['asset_id']}::{a['alarm_name']}", f"{b['asset_id']}::{b['alarm_name']}"]))
            pair_counts[pair] += 1

    correlations = [
        {
            "pair": list(pair),
            "co_occurrences": count,
            "lag_window_minutes": req.lag_window_minutes,
        }
        for pair, count in pair_counts.items()
        if count >= req.min_support
    ]
    correlations.sort(key=lambda c: c["co_occurrences"], reverse=True)
    return {
        "correlation_method": req.correlation_method,
        "severity_threshold": req.severity_threshold,
        "asset_ids": req.asset_ids,
        "correlations": correlations,
        "total_alarms_considered": len(rows),
    }


# --------------------------------------------------------------------------- #
# Flood analysis
# --------------------------------------------------------------------------- #
def flood_analysis(req: FloodAnalysisRequest) -> dict[str, Any]:
    start, end = _parse(req.time_range.start_time), _parse(req.time_range.end_time)
    rows = _filtered_alarms(None, req.site, req.unit, start, end)
    rows.sort(key=lambda a: a["start_time"])

    window = timedelta(minutes=req.rolling_window_minutes)
    flood_windows = []
    i = 0
    times = [_parse(a["start_time"]) for a in rows]
    n = len(rows)
    while i < n:
        j = i
        while j < n and times[j] - times[i] <= window:
            j += 1
        count = j - i
        if count >= req.threshold_count:
            flood_windows.append(
                {
                    "start": times[i].isoformat().replace("+00:00", "Z"),
                    "end": times[j - 1].isoformat().replace("+00:00", "Z"),
                    "alarm_count": count,
                }
            )
            i = j
        else:
            i += 1

    return {
        "unit": req.unit,
        "site": req.site,
        "threshold_count": req.threshold_count,
        "rolling_window_minutes": req.rolling_window_minutes,
        "flood_windows": flood_windows,
        "total_alarms_considered": len(rows),
    }


# --------------------------------------------------------------------------- #
# Rationalization candidates
# --------------------------------------------------------------------------- #
def rationalization_candidates(req: RationalizationRequest) -> dict[str, Any]:
    start, end = _parse(req.time_range.start_time), _parse(req.time_range.end_time)
    rows = _filtered_alarms(req.asset_ids, req.site, req.unit, start, end)

    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for a in rows:
        by_key[(a["asset_id"], a["alarm_name"])].append(a)

    candidates = []
    for (asset_id, alarm_name), members in by_key.items():
        occurrences = len(members)
        avg_ack = sum(m["ack_delay_minutes"] for m in members) / occurrences
        stale_minutes = avg_ack
        reasons = []
        if occurrences >= req.recurrence_threshold:
            reasons.append("high_recurrence")
        if stale_minutes * 60 >= req.stale_minutes_threshold or avg_ack >= req.stale_minutes_threshold:
            reasons.append("slow_acknowledgement")
        if not reasons:
            continue
        candidates.append(
            {
                "asset_id": asset_id,
                "asset_name": members[0]["asset_name"],
                "alarm_name": alarm_name,
                "occurrences": occurrences,
                "avg_ack_delay_minutes": round(avg_ack, 2),
                "reasons": reasons,
            }
        )

    candidates.sort(key=lambda c: c["occurrences"], reverse=True)
    return {
        "recurrence_threshold": req.recurrence_threshold,
        "stale_minutes_threshold": req.stale_minutes_threshold,
        "candidates": candidates,
    }


# --------------------------------------------------------------------------- #
# Priority scoring
# --------------------------------------------------------------------------- #
def priority_score(req: PriorityScoreRequest) -> dict[str, Any]:
    alarm = DB.alarms.get(req.alarm_id)
    if alarm is None:
        raise NotFoundError(f"Alarm '{req.alarm_id}' not found")

    asset = DB.assets.get(alarm["asset_id"], {})
    severity_component = SEVERITY_RANK.get(alarm["severity"], 1) * 20
    criticality_component = {"low": 5, "medium": 10, "high": 20}.get(asset.get("criticality", "low"), 5)
    active_bonus = 15 if alarm["status"] == "active" else 0
    ack_penalty = min(alarm["ack_delay_minutes"] / 2, 15)

    score = round(min(severity_component + criticality_component + active_bonus + ack_penalty, 100), 1)
    if score >= 80:
        band = "critical"
    elif score >= 60:
        band = "high"
    elif score >= 35:
        band = "medium"
    else:
        band = "low"

    return {
        "alarm_id": alarm["alarm_id"],
        "asset_id": alarm["asset_id"],
        "priority_score": score,
        "priority_band": band,
        "components": {
            "severity_component": severity_component,
            "asset_criticality_component": criticality_component,
            "active_bonus": active_bonus,
            "ack_delay_penalty": round(ack_penalty, 2),
        },
    }


# --------------------------------------------------------------------------- #
# Operator recommendations
# --------------------------------------------------------------------------- #
_RECOMMENDATION_LIBRARY: dict[str, list[str]] = {
    "High Vibration": [
        "Inspect pump bearings and coupling alignment.",
        "Check for cavitation caused by low suction pressure.",
        "Review recent maintenance history for this asset.",
    ],
    "Bearing Temperature High": [
        "Verify lubrication levels and grease schedule.",
        "Inspect bearing for wear or contamination.",
    ],
    "Discharge Pressure High": [
        "Check downstream valve positions for blockage.",
        "Verify discharge pressure transmitter calibration.",
    ],
    "Motor Trip": [
        "Confirm motor protection relay trip cause before reset.",
        "Inspect for overcurrent or ground fault conditions.",
    ],
    "Surge Detected": [
        "Reduce compressor load and verify anti-surge valve operation.",
        "Inspect suction/discharge piping for restrictions.",
    ],
}
_DEFAULT_RECOMMENDATIONS = [
    "Acknowledge the alarm and verify current process values.",
    "Cross-check the asset's maintenance history for recurring issues.",
    "Escalate to the shift supervisor if the condition persists.",
]


def operator_recommendations(req: OperatorRecommendationsRequest) -> dict[str, Any]:
    alarm = DB.alarms.get(req.alarm_id)
    if alarm is None:
        raise NotFoundError(f"Alarm '{req.alarm_id}' not found")

    actions = list(_RECOMMENDATION_LIBRARY.get(alarm["alarm_name"], _DEFAULT_RECOMMENDATIONS))

    response: dict[str, Any] = {
        "alarm_id": alarm["alarm_id"],
        "alarm_name": alarm["alarm_name"],
        "asset_id": alarm["asset_id"],
        "recommended_actions": actions,
    }

    if req.include_related:
        asset = DB.assets.get(alarm["asset_id"], {})
        response["related_assets"] = asset.get("related_assets", [])

    if req.include_asset_context:
        response["asset_context"] = DB.assets.get(alarm["asset_id"])

    if req.include_historical_pattern:
        same = [a for a in DB.alarms.values() if a["asset_id"] == alarm["asset_id"] and a["alarm_name"] == alarm["alarm_name"]]
        response["historical_pattern"] = {
            "occurrences": len(same),
            "avg_ack_delay_minutes": round(sum(a["ack_delay_minutes"] for a in same) / len(same), 2) if same else 0.0,
        }

    return response


# --------------------------------------------------------------------------- #
# Calculation code generate/execute (two-step KPI flow)
# --------------------------------------------------------------------------- #
_CALCULATIONS: dict[str, dict[str, Any]] = {}


def generate_calculation(req: CalculationGenerateRequest) -> dict[str, Any]:
    calculation_id = f"CALC-{uuid.uuid4().hex[:10]}"
    _CALCULATIONS[calculation_id] = {"calculation_type": req.calculation_type, "filters": req.filters}
    return {"calculation_id": calculation_id, "calculation_type": req.calculation_type, "status": "generated"}


def execute_calculation(req: CalculationExecuteRequest) -> dict[str, Any]:
    calc = _CALCULATIONS.get(req.calculation_id)
    if calc is None:
        raise NotFoundError(f"Calculation '{req.calculation_id}' not found. Call /calculation-code/generate first.")

    filters = {**calc["filters"], **req.filters}
    unit = filters.get("unit")
    site = filters.get("site")
    start = _parse(filters["start_time"]) if "start_time" in filters else datetime.min
    end = _parse(filters["end_time"]) if "end_time" in filters else datetime.max
    rows = _filtered_alarms(None, site, unit, start, end)

    calc_type = calc["calculation_type"]
    if calc_type == "alarm_flood_index":
        result = {"alarm_flood_index": round(len(rows) / max((end - start).days, 1), 2)}
    elif calc_type == "critical_alarm_density":
        critical = sum(1 for a in rows if a["severity"] == "critical")
        result = {"critical_alarm_density": round(critical / len(rows), 3) if rows else 0.0, "critical_count": critical}
    elif calc_type == "operator_response_efficiency":
        acked = [a["ack_delay_minutes"] for a in rows]
        result = {"avg_ack_delay_minutes": round(sum(acked) / len(acked), 2) if acked else 0.0}
    elif calc_type == "nuisance_alarm_score":
        names = Counter(a["alarm_name"] for a in rows)
        nuisance = sum(1 for c in names.values() if c >= 8)
        result = {"nuisance_alarm_score": nuisance, "distinct_alarm_types": len(names)}
    else:
        result = {}

    return {
        "calculation_id": req.calculation_id,
        "calculation_type": calc_type,
        "filters": filters,
        "alarms_considered": len(rows),
        "result": result,
    }


# --------------------------------------------------------------------------- #
# KPI definitions (static reference/catalog data)
# --------------------------------------------------------------------------- #
KPI_DEFINITIONS: list[dict[str, str]] = [
    {"kpi": "alarm_count", "description": "Total number of alarm events in the selected window."},
    {"kpi": "recurring_rate", "description": "Fraction of alarms belonging to a name that occurred more than once."},
    {"kpi": "avg_ack_delay", "description": "Average minutes between alarm activation and operator acknowledgement."},
    {"kpi": "critical_count", "description": "Number of alarms at critical severity."},
    {"kpi": "suppression_candidate_rate", "description": "Fraction of alarms still active/unresolved, a rationalization signal."},
    {"kpi": "alarm_flood_index", "description": "Average alarms per day within the filtered window."},
    {"kpi": "critical_alarm_density", "description": "Share of alarms in the window that are critical severity."},
    {"kpi": "operator_response_efficiency", "description": "Average acknowledgement delay, lower is better."},
    {"kpi": "nuisance_alarm_score", "description": "Count of alarm types recurring 8+ times in the window (candidate nuisance alarms)."},
]
