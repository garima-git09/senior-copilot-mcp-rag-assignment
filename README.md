# Alarm Investigation and Procedure Guidance Copilot

An MCP + RAG copilot that investigates industrial plant alarms: it resolves an
asset name, pulls alarm history and analytics through a candidate-developed
MCP server, retrieves the relevant operating procedure or maintenance manual
through a document RAG pipeline, and produces one grounded, cited answer that
compares what the Alarm Management API recommends against what the
documentation says.

**Selected use case:** Alarm Investigation and Procedure Guidance Copilot (as assigned).

## Main capabilities

- Natural-language chat that plans its own investigation (no hard-coded question handling)
- 14 MCP tools covering asset search, alarm retrieval, summary/trend analytics, correlation, flood analysis, rationalization, priority scoring, operator recommendations, and KPI calculation
- Document RAG over operating procedures, maintenance manuals, troubleshooting guides, and safety instructions, with citations and low-confidence handling
- MCP and RAG combined in one agentic loop — every answer can cite both live alarm data and document guidance
- Full MCP execution trace + raw request/response inspection in the GUI
- Graceful degradation when a tool is unavailable, invalid, or returns low-confidence results (shown, not hidden)
- Pluggable LLM provider (Anthropic or OpenAI) via environment variables only

## Technology stack

| Layer | Technology |
|---|---|
| Alarm Management API simulator | Python, FastAPI, synthetic seeded data |
| MCP server | Python, official `mcp` SDK (FastMCP), streamable-HTTP transport |
| Copilot backend | Python, FastAPI, `httpx`, official `mcp` client SDK |
| RAG | `sentence-transformers` embeddings + ChromaDB (embedded) + `rank_bm25`, fused hybrid retrieval |
| LLM | Anthropic, OpenAI, or Groq (OpenAI-compatible), switchable by env var |
| GUI | Streamlit |
| Packaging | Docker, Docker Compose, GitHub Actions CI |

## MCP server

`mcp-servers/alarm-management/` — see **`docs/mcp-tool-catalog.md`** for full
per-tool documentation (input/output schema, auth, error, timeout behavior,
example invocation/response).

**Tool list:** `search_assets`, `get_asset_metadata`, `get_alarms`,
`get_alarm_by_id`, `get_alarm_summary`, `get_alarm_trends`,
`correlate_alarms`, `analyze_alarm_flood`, `get_rationalization_candidates`,
`score_alarm_priority`, `get_operator_recommendations`,
`generate_calculation`, `execute_calculation`, `get_kpi_definitions`.

**Start the MCP server independently:**
```bash
cd mcp-servers/alarm-management
export ALARM_API_BASE_URL=http://localhost:8000
export ALARM_API_TOKEN=demo-token
PYTHONPATH=../.. python -m server.app
# -> streamable-HTTP MCP server on http://localhost:9000/mcp
```

## RAG corpus and ingestion

10 synthetic Markdown documents under `rag/documents/` (operating procedures,
maintenance manuals, troubleshooting guides, safety instructions), chunked
heading-aware and indexed with a hybrid retriever — dense `sentence-transformers`
embeddings in ChromaDB, fused with BM25 keyword search (see
**`docs/rag-design.md`** for the full design and rationale).

**Build the index:**
```bash
python -m rag.ingestion.index_builder --documents ./rag/documents --index ./rag/index/local
# or: make ingest
```
The copilot backend also auto-builds the index on first startup if missing.

## Quick start

### Option A — Docker Compose (preferred)

```bash
cp .env.example .env      # then set LLM_API_KEY
docker compose up --build
```

This starts, in dependency order with health checks: `alarm-api` (:8000) →
`alarm-mcp` (:9000) → `copilot-backend` (:8080) → `frontend` (:8501). Open
http://localhost:8501.

> **Sandbox note:** the container images were validated with `docker compose
> config` (syntax + service graph) but an actual `docker compose build` could
> not be run inside the development sandbox used to build this submission,
> because its network policy blocks Docker Hub. Every service's application
> code was instead exhaustively tested directly (67 automated tests). See
> `docs/known-limitations.md`.

### Option B — run each service locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r apps/alarm-api/requirements.txt -r apps/backend/requirements.txt \
            -r apps/frontend/requirements.txt -r mcp-servers/alarm-management/requirements.txt \
            -r rag/requirements.txt

# terminal 1
cd apps/alarm-api && uvicorn app.main:app --port 8000

# terminal 2
cd mcp-servers/alarm-management && PYTHONPATH=../.. ALARM_API_BASE_URL=http://localhost:8000 python -m server.app

# terminal 3
export LLM_PROVIDER=anthropic LLM_API_KEY=sk-... MCP_SERVER_URL=http://localhost:9000/mcp
PYTHONPATH=. uvicorn apps.backend.main:app --port 8080

