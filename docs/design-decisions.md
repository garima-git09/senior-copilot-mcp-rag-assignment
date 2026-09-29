# Design Decisions

## Language & stack: Python + FastAPI + Streamlit

Python across every service (simulator, MCP server, backend) keeps one
runtime, one dependency ecosystem, and lets the official `mcp` Python SDK
drive both the server and the client. Streamlit was chosen over a
React/Vue frontend for build speed within the assignment's time box while
still satisfying every GUI requirement (chat, structured panels, trace
inspection, loading/error states, env-var configuration).

## LLM provider: pluggable, no hard-coded fallback

Per explicit direction for this build: no deterministic rule-based planner
fallback was implemented. `LLM_PROVIDER` selects between Anthropic, OpenAI,
and Groq via `apps/backend/llm/factory.py`; adding a further provider means
implementing `LlmProvider.generate()` once (`apps/backend/llm/base.py`) — no
orchestrator change. Groq specifically reuses `OpenAiProvider` with a
different `base_url` rather than a new class, since Groq implements the same
OpenAI chat-completions request/response shape — it was added so the
submission can be smoke-tested without a funded OpenAI account (Groq's free
tier needs no card). If `LLM_API_KEY` is missing or invalid, `/chat` returns
a clear 503 rather than crashing, and `/health` still reports the service as
up.

## Planner: general agentic tool-calling loop, not a hard-coded sequence

`apps/backend/orchestrator/agent.py` gives the LLM the full discovered tool
list (MCP tools + `search_documents`) every turn and lets it decide which
tools to call and in what order, up to `MAX_ITERATIONS` (12 -- raised from an
initial 8 after real-world testing with a smaller free-tier model showed it
sometimes needs a few extra steps to converge; the system prompt separately
instructs the model to stop investigating once it has enough evidence, so
the higher budget is a safety margin rather than an invitation to loop).
Nothing branches
on the literal text of the example questions from the assignment brief — the
same loop handles "show active alarms for X", "why do compressor alarms keep
firing", or an entirely new question, because the tool schemas (not
if/elif string matching) are what the model reasons over.

## Embeddings: real sentence-transformer model + BM25 hybrid (was TF-IDF)

See `docs/rag-design.md` for the full rationale and history. The project
originally used TF-IDF instead of a downloaded embedding model, specifically
because a downloaded model needs network access that isn't guaranteed in
every environment this runs in, and TF-IDF is a documented, allowed
"equivalent retrieval approach" for a corpus this size. Once network access
to a model hub was confirmed available in the deployment environment, this
was revisited: `sentence-transformers/all-MiniLM-L6-v2` real embeddings
replace TF-IDF for the dense signal (BM25 keyword matching is unchanged),
because real embeddings capture paraphrases/synonyms that pure lexical
overlap cannot. The embedding function stayed behind a small injectable
interface (`EmbedFn`) throughout this change, so the test suite never needed
network access even after production switched to a real model.

## Vector store: ChromaDB (embedded), not a hosted vector DB service

Dense vectors are stored in a **ChromaDB** collection via `PersistentClient`
(embedded/in-process, on-disk under `rag/index/local/chroma/`) rather than a
separately-run Chroma/Pinecone/Weaviate service. This gives a real vector
database (similarity search, metadata storage) without adding an extra
container or network hop -- `docker compose up --build` still starts exactly
one backend process. BM25 and chunk metadata remain plain local
`pickle`/`jsonl` files alongside the Chroma directory. See
`docs/known-limitations.md` for what this embedded deployment mode trades off
against a separately-hosted vector database service.

## Alarm Management API simulator: synthetic, fixed-window data

The simulator's alarm history is generated with a **fixed** time window
(`2026-05-01` .. `2026-07-01`) rather than "last 90 days from now". This was
a deliberate fix after an initial version generated data relative to the
current wall-clock date, which silently produced **empty results** for every
analytics query using the reference Postman collections' example time ranges.
A fixed window keeps every documented example query reproducible regardless
of when the simulator is started.

## MCP tool granularity: one tool per API capability

Rather than a single generic "call_alarm_api" tool, each capability
(`search_assets`, `get_alarms`, `correlate_alarms`, ...) is its own MCP tool
with its own typed schema. This is slightly more code but is what makes tool
descriptions, input validation, and the tool catalog genuinely meaningful to
an LLM planner and to a human reviewer — a single generic tool would just
move the API's schema into a string parameter and defeat MCP's purpose.

## MCP transport: streamable-HTTP

Chosen over stdio so the MCP server is independently runnable as a normal
network service (matches "must be independently runnable and testable" and
Docker Compose's service model) rather than requiring a client to spawn it as
a subprocess.

## Write operations

No ticketing/write-operation tool was implemented for this use case (the
assigned scenario is read-only investigation and recommendation). The
`.env.example` still documents a `TICKETING_API_URL` placeholder and
`docs/known-limitations.md` notes that any future write tool must require
explicit user confirmation before execution, per the assignment's security
expectations.
