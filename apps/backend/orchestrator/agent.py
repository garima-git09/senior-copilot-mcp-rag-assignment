"""The copilot orchestrator: a general (not hard-coded) agentic loop that
lets the LLM plan its own investigation, discovering and chaining MCP tools
and interleaving RAG document lookups, until it has enough evidence to give
a grounded, cited answer.

This is the one place in the system where the "Mandatory Combined Workflow"
requirement is realized: MCP tool calls and RAG retrieval happen inside the
same loop, informing the same final answer, not as two separate demos.
"""

from __future__ import annotations

import json
import logging
import re
import time

from apps.backend.llm.base import (
    LlmMessage,
    LlmProvider,
    LlmProviderError,
    LlmToolCallValidationError,
    ToolCall,
    ToolSpec,
)
from apps.backend.mcp_client.client import AlarmMcpClient
from apps.backend.mcp_client.exceptions import (
    McpClientError,
    McpInvalidArgumentsError,
    McpServerUnavailableError,
    McpToolExecutionError,
    McpToolNotFoundError,
)
from apps.backend.orchestrator.prompts import SYSTEM_PROMPT
from apps.backend.orchestrator.trace import OrchestrationResult, ToolExecutionEvent
from apps.backend.rag_client.tool import SEARCH_DOCUMENTS_TOOL, RagTool

logger = logging.getLogger("orchestrator")

# 8 was the original budget; raised to 12 after real-world testing showed a
# smaller free-tier model (Groq's openai/gpt-oss-20b) sometimes keeps
# re-querying with overlapping filters instead of converging. Raised again to
# 16 once rate limiting was no longer the bottleneck (a paid/Dev Tier Groq
# account has ample throughput, so a few extra reasoning steps cost seconds,
# not minutes) and the model was still legitimately investigating multiple
# related assets when it ran out of steps. Paired with an explicit "stop
# investigating once you have enough evidence" instruction in the system
# prompt (prompts.py) so the extra budget is a safety margin, not a license
# to loop indefinitely.
MAX_ITERATIONS = 16

_OUTCOME_BY_EXCEPTION = {
    McpToolNotFoundError: "tool_not_found",
    McpInvalidArgumentsError: "invalid_arguments",
    McpToolExecutionError: "execution_error",
    McpServerUnavailableError: "unavailable",
}

# Every tool result is appended to the conversation and re-sent to the LLM on
# every subsequent iteration. An unshrunk get_alarms page (or a large RAG
# excerpt list) can make that payload grow past a small-tier LLM provider's
# per-request token limit (seen in practice: Groq's free tier caps at 8000
# TPM for openai/gpt-oss-20b) a few tool calls into an investigation. Shrink
# large list fields before they go back to the LLM -- the MCP tool's actual
# response to the *client* is untouched; this only bounds what re-enters the
# conversation history.
_MAX_LIST_ITEMS_FOR_LLM = 8
_MAX_TOOL_RESULT_CHARS_FOR_LLM = 4000


# Some LLM providers/models (observed with Groq's openai/gpt-oss models,
# which use an internal "harmony" channel format to separate tool calls from
# visible content) occasionally leak fragments of that internal tool-call
# syntax into the final answer text instead of keeping it fully out of band
# -- e.g. "...reads as vibration【assistant to=functions.search_documents】"
# or a stray "<|constrain|>json_output" token. This is a model/provider
# quirk, unrelated to RAG retrieval or MCP tool execution: the underlying
# evidence and citations are still correct, only the rendered text is
# polluted. Defense in depth: the system prompt (prompts.py) explicitly
# tells the model never to include this syntax, and this regex strips any
# that leaks through anyway before the answer reaches the GUI.
_LEAKED_TOOL_SYNTAX_RE = re.compile(
    r"【[^】]*】"  # a full 【...】 bracketed block, whatever it contains
    r"|<\|[^|]*\|>"  # a <|...|> special-token marker
    r"|\{?assistant to=functions\.[a-zA-Z0-9_.]*\}?"  # a bare "assistant to=functions.X" fragment outside brackets
)


def _sanitize_answer(text: str) -> str:
    """Strip any leaked internal tool-call/channel syntax from a final answer
    before it is shown to the user. Collapses the whitespace left behind so
    removing a mid-sentence token doesn't leave an awkward double space.
    """
    if not text:
        return text
    cleaned = _LEAKED_TOOL_SYNTAX_RE.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n[ \t]+", "\n", cleaned)
    return cleaned.strip()


