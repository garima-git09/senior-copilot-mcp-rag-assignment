"""Copilot backend: FastAPI service that wires together the MCP client, the
RAG retrieval tool, and the pluggable LLM provider behind a small HTTP API
consumed by the Streamlit GUI.

Run standalone:
    uvicorn apps.backend.main:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from apps.backend.config.settings import settings
from apps.backend.llm.base import LlmMessage, LlmProviderError
from apps.backend.llm.factory import get_llm_provider
from apps.backend.mcp_client.client import AlarmMcpClient
from apps.backend.mcp_client.exceptions import McpServerUnavailableError
from apps.backend.models.api_models import (
    ChatRequest,
    ChatResponse,
    ToolCatalogEntry,
    ToolCatalogResponse,
    ToolExecutionEventOut,
)
from apps.backend.orchestrator.agent import AlarmInvestigationOrchestrator
from apps.backend.rag_client.tool import RagTool
from rag.ingestion.index_builder import build_index
from rag.retrieval.retriever import DocumentRetriever

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("copilot_backend")

# In-memory conversation store: {conversation_id: [LlmMessage, ...]}. This is
# intentionally simple (no external persistence dependency) -- see
# docs/known-limitations.md.
_conversations: dict[str, list[LlmMessage]] = {}


def _ensure_index() -> DocumentRetriever:
    index_dir = Path(settings.vector_store_url)
    if not (index_dir / "index_manifest.json").exists():
        logger.info("rag_index_missing building_now document_path=%s index_path=%s", settings.document_path, settings.vector_store_url)
        build_index(settings.document_path, settings.vector_store_url, embedding_model=settings.embedding_model)
    return DocumentRetriever(settings.vector_store_url, embedding_model=settings.embedding_model)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mcp_client = AlarmMcpClient(settings.mcp_server_url)
    app.state.retriever = _ensure_index()
    app.state.rag_tool = RagTool(app.state.retriever, top_k=settings.rag_top_k, min_score=settings.rag_min_score)
    try:
        app.state.llm_provider = get_llm_provider(settings)
        app.state.llm_error = None
    except LlmProviderError as exc:
        # Defer the failure to request time so the service still starts (and
        # /health still responds) even if LLM_API_KEY has not been set yet.
        logger.warning("llm_provider_unavailable_at_startup error=%s", exc)
        app.state.llm_provider = None
        app.state.llm_error = str(exc)
    app.state.orchestrator = None
    yield


app = FastAPI(title="Alarm Investigation Copilot Backend", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _get_orchestrator(app_state) -> AlarmInvestigationOrchestrator:
    if app_state.llm_provider is None:
        raise HTTPException(status_code=503, detail=f"LLM provider not configured: {app_state.llm_error}")
    if app_state.orchestrator is None:
        app_state.orchestrator = AlarmInvestigationOrchestrator(app_state.mcp_client, app_state.rag_tool, app_state.llm_provider)
    return app_state.orchestrator


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "copilot-backend"}


@app.get("/tools", response_model=ToolCatalogResponse)
async def list_tools() -> ToolCatalogResponse:
    """Powers the GUI's 'MCP tool discovery' view."""
    try:
        tools = await app.state.mcp_client.discover_tools()
    except McpServerUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"MCP server unavailable: {exc}") from exc
    return ToolCatalogResponse(
        mcp_server_url=settings.mcp_server_url,
        tools=[ToolCatalogEntry(name=t.name, description=t.description, input_schema=t.input_schema, output_schema=t.output_schema) for t in tools],
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    orchestrator = _get_orchestrator(app.state)
    history = _conversations.setdefault(request.conversation_id, [])

    result = await orchestrator.handle_message(request.message, history)

    history.append(LlmMessage(role="user", content=request.message))
    history.append(LlmMessage(role="assistant", content=result.answer))
    # Keep conversation history bounded so a long-running session doesn't
    # grow the LLM context unboundedly.
    _conversations[request.conversation_id] = history[-20:]

    return ChatResponse(
        conversation_id=request.conversation_id,
        answer=result.answer,
        events=[ToolExecutionEventOut(**vars(e)) for e in result.events],
        citations=result.citations,
        degraded=result.degraded,
        degraded_reasons=result.degraded_reasons,
        iterations=result.iterations,
    )


@app.post("/conversations/{conversation_id}/reset")
async def reset_conversation(conversation_id: str) -> dict:
    _conversations.pop(conversation_id, None)
    return {"status": "reset", "conversation_id": conversation_id}
