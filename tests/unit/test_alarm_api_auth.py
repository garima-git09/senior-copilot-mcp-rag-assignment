"""Unit tests for the Alarm Management API simulator's bearer-auth dependency."""

from __future__ import annotations

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_does_not_require_auth():
    assert client.get("/health").status_code == 200


def test_missing_authorization_header_is_401():
    resp = client.get("/alarms")
    assert resp.status_code == 401


def test_wrong_token_is_403():
    resp = client.get("/alarms", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 403


def test_malformed_authorization_header_is_401():
    resp = client.get("/alarms", headers={"Authorization": "not-a-bearer-token"})
    assert resp.status_code == 401


def test_correct_token_is_accepted():
    resp = client.get("/alarms", headers={"Authorization": "Bearer demo-token"})
    assert resp.status_code == 200


def test_trace_headers_are_echoed_back():
    resp = client.get(
        "/alarms",
        headers={"Authorization": "Bearer demo-token", "trace_id": "trace-unit-test-1", "x-client-id": "pytest"},
    )
    assert resp.headers["trace_id"] == "trace-unit-test-1"
    assert resp.headers["x-client-id"] == "pytest"


def test_trace_id_is_generated_when_absent():
    resp = client.get("/alarms", headers={"Authorization": "Bearer demo-token"})
    assert resp.headers["trace_id"].startswith("trace-")
