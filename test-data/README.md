# Test Data

The three Postman collections that were provided as the specification for
this assignment, kept here verbatim for traceability between the reference
contract and the implementation:

- `Alarm-API-Simulator.postman_collection.json` — the core Alarm Management
  API endpoint contract (search, alarms, summary/trends/correlation/flood/
  rationalization/priority/recommendations, KPI calculation).
- `Alarm-API-Chaining.postman_collection.json` — multi-step request chains
  (asset → summary → rationalization, flood → alarms → summary, KPI
  generate → execute → summary, etc.) that the MCP tool sequences in
  `docs/api-integration.md` are designed to satisfy.
- `Alarm-API-Scenarios.postman_collection.json` — example investigation
  scenarios.

These were **not executed directly** against anything in this repository —
they were used as the human-readable specification for
`apps/alarm-api/app/main.py` (the simulator that implements this contract)
and `mcp-servers/alarm-management/server/app.py` (the MCP tools that wrap
it). The copilot itself never calls this API directly; see
`docs/api-integration.md`.

> Note: as provided, `Alarm-API-Simulator.postman_collection.json` and
> `Alarm-API-Scenarios.postman_collection.json` are byte-identical. They are
> kept as two separate files here only to preserve the original naming/
> structure exactly as supplied for the assignment.

No credentials are embedded in these files — the simulator's bearer token
(`ALARM_API_TOKEN`) is supplied via environment variable, not via the
collection's saved variables.
