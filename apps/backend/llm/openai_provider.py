"""OpenAI implementation of the LlmProvider interface.

Included to demonstrate the replaceable-LLM-provider requirement: switching
LLM_PROVIDER=openai and supplying an OpenAI-compatible LLM_API_KEY /
LLM_MODEL (e.g. gpt-4o) is enough -- no orchestrator code changes.
"""

from __future__ import annotations

import json
import logging
import re

from apps.backend.llm.base import (
    LlmMessage,
    LlmProvider,
    LlmProviderError,
    LlmToolCallValidationError,
    LlmTurn,
    ToolCall,
    ToolSpec,
)

logger = logging.getLogger("llm.openai")

# Groq/OpenAI's function-calling layer validates a proposed tool call against
# its JSON schema *before* handing anything back to us, and on rejection
# raises an HTTP 400 with code "tool_use_failed" (observed with Groq's
# openai/gpt-oss models -- e.g. the model omits a required field, or invents
# one that isn't in the schema). This is a distinct failure point from an
# MCP-side schema rejection (see McpInvalidArgumentsError / server/app.py's
# @mcp.tool validation): that one happens *after* a valid-shaped tool call
# reaches the MCP server; this happens *before* we ever see a tool call at
# all. Because the provider's exception message format isn't part of any
# stable public contract, this pattern-matches its known shape defensively --
# if the shape doesn't match (a different provider, an SDK version change),
# the code falls back to a plain LlmProviderError, which still surfaces the
# failure (just without a chance for the model to self-correct).
_TOOL_USE_FAILED_RE = re.compile(r"'code':\s*'tool_use_failed'")
_FAILED_GENERATION_RE = re.compile(r"'failed_generation':\s*'((?:[^'\\]|\\.)*)'")


class OpenAiProvider(LlmProvider):
    """OpenAI-compatible provider.

    Also used for any other vendor that implements the OpenAI chat-completions
    API shape (e.g. Groq), by passing a different ``base_url``. This keeps the
    provider abstraction genuinely pluggable without adding a new SDK/class
    per OpenAI-compatible vendor.
    """

    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        if not api_key:
            raise LlmProviderError("LLM_API_KEY is not set for this LLM_PROVIDER")
        try:
            import openai
        except ImportError as exc:  # pragma: no cover
            raise LlmProviderError("The 'openai' package is required for this LLM_PROVIDER") from exc
        # A generous max_retries matters most for OpenAI-compatible free tiers
        # with tight per-minute token limits (e.g. Groq's free tier: 8000
        # TPM shared across the whole conversation, including all tool
        # schemas resent every call). The SDK's default retry count gives up
        # after a couple of 429s even though the provider's own error message
        # says "try again in ~5s" -- a real transient condition, not a hard
        # failure. Retrying more patiently (with the SDK's built-in backoff)
        # converts most of these into an eventual success instead of an
        # error surfaced to the user.
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=6)
        self.model = model

    def _to_openai_messages(self, system_prompt: str, messages: list[LlmMessage]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system_prompt}]
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "content": m.content or ""})
            elif m.role == "assistant":
                msg: dict = {"role": "assistant", "content": m.content}
                if m.tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in m.tool_calls
                    ]
                out.append(msg)
            elif m.role == "tool":
                out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content or ""})
        return out

    async def generate(self, system_prompt: str, messages: list[LlmMessage], tools: list[ToolSpec]) -> LlmTurn:
        openai_tools = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}} for t in tools]
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=self._to_openai_messages(system_prompt, messages),
                tools=openai_tools,
            )
        except Exception as exc:
            raw = str(exc)
            if _TOOL_USE_FAILED_RE.search(raw):
                tool_name = None
                arguments = None
                match = _FAILED_GENERATION_RE.search(raw)
                if match:
                    try:
                        generation = match.group(1).encode().decode("unicode_escape")
                        parsed = json.loads(generation)
                        tool_name = parsed.get("name")
                        arguments = parsed.get("arguments")
                    except (ValueError, json.JSONDecodeError):
                        logger.warning("tool_use_failed_generation_unparseable raw=%s", raw[:500])
                raise LlmToolCallValidationError(
                    f"The model's proposed call to '{tool_name or 'a tool'}' was rejected by the "
                    f"provider's own schema validation before it reached the MCP server: {raw}",
                    tool_name=tool_name,
                    attempted_arguments=arguments,
                ) from exc
            raise LlmProviderError(f"OpenAI API call failed: {exc}") from exc

        choice = response.choices[0].message
        tool_calls = [ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments or "{}")) for tc in (choice.tool_calls or [])]
        return LlmTurn(content=choice.content, tool_calls=tool_calls)
