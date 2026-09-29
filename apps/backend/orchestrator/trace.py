"""Data structures describing one full orchestration run, used both as the
API response payload and as the source of the GUI's execution-trace panel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolExecutionEvent:
    step: int
    tool_name: str
    tool_kind: str  # "mcp" | "rag"
    arguments: dict[str, Any]
    outcome: str  # "success" | "invalid_arguments" | "tool_not_found" | "execution_error" | "unavailable" | "low_confidence"
    duration_ms: float
    trace_id: str | None
    result_preview: Any
    error: str | None = None


@dataclass
class OrchestrationResult:
    answer: str
    events: list[ToolExecutionEvent] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    degraded: bool = False
    degraded_reasons: list[str] = field(default_factory=list)
    iterations: int = 0
