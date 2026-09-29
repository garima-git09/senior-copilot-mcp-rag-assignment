"""Provider-agnostic LLM abstraction.

The orchestrator only ever talks to this interface, never to a specific
vendor SDK. Swapping the LLM is a matter of changing LLM_PROVIDER and
LLM_API_KEY in the environment (see .env.example) -- no code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LlmMessage:
    role: Literal["user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # set on role="tool" messages
    tool_name: str | None = None


@dataclass
class LlmTurn:
    """One assistant turn: either it wants to call tools, or it has a final answer."""

    content: str | None
    tool_calls: list[ToolCall]

    @property
    def is_final(self) -> bool:
        return not self.tool_calls


class LlmProviderError(Exception):
    """Raised when the LLM provider call fails (auth, rate limit, network)."""


class LlmToolCallValidationError(LlmProviderError):
    """Raised when the provider's OWN function-calling layer rejects a tool
    call as malformed (e.g. missing a required field) before ever returning
    it to us as a normal LlmTurn.

    This is a distinct failure point from an MCP-side schema rejection
    (McpInvalidArgumentsError in mcp_client/exceptions.py): that one happens
    *after* the model successfully proposes a tool call, when our own MCP
    client sends it on to the MCP server and the server's schema validation
    rejects it -- in that case we already have the malformed call recorded
    and can feed the MCP server's error back to the model as a normal tool
    result. Here, the provider (Groq/OpenAI) refuses to even hand back a
    completion containing the bad call, so there is no ToolCall object and
    no tool_call_id to attach a corrective tool-result message to. The
    orchestrator has to construct a corrective *user*-role message instead
    and let the model retry the whole turn -- see agent.py's handling of
    this exception type.
    """

    def __init__(self, message: str, tool_name: str | None = None, attempted_arguments: dict | None = None) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.attempted_arguments = attempted_arguments


class LlmProvider(ABC):
    @abstractmethod
    async def generate(self, system_prompt: str, messages: list[LlmMessage], tools: list[ToolSpec]) -> LlmTurn:
        """Send the conversation + tool specs to the model and return the next turn."""
        raise NotImplementedError
