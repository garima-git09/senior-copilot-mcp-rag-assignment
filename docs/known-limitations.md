# Known Limitations

- **Docker build could not be executed inside the development sandbox used to
  build this submission.** The sandbox's network egress is restricted to pip/
  npm/GitHub, so `docker pull python:3.11-slim` was blocked (`Forbidden` from
  the registry). `docker compose config` was used to validate the compose
  file's syntax and service graph, and every service's application code was
  instead validated directly with isolated virtualenvs mirroring each
  container's `requirements.txt` (67 automated tests passing, including a
  session that ran the real `alarm-management` MCP server over streamable-HTTP
  and a FastAPI TestClient exercising the full backend). On a machine with
  normal Docker Hub access, `docker compose up --build` is expected to work
  as documented; please re-verify on first run and report any image-layer
  issue.
- **Retrieval uses a real sentence-transformer embedding model + ChromaDB,
  fused with BM25** (see `docs/rag-design.md` for the full history — this
  replaced an earlier TF-IDF-based version once network access to a model hub
  was confirmed available). Ingestion now requires outbound network access on
  first run to download `sentence-transformers/all-MiniLM-L6-v2` from Hugging
  Face (cached locally afterwards, so restarts don't need it again); a fully
  offline/air-gapped deployment would need to pre-bake the model into the
  image or fall back to the lexical-only TF-IDF path this project used
  previously. ChromaDB itself runs embedded/in-process (`PersistentClient`),
  not as a separately-hosted service, so there is no distributed vector-DB
  story (replication, horizontal scaling) here — acceptable for a
  single-instance investigation copilot over a small (10 document, 44 chunk)
  corpus, not for a large multi-tenant deployment. `RAG_MIN_SCORE` (default
  0.35) was tuned against the current corpus and current fusion weights; a
  larger, more topically diverse corpus would need re-tuning either way.
- **The test suite never downloads the real embedding model.** Both
  `build_index()` and `DocumentRetriever` accept an injectable `embed_fn`, and
  the automated tests inject a small deterministic hashing-trick fake
  embedder (`rag/tests/fake_embedder.py`) instead. This keeps CI fast and
  network-free, but it also means the test suite does not exercise the real
  model's actual semantic-similarity behavior — only the retrieval
  *pipeline* (fusion, filtering, thresholding, citations) is covered by
  automated tests; semantic retrieval quality was spot-checked manually
  against the real model instead.
- **No persistent database.** Alarm/asset data lives in-memory in the
  simulator process (regenerated deterministically from a fixed seed on
  restart); conversation history lives in-memory in the copilot backend
  process (bounded to the last 20 messages, lost on restart). Neither is
  durable across a restart — acceptable for a single-session investigation
  copilot, not for multi-instance production deployment.
- **Prompt-injection defense is heuristic, not exhaustive.** Detection uses a
  fixed set of regex patterns (`rag/retrieval/injection_guard.py`); a
  sufficiently reworded injection attempt could evade detection, though every
  retrieved chunk is still fenced as untrusted data in the prompt regardless
  of whether it was flagged, which is the primary defense layer.
- **No write/ticketing operations are implemented** for this use case (the
  assigned scenario is read-only investigation). If a future iteration adds
  one, the assignment's security expectations (explicit user confirmation
  before execution) must be implemented for it.
- **Single-tenant, no persistence of per-user identity.** There is no login;
  `conversation_id` is a client-generated UUID with no authentication of its
  own. Fine for a local/demo deployment, not for a shared production
  instance.
- **LLM tool-calling loop testing is scripted, not live-model-verified in
  this submission's sandbox.** No live Anthropic/OpenAI API key was available
  in the build environment, so `tests/integration/test_orchestrator.py` and
  `tests/e2e/test_combined_workflow.py` use a small scripted `LlmProvider`
  stand-in to deterministically exercise the orchestrator's tool-execution,
  chaining, and error-handling logic. The `AnthropicProvider` /
  `OpenAiProvider` request/response mapping code itself is exercised by
  `tests/unit/test_llm_factory.py` and should be smoke-tested against a real
  key before the demo recording.
- **Tool results are shrunk before being fed back to the LLM** (`apps/backend/orchestrator/agent.py::_shrink_for_llm`). A large `get_alarms` page can otherwise make the growing conversation exceed a low-tier LLM provider's per-request token limit a few tool calls into an investigation (observed in practice: Groq's free tier caps `openai/gpt-oss-20b` at 8000 tokens/minute). List-valued fields over 8 items are truncated with a note of how many were omitted; this only affects what re-enters the LLM's context, not the MCP tool's actual response to the client, and not the GUI's own (separately bounded) preview of the same result.
- **Correlation/rationalization results depend on the synthetic data's random
  seed.** Because the simulator's alarm history is procedurally generated
  (deterministic seed, but still randomized event placement), a specific
  numeric example in this documentation may not exactly match a fresh run if
  `ALARM_API_SEED` or the document corpus changes.
