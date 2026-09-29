"""Request/response models for the copilot backend's HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: str = "default"


class ToolExecutionEventOut(BaseModel):
    step: int
    tool_name: str
    tool_kind: str
    arguments: dict[str, Any]
    outcome: str
    duration_ms: float
    trace_id: str | None = None
    result_preview: Any = None
    error: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    events: list[ToolExecutionEventOut]
    citations: list[dict[str, Any]]
    degraded: bool
    degraded_reasons: list[str]
    iterations: int


class ToolCatalogEntry(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None


class ToolCatalogResponse(BaseModel):
    mcp_server_url: str
    tools: list[ToolCatalogEntry]