def _shrink_for_llm(value: object) -> str:
    if isinstance(value, dict):
        shrunk: dict[str, object] = {}
        for key, item in value.items():
            if isinstance(item, list) and len(item) > _MAX_LIST_ITEMS_FOR_LLM:
                shrunk[key] = item[:_MAX_LIST_ITEMS_FOR_LLM]
                note = f"showing first {_MAX_LIST_ITEMS_FOR_LLM} of {len(item)} items (truncated to fit the LLM's context/rate limit)"
                shrunk[f"{key}_note"] = note
            else:
                shrunk[key] = item
        value = shrunk

    text = json.dumps(value, default=str)
    if len(text) > _MAX_TOOL_RESULT_CHARS_FOR_LLM:
        text = text[:_MAX_TOOL_RESULT_CHARS_FOR_LLM] + '..."(truncated)'
    return text


class AlarmInvestigationOrchestrator:
    def __init__(self, mcp_client: AlarmMcpClient, rag_tool: RagTool, llm_provider: LlmProvider) -> None:
        self.mcp_client = mcp_client
        self.rag_tool = rag_tool
        self.llm = llm_provider

    async def _build_tool_specs(self) -> tuple[list[ToolSpec], str | None]:
        """Discover MCP tools. If the MCP server itself is unreachable, degrade
        gracefully: the copilot still has the RAG tool available and can say
        so explicitly, rather than crashing the whole conversation turn.
        """
        try:
            mcp_tools = await self.mcp_client.discover_tools()
        except McpServerUnavailableError as exc:
            logger.warning("mcp_discovery_failed error=%s", exc)
            return [SEARCH_DOCUMENTS_TOOL], str(exc)
        specs = [ToolSpec(name=t.name, description=t.description, input_schema=t.input_schema) for t in mcp_tools]
        specs.append(SEARCH_DOCUMENTS_TOOL)
        return specs, None

    async def _execute_tool_call(self, call: ToolCall, step: int) -> tuple[str, ToolExecutionEvent]:
        started = time.perf_counter()

        if call.name == "search_documents":
            try:
                result = self.rag_tool.run(
                    query=call.arguments.get("query", ""),
                    doc_type=call.arguments.get("doc_type"),
                    asset_type=call.arguments.get("asset_type"),
                )
            except Exception as exc:  # noqa: BLE001 - RAG failure should degrade gracefully, not crash the chat
                duration = round((time.perf_counter() - started) * 1000, 2)
                event = ToolExecutionEvent(
                    step=step,
                    tool_name=call.name,
                    tool_kind="rag",
                    arguments=call.arguments,
                    outcome="execution_error",
                    duration_ms=duration,
                    trace_id=None,
                    result_preview=None,
                    error=str(exc),
                )
                return json.dumps({"error": str(exc)}), event

            duration = round((time.perf_counter() - started) * 1000, 2)
            outcome = "low_confidence" if result.get("low_confidence") else "success"
            event = ToolExecutionEvent(
                step=step,
                tool_name=call.name,
                tool_kind="rag",
                arguments=call.arguments,
                outcome=outcome,
                duration_ms=duration,
                trace_id=None,
                result_preview=result.get("citations"),
            )
            return _shrink_for_llm(result), event

        # Otherwise: an MCP tool call.
        try:
            result = await self.mcp_client.call_tool(call.name, call.arguments)
            duration = round((time.perf_counter() - started) * 1000, 2)
            record = self.mcp_client.call_log[-1] if self.mcp_client.call_log else None
            event = ToolExecutionEvent(
                step=step,
                tool_name=call.name,
                tool_kind="mcp",
                arguments=call.arguments,
                outcome="success",
                duration_ms=duration,
                trace_id=record.trace_id if record else None,
                result_preview=record.result_preview if record else None,
            )
            return _shrink_for_llm(result), event
        except McpClientError as exc:
            duration = round((time.perf_counter() - started) * 1000, 2)
            outcome = _OUTCOME_BY_EXCEPTION.get(type(exc), "execution_error")
            record = self.mcp_client.call_log[-1] if self.mcp_client.call_log else None
            event = ToolExecutionEvent(
                step=step,
                tool_name=call.name,
                tool_kind="mcp",
                arguments=call.arguments,
                outcome=outcome,
                duration_ms=duration,
                trace_id=record.trace_id if record else None,
                result_preview=None,
                error=str(exc),
            )
            # Feed the error back to the LLM as a tool result (not a crash) so
            # it can adapt: skip that step, try an alternative tool, or note
            # the gap in its final answer. This is the "graceful handling of
            # unavailable tools / partial failures" requirement.
            return json.dumps({"error": str(exc), "outcome": outcome}), event

    async def handle_message(self, user_text: str, conversation_history: list[LlmMessage] | None = None) -> OrchestrationResult:
        tools, discovery_error = await self._build_tool_specs()
        messages: list[LlmMessage] = list(conversation_history or [])
        messages.append(LlmMessage(role="user", content=user_text))

        events: list[ToolExecutionEvent] = []
        citations: list[dict] = []
        degraded_reasons: list[str] = []
        step = 0

        if discovery_error:
            degraded_reasons.append(f"mcp_server_unavailable: {discovery_error}")
            messages.append(
                LlmMessage(
                    role="user",
                    content=(
                        "[system notice] The alarm-management MCP server is currently unreachable, so no "
                        "Alarm Management API tools are available for this turn. Only search_documents can be "
                        "used. Tell the user the alarm data source is unavailable and answer using document "
                        "guidance only, where possible."
                    ),
                )
            )

        provider_validation_retries = 0
        for iteration in range(1, MAX_ITERATIONS + 1):
            try:
                turn = await self.llm.generate(SYSTEM_PROMPT, messages, tools)
            except LlmToolCallValidationError as exc:
                # The provider's own function-calling layer rejected a
                # malformed tool call before we ever saw a ToolCall object
                # (see LlmToolCallValidationError's docstring for how this
                # differs from an MCP-side schema rejection). There is no
                # tool_call_id to attach a corrective "tool" message to, so
                # we inject a plain user-role notice describing exactly what
                # was rejected and ask the model to retry with a corrected
                # call -- mirroring, as closely as this failure point
                # allows, the self-correction we already get for free on the
                # MCP-side path (McpInvalidArgumentsError below).
                step += 1
                event = ToolExecutionEvent(
                    step=step,
                    tool_name=exc.tool_name or "unknown",
                    tool_kind="mcp",
                    arguments=exc.attempted_arguments or {},
                    outcome="invalid_arguments",
                    duration_ms=0.0,
                    trace_id=None,
                    result_preview=None,
                    error=str(exc),
                )
                events.append(event)
                degraded_reasons.append(f"provider_rejected_tool_call: {exc.tool_name}")
                provider_validation_retries += 1
                if provider_validation_retries > 3:
                    return OrchestrationResult(
                        answer=(
                            "I could not complete this investigation: the model repeatedly proposed "
                            "invalid tool calls that the provider rejected before they could run. "
                            f"Last rejection: {exc}"
                        ),
                        events=events,
                        citations=citations,
                        degraded=True,
                        degraded_reasons=degraded_reasons,
                        iterations=iteration,
                    )
                messages.append(
                    LlmMessage(
                        role="user",
                        content=(
                            f"[system notice] Your previous attempt to call the tool "
                            f"'{exc.tool_name}' with arguments {json.dumps(exc.attempted_arguments or {})} "
                            f"was rejected before it could run, because it did not match that tool's "
                            f"required input schema. Check the tool's schema again (especially required "
                            f"fields such as time_range) and either retry that tool with corrected "
                            f"arguments, or use a different tool/approach."
                        ),
                    )
                )
                continue
            except LlmProviderError as exc:
                return OrchestrationResult(
                    answer=(f"I could not reach the language model provider, so I can't complete this investigation right now. Details: {exc}"),
                    events=events,
                    citations=citations,
                    degraded=True,
                    degraded_reasons=[f"llm_provider_error: {exc}"],
                    iterations=iteration,
                )

            if turn.is_final:
                return OrchestrationResult(
                    answer=_sanitize_answer(turn.content or ""),
                    events=events,
                    citations=citations,
                    degraded=bool(degraded_reasons),
                    degraded_reasons=degraded_reasons,
                    iterations=iteration,
                )

            messages.append(LlmMessage(role="assistant", content=turn.content, tool_calls=turn.tool_calls))

            for call in turn.tool_calls:
                step += 1
                tool_result_text, event = await self._execute_tool_call(call, step)
                events.append(event)
                if event.outcome != "success":
                    degraded_reasons.append(f"{event.tool_name}: {event.outcome}" + (f" ({event.error})" if event.error else ""))
                if event.tool_kind == "rag" and event.outcome == "success":
                    try:
                        parsed = json.loads(tool_result_text)
                        citations.extend(parsed.get("citations", []))
                    except (json.JSONDecodeError, AttributeError):
                        pass
                messages.append(LlmMessage(role="tool", content=tool_result_text, tool_call_id=call.id, tool_name=call.name))

        return OrchestrationResult(
            answer="I was unable to complete this investigation within the allotted reasoning steps. Please narrow the question or try again.",
            events=events,
            citations=citations,
            degraded=True,
            degraded_reasons=degraded_reasons + ["max_iterations_exceeded"],
            iterations=MAX_ITERATIONS,
        )
