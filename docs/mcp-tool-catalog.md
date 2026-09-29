# MCP Tool Catalog — `alarm-management` server

Server location: `mcp-servers/alarm-management/`. Start it independently with:

```bash
cd mcp-servers/alarm-management
export ALARM_API_BASE_URL=http://localhost:8000
export ALARM_API_TOKEN=demo-token
PYTHONPATH=../.. python -m server.app
```

This starts a streamable-HTTP MCP server on `0.0.0.0:9000` (configurable via
`MCP_SERVER_HOST` / `MCP_SERVER_PORT`). Any MCP client (this project's copilot
backend, Claude Desktop, `mcp inspector`, etc.) can connect to
`http://localhost:9000/mcp`.

**Authentication behavior (applies to every tool):** the server holds a single
Alarm Management API bearer token from `ALARM_API_TOKEN` (never exposed to the
MCP client or logged). Every underlying HTTP call carries `Authorization: Bearer
<token>` plus `trace_id`, `x-client-id`, and `x-metadata-tag` headers.

**Timeout & retry behavior (applies to every tool):** requests to the Alarm
Management API time out after `ALARM_API_TIMEOUT_SECONDS` (default 10s) and are
retried up to `ALARM_API_MAX_RETRIES` times (default 3) with linear backoff, on
connection failures, timeouts, and 502/503/504 responses.

**Error behavior (applies to every tool):** connector failures are mapped to a
typed `McpError` with a stable code — see `server/errors.py`:

| Condition | MCP error code |
|---|---|
| Alarm API auth failure (401/403) | -32001 |
| Resource not found (404) | -32002 |
| Invalid request payload (400/422) | -32003 |
| Timeout after retries | -32004 |
| Unreachable / 5xx after retries | -32005 |
| Unexpected connector error | -32000 |

**How to think about this catalog for the demo/interview:** every tool here
answers one narrow question about the plant. The LLM's job in the orchestrator
is to pick the right sequence of these narrow questions to answer a broad,
vague operator question ("why does this alarm keep going off?"). None of these
tools does "investigation" by itself — investigation is the *orchestrator*
chaining several of them together, informed by what each one returns.

---

## 1. `search_assets`

**Purpose:** Resolve a free-text asset name/keyword to one or more asset IDs.
Always called first when the user names an asset.

**When it's used / why it exists:** Every other tool in this catalog needs a
real `asset_id` (like `AST-bdd640fb06`), but a human never talks that way —
they say "the boiler feed pump" or "BFP-101". This tool is the translation
step between human language and the system's internal identifiers. Without
it, every other tool would require the user to already know the asset ID,
which defeats the point of a natural-language copilot.

**Example use case:** User asks *"Show active critical alarms for Boiler Feed
Pump 102 and recommend immediate actions."* The orchestrator cannot call
`get_alarms` yet — it doesn't have an `asset_id`. So the very first tool call
it makes is `search_assets({"query": "Boiler Feed Pump 102"})`, which returns
`asset_id: "AST-xxxxx"`. Only then can it call `get_alarms(asset_id=...)`.

**Input schema:**
```json
{"query": "string (required)", "unit": "string?", "site": "string?", "limit": "int 1-100, default 10"}
```

**Output schema:** `{query, count, results: [{asset_id, asset_name, asset_type, site, unit, criticality}], trace_id}`

**Underlying operation:** `GET /assets/search`

**Example invocation:**
```json
{"query": "Boiler Feed Pump 101"}
```

**Example response:**
```json
{"query": "Boiler Feed Pump 101", "count": 1, "results": [{"asset_id": "AST-bdd640fb06", "asset_name": "Boiler Feed Pump 101", "asset_type": "pump", "site": "NorthPlant", "unit": "Unit 1", "criticality": "medium"}]}
```

---

## 2. `get_asset_metadata`

**Purpose:** Fetch full metadata for a resolved `asset_id`.

**When it's used / why it exists:** `search_assets` only returns enough to
identify the asset (name, type, site). This tool returns the *context* about
that asset needed for deeper reasoning — manufacturer, install date, and
crucially `related_assets` (e.g. an upstream valve or a downstream reactor
feed line). The LLM needs this to answer "what else should I inspect?"
questions, and it needs `criticality`/`manufacturer` to judge how urgent a
recommendation should be.

