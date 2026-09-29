# Architecture

## Request flow, end to end

1. **GUI (Streamlit, `apps/frontend`)** sends the user's natural-language message to
   **Copilot backend (`apps/backend`)** over HTTP (`POST /chat`).
2. The backend's **orchestrator** (`apps/backend/orchestrator/agent.py`) is the only
   component that talks to the **LLM provider** (`apps/backend/llm`, pluggable:
   Anthropic or OpenAI).
3. The orchestrator discovers tools from the **MCP client**
   (`apps/backend/mcp_client`), which connects over streamable-HTTP to the
   **alarm-management MCP server** (`mcp-servers/alarm-management`).
4. The MCP server's tools call the **Alarm Management API connector**
   (`connectors/alarm_api`), which talks to the **Alarm Management API simulator**
   (`apps/alarm-api`) — a synthetic but realistic REST backend built from the
   reference Postman collections.
5. In the same loop, the orchestrator also calls the **RAG tool**
   (`apps/backend/rag_client`), which queries the **retrieval index**
   (`rag/retrieval`) built by the **ingestion pipeline** (`rag/ingestion`) from the
   **document corpus** (`rag/documents`).
6. The LLM combines both kinds of evidence (structured alarm data via MCP,
   unstructured procedure text via RAG), compares them, and produces a grounded
   answer with citations and a full execution trace.
7. The backend returns `{answer, events, citations, degraded, degraded_reasons}` to
   the GUI, which renders the alarm summary, recommendations, citations, and MCP
   trace panels.

```
┌─────────────┐      HTTP       ┌───────────────────────────────────────────┐
│  Streamlit  │ ───────────────▶│              Copilot Backend               │
│    GUI      │◀─────────────── │  (FastAPI)                                 │
└─────────────┘   JSON answer   │                                             │
                                 │  ┌───────────────────────────────────┐    │
                                 │  │        Orchestrator (agent.py)     │    │
                                 │  │  - LLM tool-calling loop           │    │
                                 │  │  - combines MCP + RAG evidence     │    │
                                 │  └───────────┬───────────┬───────────┘    │
                                 │              │           │                │
                                 │   ┌──────────▼───┐   ┌───▼────────────┐  │
                                 │   │  LLM Provider │   │   MCP Client    │  │
                                 │   │ (Anthropic/   │   │ (discovery,     │  │
                                 │   │  OpenAI)      │   │  invocation)    │  │
                                 │   └───────────────┘   └───────┬────────┘  │
                                 │                                │           │
                                 │                        ┌───────▼────────┐  │
                                 │                        │    RAG Tool     │  │
                                 │                        └───────┬────────┘  │
                                 └────────────────────────────────┼───────────┘
                                       streamable-HTTP (MCP)       │
                                                │                  │
                                 ┌──────────────▼──────────┐       │
                                 │  Alarm-Management MCP    │      │
                                 │  Server (typed tools,    │      │
                                 │  auth, retry, trace)     │      │
                                 └──────────────┬───────────┘       │
                                                 │ HTTP (bearer)     │
                                 ┌───────────────▼──────────┐       │
                                 │  Alarm Management API     │      │
                                 │  Simulator (FastAPI)      │      │
                                 │  in-memory synthetic data │      │
                                 └────────────────────────────┘     │
                                                                     │
                                                        ┌────────────▼────────────┐
                                                        │   RAG Retrieval Index    │
                                                        │ (ChromaDB embeddings +   │
                                                        │   BM25 hybrid)           │
                                                        └────────────┬────────────┘
                                                                     │
                                                        ┌────────────▼────────────┐
                                                        │  Document Corpus (.md)   │
                                                        │  operating procedures,   │
                                                        │  manuals, guides, safety │
                                                        └──────────────────────────┘
```

A rendered version of this diagram is at `docs/architecture-diagram.png`.

## Layer responsibilities (mapped to files)

| Layer | Location | Responsibility |
|---|---|---|
| User interface | `apps/frontend/app.py` | Chat, alarm summary panel, citations, MCP trace, loading/error/empty states |
| Copilot orchestration | `apps/backend/orchestrator/` | Agentic loop: tool discovery, planning, multi-step chaining, combining MCP + RAG evidence |
| MCP client / tool registry | `apps/backend/mcp_client/` | Discovery, schema-aware invocation, typed error handling, execution trace |
| Candidate MCP server | `mcp-servers/alarm-management/server/` | Typed tools, input/output schemas, validation, auth, retry/timeout, error mapping, trace propagation |
| API / source-system connector | `connectors/alarm_api/` | Reusable HTTP client for the Alarm Management API (used only by the MCP server) |
| Alarm Management API simulator | `apps/alarm-api/app/` | Synthetic REST backend implementing the reference Postman contract |
| RAG ingestion | `rag/ingestion/` | Document loading, frontmatter parsing, chunking, index building |
| Retrieval service | `rag/retrieval/` | Hybrid dense (ChromaDB, sentence-transformer embeddings) + BM25 search, filtering, citations, low-confidence handling, injection defense |
| Domain models | `mcp-servers/alarm-management/server/schemas.py`, `apps/backend/models/` | Typed Pydantic contracts |
| Authentication & configuration | `connectors/alarm_api/config.py`, `apps/*/config`, `.env.example` | Environment-driven config, bearer auth, no secrets in code |
| Observability | `apps/alarm-api/app/middleware.py`, structured logging throughout | trace_id / client_id propagation, structured logs, execution trace surfaced to the GUI |
| Persistence | `rag/index/` (retrieval index on disk); alarm/asset data is in-memory (simulator) | See known-limitations.md |

## Why this separation

- The copilot backend **never** calls the Alarm Management API directly -- every
  alarm-data operation goes through the MCP client → MCP server → connector chain.
  This is enforced structurally: `apps/backend` has no dependency on
  `connectors/alarm_api`.
- The **connector** is a separate package from the **MCP server** so it is reusable
  (e.g. by a second MCP server, or a batch job) and independently unit-testable
  against an in-process ASGI transport (no real network needed in tests).
- The **LLM provider** is behind an abstract interface (`apps/backend/llm/base.py`)
  so switching providers is an environment-variable change, not a code change.
- **RAG and MCP share one orchestrator loop** (`agent.py`), not two separate code
  paths, which is what the assignment's "Mandatory Combined Workflow" requires.
