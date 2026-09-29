"""Alarm Management API simulator.

A realistic-but-synthetic REST backend implementing the endpoint surface
documented in the reference Postman collections (search, metadata, alarms,
summary, trends, correlation, flood analysis, rationalization, priority
scoring, operator recommendations, two-step calculation codes, and KPI
definitions), plus bearer auth, trace-header propagation, and pagination.

Run standalone:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from app import store
from app.middleware import TraceMiddleware
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
from app.security import require_bearer_token

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Alarm Management API Simulator",
    description="Synthetic Alarm Management source system used as the reference backend for the alarm-management MCP server.",
    version="1.0.0",
)
app.add_middleware(TraceMiddleware)

AUTH = Depends(require_bearer_token)


@app.exception_handler(store.NotFoundError)
async def not_found_handler(request: Request, exc: store.NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "not_found", "message": str(exc)})


@app.exception_handler(store.ValidationError)
async def validation_handler(request: Request, exc: store.ValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "validation_error", "message": str(exc)})


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "alarm-api-simulator"}


@app.get("/assets/search", dependencies=[AUTH])
async def assets_search(
    query: str = Query(default=""),
    unit: str | None = None,
    site: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
) -> dict:
    results = store.search_assets(query=query, unit=unit, site=site, limit=limit)
    return {"query": query, "count": len(results), "results": results}


@app.get("/assets/{asset_id}/metadata", dependencies=[AUTH])
async def asset_metadata(asset_id: str) -> dict:
    return store.get_asset_metadata(asset_id)


@app.get("/alarms", dependencies=[AUTH])
async def alarms_list(
    asset_id: str | None = None,
    site: str | None = None,
    unit: str | None = None,
    status: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    sort_by: str = "start_time",
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> dict:
    rows, total = store.list_alarms(asset_id, site, unit, status, start_time, end_time, page, page_size, sort_by, sort_order)
    return {
        "data": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        },
    }


@app.get("/alarms/{alarm_id}", dependencies=[AUTH])
async def alarm_detail(alarm_id: str) -> dict:
    return store.get_alarm(alarm_id)


@app.post("/alarms/summary", dependencies=[AUTH])
async def alarms_summary(payload: AlarmSummaryRequest) -> dict:
    return store.alarm_summary(payload)


@app.post("/alarms/trends", dependencies=[AUTH])
async def alarms_trends(payload: AlarmTrendsRequest) -> dict:
    return store.alarm_trends(payload)


@app.post("/alarms/correlation", dependencies=[AUTH])
async def alarms_correlation(payload: AlarmCorrelationRequest) -> dict:
    return store.alarm_correlation(payload)


@app.post("/alarms/flood-analysis", dependencies=[AUTH])
async def alarms_flood_analysis(payload: FloodAnalysisRequest) -> dict:
    return store.flood_analysis(payload)


@app.post("/alarms/rationalization-candidates", dependencies=[AUTH])
async def alarms_rationalization_candidates(payload: RationalizationRequest) -> dict:
    return store.rationalization_candidates(payload)


@app.post("/alarms/priority-score", dependencies=[AUTH])
async def alarms_priority_score(payload: PriorityScoreRequest) -> dict:
    return store.priority_score(payload)


@app.post("/recommendations/operator-actions", dependencies=[AUTH])
async def operator_recommendations(payload: OperatorRecommendationsRequest) -> dict:
    return store.operator_recommendations(payload)


@app.post("/calculation-code/generate", dependencies=[AUTH])
async def calculation_generate(payload: CalculationGenerateRequest) -> dict:
    return store.generate_calculation(payload)


@app.post("/calculation-code/execute", dependencies=[AUTH])
async def calculation_execute(payload: CalculationExecuteRequest) -> dict:
    return store.execute_calculation(payload)


@app.get("/analytics/kpi-definitions", dependencies=[AUTH])
async def kpi_definitions() -> dict:
    return {"kpis": store.KPI_DEFINITIONS}