**Example use case:** User asks *"What related assets should be inspected for
this motor trip alarm?"* After resolving the asset and pulling the alarm, the
orchestrator calls `get_asset_metadata(asset_id=...)` specifically to read
`related_assets`, which it then feeds into the answer as "also check X and Y."
Without this call, the copilot would have no way to know that Boiler Feed
Pump 101 is mechanically linked to Boiler Feed Pump 102 and Reactor Feed Valve
V-701 — that relationship lives only in this endpoint, not in the alarm data.

**Input schema:** `{"asset_id": "string (required)"}`

**Output schema:** `{asset_id, asset_name, asset_type, site, unit, criticality, manufacturer, installed_on, related_assets: [string], tags: [string]}`

**Underlying operation:** `GET /assets/{asset_id}/metadata`

**Error behavior:** raises `not_found` (-32002) for an unknown asset_id.

**Example invocation / response:** see `search_assets` output's `asset_id`, then:
```json
{"asset_id": "AST-bdd640fb06", "asset_name": "Boiler Feed Pump 101", "related_assets": ["Boiler Feed Pump 102", "Reactor Feed Valve V-701"], ...}
```

---

## 3. `get_alarms`

**Purpose:** Retrieve active or historical alarms with filtering and pagination.

**When it's used / why it exists:** This is the core "what's actually
happening / what happened" tool — the raw alarm log for an asset, a time
window, a severity, or a status (active vs. cleared). Almost every
investigation touches this tool at least once, because it's the only place
that returns individual alarm records (timestamps, severities, ack status)
rather than an aggregate.

**Example use case:** User asks *"Show active critical alarms for Boiler Feed
Pump 102."* Once the asset is resolved, the orchestrator calls
`get_alarms({"asset_id": "AST-...", "status": "active"})` and filters/reads
the severities from the returned `data` array to build the "active critical
alarms" list. For a recurrence question ("why do these keep happening?"), it
instead calls this with a wide `start_time`/`end_time` window to pull the
*history*, which it can then hand to `get_alarm_summary` or reason over
directly to spot a pattern (e.g. "6 occurrences in the last 30 days").

**Input schema:**
```json
{"asset_id": "string?", "site": "string?", "unit": "string?", "status": "active|cleared?",
 "start_time": "ISO-8601?", "end_time": "ISO-8601?", "page": "int>=1, default 1",
 "page_size": "int 1-500, default 50", "sort_by": "string, default start_time", "sort_order": "asc|desc, default desc"}
```

**Output schema:** `{data: [AlarmRecord], pagination: {page, page_size, total_items, total_pages}}`

**Underlying operation:** `GET /alarms`

**Example invocation:** `{"asset_id": "AST-bdd640fb06", "page": 1, "page_size": 5}`

---

## 4. `get_alarm_by_id`

**Purpose:** Fetch full detail for one alarm.

**When it's used / why it exists:** `get_alarms` returns a list, sometimes
with fields trimmed to keep the payload small. Once the LLM has picked out
*which specific alarm* it's investigating (from a list, or because the user
gave an `alarm_id` directly), this tool gets the complete record for that one
alarm — every field, not a summary row. It's also the required input to
`score_alarm_priority` and `get_operator_recommendations`, both of which key
off a single `alarm_id`.

**Example use case:** User asks *"What operating procedure applies to this
alarm?"* and pastes a specific `alarm_id` from an earlier answer. The
orchestrator calls `get_alarm_by_id(alarm_id=...)` to get the full record
(alarm name, asset, severity, description) before it can construct a good
`search_documents` query — it needs the exact alarm name/asset from this call
to search the RAG corpus for the matching procedure, rather than guessing.

**Input schema:** `{"alarm_id": "string (required)"}`

**Output schema:** `AlarmRecord`

**Underlying operation:** `GET /alarms/{alarm_id}`

---

## 5. `get_alarm_summary`

**Purpose:** Summarize alarms grouped by a field (alarm_name, asset_id, severity, ...)
with KPIs (alarm_count, recurring_rate, avg_ack_delay, critical_count,
suppression_candidate_rate).

**When it's used / why it exists:** `get_alarms` gives you raw rows; a human
asking "which alarm has the highest priority in EastRefinery, and why?" or
"is this alarm noisy?" doesn't want 200 individual rows — they want it
grouped and counted. This tool pushes the aggregation down to the Alarm API
itself instead of making the LLM count rows out of a giant JSON blob (which
is slow, token-expensive, and error-prone for an LLM to do correctly).

