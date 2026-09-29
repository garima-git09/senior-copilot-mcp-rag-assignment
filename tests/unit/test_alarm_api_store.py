"""Unit tests for the Alarm Management API simulator's query/analytics logic
(apps/alarm-api/app/store.py) -- pure functions, no HTTP involved.
"""

from __future__ import annotations

import pytest
from app import store
from app.schemas import PriorityScoreRequest, RationalizationRequest, TimeRange
from app.seed_data import DB


def test_search_assets_matches_by_name_case_insensitive():
    results = store.search_assets(query="boiler feed pump 101")
    assert any(a["asset_name"] == "Boiler Feed Pump 101" for a in results)


def test_search_assets_respects_limit():
    results = store.search_assets(query="", limit=3)
    assert len(results) == 3


def test_get_asset_metadata_raises_not_found_for_unknown_asset():
    with pytest.raises(store.NotFoundError):
        store.get_asset_metadata("AST-does-not-exist")


def test_list_alarms_pagination_is_consistent():
    any_asset_id = next(iter(DB.assets))
    page1, total = store.list_alarms(any_asset_id, None, None, None, None, None, page=1, page_size=2, sort_by="start_time", sort_order="asc")
    page2, total2 = store.list_alarms(any_asset_id, None, None, None, None, None, page=2, page_size=2, sort_by="start_time", sort_order="asc")
    assert total == total2
    ids_page1 = {a["alarm_id"] for a in page1}
    ids_page2 = {a["alarm_id"] for a in page2}
    assert ids_page1.isdisjoint(ids_page2)


def test_list_alarms_rejects_invalid_page():
    with pytest.raises(store.ValidationError):
        store.list_alarms(None, None, None, None, None, None, page=0, page_size=10, sort_by="start_time", sort_order="asc")


def test_list_alarms_rejects_page_size_out_of_bounds():
    with pytest.raises(store.ValidationError):
        store.list_alarms(None, None, None, None, None, None, page=1, page_size=5000, sort_by="start_time", sort_order="asc")


def test_priority_score_is_bounded_0_to_100():
    any_alarm_id = next(iter(DB.alarms))
    result = store.priority_score(PriorityScoreRequest(alarm_id=any_alarm_id))
    assert 0 <= result["priority_score"] <= 100
    assert result["priority_band"] in {"low", "medium", "high", "critical"}


def test_priority_score_raises_not_found():
    with pytest.raises(store.NotFoundError):
        store.priority_score(PriorityScoreRequest(alarm_id="ALM-does-not-exist"))


def test_rationalization_candidates_flags_high_recurrence():
    any_asset_id = next(iter(DB.assets))
    result = store.rationalization_candidates(
        RationalizationRequest(
            asset_ids=[any_asset_id],
            time_range=TimeRange(start_time="2026-05-01T00:00:00Z", end_time="2026-07-01T00:00:00Z"),
            recurrence_threshold=1,
            stale_minutes_threshold=1,
        )
    )
    assert isinstance(result["candidates"], list)
    for candidate in result["candidates"]:
        assert "high_recurrence" in candidate["reasons"] or "slow_acknowledgement" in candidate["reasons"]


def test_calculation_generate_then_execute_round_trip():
    from app.schemas import CalculationExecuteRequest, CalculationGenerateRequest

    gen = store.generate_calculation(CalculationGenerateRequest(calculation_type="critical_alarm_density", filters={"unit": "Unit 2"}))
    assert gen["calculation_id"].startswith("CALC-")

    result = store.execute_calculation(
        CalculationExecuteRequest(
            calculation_id=gen["calculation_id"],
            filters={"start_time": "2026-05-01T00:00:00Z", "end_time": "2026-07-01T00:00:00Z"},
        )
    )
    assert "critical_alarm_density" in result["result"]


def test_execute_calculation_unknown_id_raises_not_found():
    from app.schemas import CalculationExecuteRequest

    with pytest.raises(store.NotFoundError):
        store.execute_calculation(CalculationExecuteRequest(calculation_id="CALC-unknown", filters={}))
