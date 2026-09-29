"""Anthropic (Claude) implementation of the LlmProvider interface."""

from __future__ import annotations

import logging

from apps.backend.llm.base import (
    LlmMessage,
    LlmProvider,
    LlmProviderError,
    LlmTurn,
    ToolCall,
    ToolSpec,
)

logger = logging.getLogger("llm.anthropic")


class AnthropicProvider(LlmProvider):
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise LlmProviderError("LLM_API_KEY is not set for LLM_PROVIDER=anthropic")
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise LlmProviderError("The 'anthropic' package is required for LLM_PROVIDER=anthropic") from exc
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    def _to_anthropic_messages(self, messages: list[LlmMessage]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "content": m.content or ""})
            elif m.role == "assistant":
                blocks: list[dict] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
                out.append({"role": "assistant", "content": blocks})
            elif m.role == "tool":
                out.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id,
                                "content": m.content or "",
                            }
                        ],
                    }
                )
        return out

    async def generate(self, system_prompt: str, messages: list[LlmMessage], tools: list[ToolSpec]) -> LlmTurn:
        anthropic_tools = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                messages=self._to_anthropic_messages(messages),
                tools=anthropic_tools,
            )
        except Exception as exc:
            raise LlmProviderError(f"Anthropic API call failed: {exc}") from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))

        return LlmTurn(content="\n".join(text_parts) if text_parts else None, tool_calls=tool_calls)