**Example use case:** User asks *"Which alarm has the highest priority in
EastRefinery, and why?"* The orchestrator calls `get_alarm_summary` grouped
by `alarm_name` with `kpis: ["alarm_count", "critical_count", "avg_ack_delay"]`
over a recent time range, scoped to `site: "EastRefinery"`. It reads the
returned `groups` array to find the alarm_name with the worst combination of
count + severity + slow acknowledgment, rather than trying to manually derive
that ranking from a raw alarm list.

**Input schema:**
```json
{"time_range": {"start_time": "ISO-8601", "end_time": "ISO-8601"}, "asset_ids": "string[]?",
 "site": "string?", "unit": "string?", "severity": "string[]?", "alarm_types": "string[]?",
 "group_by": "string[], default [alarm_name]", "kpis": "string[], default [alarm_count, recurring_rate, avg_ack_delay]"}
```

**Output schema:** `{time_range, group_by, kpis, total_alarms, groups: [object]}`

**Underlying operation:** `POST /alarms/summary` (with `trace_id`/`x-client-id`/`x-metadata-tag` headers)

**Example invocation:**
```json
{"time_range": {"start_time": "2026-05-01T00:00:00Z", "end_time": "2026-07-01T00:00:00Z"}, "asset_ids": ["AST-bdd640fb06"], "severity": ["high", "critical"]}
```

---

## 6. `get_alarm_trends`

**Purpose:** Time-bucketed (hourly/daily/weekly) series of alarm metrics.

**When it's used / why it exists:** Summaries answer "how much/how bad
overall"; trends answer "is it getting worse, and when does it spike."
This is the tool for questions with a time dimension — "has this alarm been
increasing," "does it cluster around shift changes," "did it start after a
specific date." It's the one tool that returns a series rather than a single
aggregate, so the LLM (or the GUI) can describe or plot a trajectory.