# terminal 4
cd apps/frontend && COPILOT_BACKEND_URL=http://localhost:8080 streamlit run app.py
```
(`make run-alarm-api`, `make run-mcp`, `make run-backend`, `make run-frontend` do the same.)

## Configuration

All configuration is environment-variable driven — see **`.env.example`** for
the complete list (Alarm API base URL/token, MCP server URL, LLM provider/key/
model, vector store path, document path, retrieval top-k/min-score, ticketing
placeholder). No secret has a real value committed anywhere in this repository.

**Switching the LLM provider:** set `LLM_PROVIDER=openai` (or `anthropic`),
`LLM_API_KEY`, and `LLM_MODEL` — no code change required
(`apps/backend/llm/factory.py`).

## Build and run commands

See the `Makefile`: `make up`, `make down`, `make build`, `make ingest`,
`make test`, `make test-coverage`, `make run-alarm-api`, `make run-mcp`,
`make run-backend`, `make run-frontend`.

## Test commands

```bash
make test              # full pytest suite (unit, integration, e2e, rag)
make test-coverage      # with coverage (terminal + docs/coverage_html)
pytest tests/unit -v
pytest tests/integration -v
pytest tests/e2e -v
pytest rag/tests -v
```

67 tests pass locally; see **`docs/coverage-report.md`** for the coverage
breakdown (82% across backend, connector, MCP server, alarm-api, and RAG code).

## Sample interactions

> **"Investigate recurring high-severity alarms for Boiler Feed Pump 101 over
> the last 90 days, identify likely contributing factors, retrieve the
> relevant operating procedure, and recommend actions with source evidence."**

The copilot: resolves the asset via `search_assets` → summarizes alarms via
`get_alarm_summary` (severity filter high/critical) → retrieves `OP-101` /
`MM-201` via `search_documents` → answers with alarm counts, the documented
vibration-troubleshooting guidance, and a Sources section citing both the MCP
tools called and the documents cited. This exact scenario is codified as the
automated end-to-end test in `tests/e2e/test_combined_workflow.py`.

Other supported questions (from the assignment brief, all handled by the same
general planner, not special-cased): *"Show active critical alarms for Boiler
Feed Pump 102 and recommend immediate actions"*, *"Why are compressor
discharge pressure alarms repeatedly occurring?"*, *"Which alarm has the
highest priority in EastRefinery, and why?"*, *"Are the API recommendations
consistent with the maintenance manual?"*.

## Architecture summary

See **`docs/architecture.md`** and **`docs/architecture-diagram.png`**. In
short: GUI → Copilot Backend (Orchestrator + LLM Provider + MCP Client + RAG
Tool) → [MCP Server → Connector → Alarm API Simulator] and [Retrieval Index →
Document Corpus], with the orchestrator as the only place MCP and RAG evidence
are combined.

## Assumptions

- No real Alarm Management API exists for this assignment; a synthetic
  simulator built from the reference Postman collections stands in for it,
  with a fixed historical data window so example queries are reproducible.
- The assigned use case is read-only investigation; no ticket/write-operation
  tool was required or implemented.
- A user-supplied LLM API key (Anthropic or OpenAI) is required to run the
  live chat; without one, `/chat` returns a clear 503 rather than falling back
  to a rule-based responder (the brief for this build asked for an LLM-driven
  planner, not a deterministic fallback).

## Known limitations

See **`docs/known-limitations.md`** for the full list (Docker build not
executable in the build sandbox, lexical-retrieval edge cases on a small
corpus, in-memory persistence, heuristic injection defense, no write
operations, no live-LLM test in this environment).

## Future improvements

- Already done: swapped the original TF-IDF dense signal for real
  `sentence-transformers` embeddings in ChromaDB (BM25 keyword matching is
  unchanged) — see `docs/design-decisions.md`. Next step once the corpus grows
  past a few dozen documents: evaluate a larger/domain-tuned embedding model
  and add re-ranking.
- Add a second MCP server (e.g. a maintenance-ticketing system) with
  confirm-gated write operations, per the assignment's optional-secondary-
  server allowance.
- Persist conversation history and alarm/asset state in a real database for
  multi-instance deployment.
- Add reranking on top of the current hybrid fusion for larger corpora.
- Add a live-LLM smoke test to CI once a project-owned API key with a spending
  cap is available.

## Repository structure

See `docs/architecture.md` for the full layer-by-file mapping. Top level:
`apps/` (alarm-api, backend, frontend), `mcp-servers/alarm-management/`,
`connectors/alarm_api/`, `rag/` (ingestion, retrieval, documents, tests),
`tests/` (unit, integration, e2e), `docs/`, `test-data/` (the original
reference Postman collections, kept for traceability — see
`test-data/README.md`), `scripts/` (`smoke_test.sh`, a post-startup health
check), `.github/workflows/ci.yml`, `docker-compose.yml`, `Dockerfile`,
`Makefile`, `.env.example`.
