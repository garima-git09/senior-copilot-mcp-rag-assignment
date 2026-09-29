# API Integration Documentation

## Alarm Management API Simulator

`apps/alarm-api/` implements the reference Postman contract
(`Alarm-API-Simulator.postman_collection.json`,
`Alarm-API-Chaining.postman_collection.json`,
`Alarm-API-Scenarios.postman_collection.json`) as a FastAPI service backed by
deterministic, seeded synthetic data (`apps/alarm-api/app/seed_data.py`):
15 assets (pumps, compressors, motors, heat exchangers, a fan, a valve, a
tank, a turbine) across 3 sites and 5 units, with alarm history generated over
a fixed window (`2026-05-01` .. `2026-07-01`, matching the reference
collections' `time_range` examples exactly) so results are reproducible and
match the documented example payloads.

### Endpoint surface

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness (no auth) |
| `/assets/search` | GET | Search assets by name/keyword |
| `/assets/{asset_id}/metadata` | GET | Asset metadata + related assets |
| `/alarms` | GET | List alarms, filtered + paginated |
| `/alarms/{alarm_id}` | GET | Alarm detail |
| `/alarms/summary` | POST | Grouped alarm KPIs |
| `/alarms/trends` | POST | Time-bucketed metric series |
| `/alarms/correlation` | POST | Co-occurrence correlation |
| `/alarms/flood-analysis` | POST | Alarm-flood window detection |
| `/alarms/rationalization-candidates` | POST | Recurring/nuisance alarm candidates |
| `/alarms/priority-score` | POST | 0-100 priority score |
| `/recommendations/operator-actions` | POST | Recommended actions |
| `/calculation-code/generate` | POST | Step 1 of KPI calculation |
| `/calculation-code/execute` | POST | Step 2 of KPI calculation |
| `/analytics/kpi-definitions` | GET | KPI catalog |

### Authentication

Bearer token (`Authorization: Bearer <ALARM_API_TOKEN>`), validated in
`apps/alarm-api/app/security.py`. Missing header → 401; wrong token → 403;
`/health` is intentionally unauthenticated (matches the reference collection).

### Trace / correlation metadata

`apps/alarm-api/app/middleware.py` reads `trace_id`, `x-client-id`,
`x-metadata-tag` request headers (generating a `trace_id` if absent), echoes
them back on the response, and logs every request as a structured line
(method, path, status, duration_ms, trace_id, client_id) — the Authorization
header is never logged.

### Pagination

`/alarms` supports `page` (>=1), `page_size` (1-500), `sort_by`, `sort_order`
(`asc`/`desc`), returning `{data, pagination: {page, page_size, total_items,
total_pages}}`.

### Multi-step chaining

The simulator supports every chaining flow in
`Alarm-API-Chaining.postman_collection.json` (asset → summary →
rationalization, flood → alarms → summary, root-cause + recommendations,
KPI generate → execute → summary, etc.) — these map directly onto MCP tool
sequences the copilot's orchestrator calls (see `docs/mcp-tool-catalog.md`
and the "multi-step chaining" tests in `tests/integration/`).

## How the copilot reaches this API

**The copilot never calls this API directly.** The only caller is
`connectors/alarm_api/client.py` (`AlarmApiClient`), and the only user of that
connector is the `alarm-management` MCP server
(`mcp-servers/alarm-management/server/app.py`). The copilot backend's
orchestrator calls MCP tools; the MCP server is what talks HTTP to this
simulator. This boundary is enforced by package structure, not just
convention: `apps/backend` has no import of `connectors.alarm_api`.

## Connector reliability behavior

`AlarmApiClient` (`connectors/alarm_api/client.py`):

- **Timeout:** `ALARM_API_TIMEOUT_SECONDS` (default 10s) per attempt.
- **Retry:** up to `ALARM_API_MAX_RETRIES` (default 3) attempts, linear
  backoff (`ALARM_API_RETRY_BACKOFF_SECONDS * attempt`), on connection
  failures, timeouts, and 502/503/504 responses.
- **Error mapping:** every failure becomes one of
  `AlarmApiAuthError` / `AlarmApiNotFoundError` / `AlarmApiValidationError` /
  `AlarmApiTimeoutError` / `AlarmApiUnavailableError` (see
  `connectors/alarm_api/exceptions.py`) — the MCP server then maps these to
  typed MCP errors (`docs/mcp-tool-catalog.md`).
- **Secrets:** the bearer token lives only in `AlarmApiConfig`; `redacted()`
  is used anywhere the config might be logged.