**Example use case:** For *"Why are compressor discharge pressure alarms
repeatedly occurring?"*, after confirming there IS a recurring pattern via
`get_alarm_summary`, the orchestrator can call `get_alarm_trends` with
`bucket: "daily"` to see whether the alarm count is flat, rising, or spiking
on specific days — which materially changes the answer ("steady low-level
noise" vs. "an escalating trend that needs urgent attention now").

**Input schema:** `{"time_range": {...}, "asset_ids": "string[]?", "site": "string?", "unit": "string?", "bucket": "hourly|daily|weekly, default daily", "metrics": "string[], default [alarm_count, avg_ack_delay]"}`

**Output schema:** `{bucket, metrics, series: [{bucket_start, ...metric values}], trace_id}`

**Underlying operation:** `POST /alarms/trends`

---

## 7. `correlate_alarms` (advanced operation)

**Purpose:** Find alarms across multiple assets that co-occur within a lag
window — the primary tool for root-cause / related-asset investigation.

**When it's used / why it exists:** A single asset's alarm history often
doesn't explain *why* something is happening — the real cause may be a
neighboring asset (e.g. a discharge-pressure alarm on a compressor that
always follows a valve alarm two minutes earlier on an upstream vessel). This
tool looks for that kind of co-occurrence pattern across a set of asset IDs
(typically the target asset plus its `related_assets` from
`get_asset_metadata`), which a human would otherwise have to eyeball across
several separate alarm logs.

**Example use case:** For *"What related assets should be inspected for this
motor trip alarm?"*, the orchestrator: (1) resolves the asset, (2) calls
`get_asset_metadata` to get `related_assets`, (3) calls
`correlate_alarms({"asset_ids": [motor_id, ...related_ids], "lag_window_minutes": 15})`.
If the result shows the motor's trip alarms consistently co-occur with a
bearing-temperature alarm on a related asset within the lag window, that's
the evidence for "inspect the bearing on X — its alarms fire right before
this trip."

**Input schema:**
```json
{"asset_ids": "string[] (required, min 1)", "time_range": {...},
 "correlation_method": "cooccurrence", "lag_window_minutes": "int 1-1440, default 15",
 "severity_threshold": "string, default medium", "min_support": "int>=1, default 1"}
```

**Output schema:** `{correlation_method, severity_threshold, asset_ids, correlations: [{pair, co_occurrences, lag_window_minutes}], total_alarms_considered, trace_id}`

**Underlying operation:** `POST /alarms/correlation`

---

## 8. `analyze_alarm_flood`

**Purpose:** Detect alarm-flood windows (bursts exceeding a threshold within a
rolling window) for a unit/site.

**When it's used / why it exists:** In alarm-management practice, a "flood" —
many alarms firing in a short window, often from one upset condition
cascading — is a distinct, well-known operational problem (it's how
operators get overwhelmed during a real incident and miss the alarm that
actually matters). This tool exists to detect *that specific pattern*
(bursts, not just "a lot of alarms generally"), which `get_alarm_summary`
cannot do because it aggregates over the whole time range, not rolling
windows.

**Example use case:** An operator asks *"Was there an alarm flood on Unit 1
last night?"* The orchestrator calls
`analyze_alarm_flood({"unit": "Unit 1", "time_range": {...}, "threshold_count": 10, "rolling_window_minutes": 10})`.
If `flood_windows` comes back non-empty (e.g. 23 alarms between 02:14 and
02:19), that's direct evidence of a flood event the operator can be pointed
to, with exact start/end times.

**Input schema:** `{"time_range": {...}, "unit": "string?", "site": "string?", "threshold_count": "int, default 10", "rolling_window_minutes": "int, default 10"}`

**Output schema:** `{unit, site, threshold_count, rolling_window_minutes, flood_windows: [{start, end, alarm_count}], total_alarms_considered, trace_id}`

**Underlying operation:** `POST /alarms/flood-analysis`

---

## 9. `get_rationalization_candidates`

**Purpose:** Identify alarms that are candidates for rationalization
(high-recurrence or slow-to-acknowledge).

**When it's used / why it exists:** "Alarm rationalization" is the industry
term for reviewing a plant's alarm configuration to remove noisy, low-value
alarms (ones that fire constantly but operators mostly ignore or take a long
time to acknowledge because they're not actually urgent). This tool
implements that specific analysis — it's a different lens than "what's
currently critical" (that's `get_alarm_summary`/priority); this is "what's
probably misconfigured and should be re-tuned or removed."

**Example use case:** A reliability engineer asks *"Which alarms on this unit
should we review for rationalization?"* The orchestrator calls
`get_rationalization_candidates({"unit": ..., "recurrence_threshold": 5, "stale_minutes_threshold": 180})`
and returns the `candidates` list — e.g. an alarm that fired 40 times in a
month with an average 3-hour acknowledgment delay, which is a strong signal
it's being tuned out by operators rather than acted on.

**Input schema:** `{"time_range": {...}, "asset_ids": "string[]?", "site": "string?", "unit": "string?", "recurrence_threshold": "int, default 5", "stale_minutes_threshold": "int, default 180"}`

**Output schema:** `{recurrence_threshold, stale_minutes_threshold, candidates: [{asset_id, asset_name, alarm_name, occurrences, avg_ack_delay_minutes, reasons}], trace_id}`

**Underlying operation:** `POST /alarms/rationalization-candidates`

---

## 10. `score_alarm_priority` (advanced operation)

**Purpose:** Compute a 0-100 priority score and band for a single alarm.

**When it's used / why it exists:** Severity alone (e.g. "high"/"critical")
doesn't capture true urgency — a "high" severity alarm on a low-criticality
spare pump is less urgent than a "medium" alarm on a critical reactor that's
already active and has been sitting unacknowledged. This tool turns those
several factors (severity, asset criticality, whether it's still active, how
long it's gone unacknowledged) into one comparable 0-100 number, which is
what "highest priority" questions actually need to compare across different
alarms/assets on equal footing.

**Example use case:** For *"Which alarm has the highest priority in
EastRefinery, and why?"*, after narrowing to a shortlist of candidate alarms
via `get_alarms`/`get_alarm_summary`, the orchestrator calls
`score_alarm_priority(alarm_id=...)` for each candidate and compares the
`priority_score`/`priority_band`, then explains the answer using the
`components` breakdown (e.g. "scored highest mainly because of a 45-minute
ack delay on a high-criticality asset").

**Input schema:** `{"alarm_id": "string (required)"}`

**Output schema:** `{alarm_id, asset_id, priority_score, priority_band, components: {severity_component, asset_criticality_component, active_bonus, ack_delay_penalty}}`

**Underlying operation:** `POST /alarms/priority-score`

---

## 11. `get_operator_recommendations` (advanced operation)

**Purpose:** Get recommended operator actions for an alarm, optionally
including related assets, asset context, and historical recurrence pattern.

**When it's used / why it exists:** This is the Alarm API's own "what should
I do about it" answer — its built-in, structured recommendation, independent
of the document corpus. It exists so the copilot can *compare* the system's
recommendation against the written maintenance manual/procedure (retrieved
via RAG) and flag agreement or contradiction, which is explicitly one of the
assignment's example questions ("Are the API recommendations consistent with
the maintenance manual?").

**Example use case:** For *"Show active critical alarms for Boiler Feed Pump
102 and recommend immediate actions,"* the orchestrator calls
`get_operator_recommendations(alarm_id=..., include_related=true)` to get the
system's own `recommended_actions` list, and *separately* calls
`search_documents` against the maintenance manual. The final answer then
merges both — presenting the API's recommendation and either confirming it
matches the manual's guidance or noting a discrepancy, with citations for
each source.

**Input schema:** `{"alarm_id": "string (required)", "include_related": "bool, default true", "include_asset_context": "bool, default false", "include_historical_pattern": "bool, default false"}`

**Output schema:** `{alarm_id, alarm_name, asset_id, recommended_actions: [string], related_assets?, asset_context?, historical_pattern?, trace_id}`

**Underlying operation:** `POST /recommendations/operator-actions`

---

## 12. `generate_calculation`

**Purpose:** Step 1 of a two-step KPI calculation flow — register a
calculation type + filters, returns a `calculation_id`.

**When it's used / why it exists:** This tool (together with
`execute_calculation`) deliberately demonstrates **multi-step tool chaining
where one tool's output becomes another tool's input** — a specific
requirement the assignment calls out ("passing outputs from one MCP tool
into another"). It's modeled the way a real batch/reporting API often works:
you first *register* what you want computed (so the server can validate the
request and allocate a job/calculation id), then separately *trigger*
execution. It also lets the same registered calculation be re-executed later
with different filters without re-registering it.

**Example use case:** User asks *"What's our nuisance alarm score for Unit
1 this month?"* The orchestrator first calls
`generate_calculation({"calculation_type": "nuisance_alarm_score", "filters": {"unit": "Unit 1"}})`,
gets back a `calculation_id`, and only then calls `execute_calculation` (see
below) with that ID to actually get the number. Neither call alone answers
the question — it's the chain that matters, and it's a clean, concrete
example to point to when asked "show me tool chaining" in an interview.

**Input schema:** `{"calculation_type": "alarm_flood_index|critical_alarm_density|operator_response_efficiency|nuisance_alarm_score", "filters": "object"}`

**Output schema:** `{calculation_id, calculation_type, status, trace_id}`

**Underlying operation:** `POST /calculation-code/generate`

---

## 13. `execute_calculation`

**Purpose:** Step 2 — execute a previously generated `calculation_id`.

**When it's used / why it exists:** The counterpart to `generate_calculation`
above — this is where the `calculation_id` produced by step 1 is *consumed*
as the input to step 2. It's the concrete proof point for "MCP output passed
into a subsequent tool," and it's also where you'd demonstrate the
partial-failure/error-mapping story: calling this with a `calculation_id`
that was never generated (or has expired) deliberately raises a `not_found`
error, which the orchestrator has to handle gracefully rather than crash on.

**Example use case:** Continuing the nuisance-alarm-score example: the
orchestrator calls
`execute_calculation({"calculation_id": "<id from step 1>", "filters": {"unit": "Unit 1"}})`
and gets back the actual `result` value plus `alarms_considered`, which it
then reports to the user with the number and how many alarms fed into it.

**Input schema:** `{"calculation_id": "string (required)", "filters": "object"}`

**Output schema:** `{calculation_id, calculation_type, filters, alarms_considered, result, trace_id}`

**Underlying operation:** `POST /calculation-code/execute`

**Error behavior:** raises `not_found` if `calculation_id` was never generated.

---

## 14. `get_kpi_definitions`

**Purpose:** List the KPI definitions the Alarm Management API supports.

**When it's used / why it exists:** This is a self-describing/discovery tool
rather than a data tool — it exists so the LLM (or a human exploring the
system) can find out *what KPIs are even available* before trying to compute
one, instead of guessing a `calculation_type` string and having it rejected.
It's the "menu" that makes `generate_calculation`/`execute_calculation`
discoverable rather than requiring hard-coded knowledge of the four
calculation types.

**Example use case:** User asks *"What KPIs can you calculate for me?"* or
the LLM is about to call `generate_calculation` but the user's request is
phrased vaguely ("give me some alarm health metrics"). The orchestrator calls
`get_kpi_definitions()` first, reads the returned `kpis` list with their
descriptions, and either presents the options to the user or picks the best
match itself before generating the calculation.

**Input schema:** `{}`

**Output schema:** `{kpis: [{kpi, description}], trace_id}`

**Underlying operation:** `GET /analytics/kpi-definitions`
