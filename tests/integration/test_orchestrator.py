"""Orchestration tests: multi-step MCP chains, MCP output feeding subsequent
tools, RAG retrieval in the same workflow, combined answer generation,
partial source failure, and conflicting/degraded evidence.

The LLM is replaced with a small scripted stand-in (ScriptedLlm) so these
tests are deterministic and require no API key -- they test the
orchestrator's tool-execution and trace-building logic, not a real model's
reasoning quality (which cannot be asserted on deterministically anyway).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.backend.llm.base import LlmProvider, LlmToolCallValidationError, LlmTurn, ToolCall
from apps.backend.mcp_client.client import AlarmMcpClient
from apps.backend.orchestrator.agent import AlarmInvestigationOrchestrator
from apps.backend.rag_client.tool import RagTool
from rag.ingestion.index_builder import build_index
from rag.retrieval.retriever import DocumentRetriever
from rag.tests.fake_embedder import fake_embed_fn

pytestmark = pytest.mark.integration

DOCS_PATH = Path(__file__).resolve().parents[2] / "rag" / "documents"


@pytest.fixture(scope="module")
def rag_tool(tmp_path_factory) -> RagTool:
    index_dir = tmp_path_factory.mktemp("orchestrator_rag_index")
    build_index(str(DOCS_PATH), str(index_dir), embed_fn=fake_embed_fn)
    return RagTool(DocumentRetriever(str(index_dir), embed_fn=fake_embed_fn), top_k=5, min_score=0.35)


class ScriptedLlm(LlmProvider):
    """Replays a fixed script of tool calls, then a final answer."""

    def __init__(self, script: list[ToolCall], final_answer: str) -> None:
        self.script = script
        self.final_answer = final_answer
        self.step = 0

    async def generate(self, system_prompt, messages, tools):
        if self.step < len(self.script):
            call = self.script[self.step]
            self.step += 1
            return LlmTurn(content=None, tool_calls=[call])
        return LlmTurn(content=self.final_answer, tool_calls=[])


@pytest.mark.asyncio
async def test_full_mcp_and_rag_combined_workflow(mcp_server_url, rag_tool):
    """The mandatory combined workflow: asset resolution -> alarm retrieval ->
    document retrieval -> grounded answer with both MCP and RAG evidence.
    """
    mcp_client = AlarmMcpClient(mcp_server_url)
    llm = ScriptedLlm(
        script=[
            ToolCall(id="1", name="search_assets", arguments={"query": "Boiler Feed Pump 101"}),
        ],
        final_answer="placeholder",
    )
    orchestrator = AlarmInvestigationOrchestrator(mcp_client, rag_tool, llm)

    # Extend the script dynamically once we know the asset_id (mirrors how a
    # real LLM would chain outputs step by step).
    async def scripted_generate(system_prompt, messages, tools):
        llm.step += 1
        if llm.step == 1:
            return LlmTurn(content=None, tool_calls=[ToolCall(id="1", name="search_assets", arguments={"query": "Boiler Feed Pump 101"})])
        if llm.step == 2:
            last = json.loads(messages[-1].content)
            asset_id = last["results"][0]["asset_id"]
            return LlmTurn(content=None, tool_calls=[ToolCall(id="2", name="get_alarms", arguments={"asset_id": asset_id, "page": 1, "page_size": 5})])
        if llm.step == 3:
            return LlmTurn(content=None, tool_calls=[ToolCall(id="3", name="search_documents", arguments={"query": "boiler feed pump vibration procedure"})])
        return LlmTurn(
            content="Boiler Feed Pump 101 has recurring vibration alarms. Sources: search_assets, get_alarms, OP-101, MM-201.",
            tool_calls=[],
        )

    llm.generate = scripted_generate  # type: ignore[method-assign]

    result = await orchestrator.handle_message("Investigate recurring alarms for Boiler Feed Pump 101")

    tool_names = [e.tool_name for e in result.events]
    assert tool_names == ["search_assets", "get_alarms", "search_documents"]
    assert all(e.tool_kind == "mcp" for e in result.events[:2])
    assert result.events[2].tool_kind == "rag"
    assert not result.degraded
    assert result.citations, "expected RAG citations to be present in a combined-workflow answer"
    assert "OP-101" in result.answer or "MM-201" in result.answer


@pytest.mark.asyncio
async def test_partial_failure_is_reported_but_does_not_crash_the_turn(mcp_server_url, rag_tool):
    """A failing tool call (unknown asset) must show up as a degraded event,
    not raise out of the orchestrator.
    """

    class FailThenAnswerLlm(LlmProvider):
        def __init__(self):
            self.step = 0

        async def generate(self, system_prompt, messages, tools):
            self.step += 1
            if self.step == 1:
                return LlmTurn(content=None, tool_calls=[ToolCall(id="1", name="get_asset_metadata", arguments={"asset_id": "AST-does-not-exist"})])
            return LlmTurn(content="I could not find that asset. Please check the asset identifier.", tool_calls=[])

    mcp_client = AlarmMcpClient(mcp_server_url)
    orchestrator = AlarmInvestigationOrchestrator(mcp_client, rag_tool, FailThenAnswerLlm())

    result = await orchestrator.handle_message("metadata for asset AST-does-not-exist")

    assert result.degraded
    assert result.events[0].outcome == "execution_error"
    assert "could not find" in result.answer.lower()


@pytest.mark.asyncio
async def test_mcp_server_unavailable_degrades_to_rag_only(rag_tool):
    """If the whole MCP server is unreachable, the orchestrator must still
    respond (using only the RAG tool) instead of crashing the conversation.
    """

    class AnswerOnlyLlm(LlmProvider):
        async def generate(self, system_prompt, messages, tools):
            # Only search_documents should be offered when MCP is down.
            assert {t.name for t in tools} == {"search_documents"}
            return LlmTurn(content="The alarm system is unreachable; based on documented guidance only: ...", tool_calls=[])

    unreachable_client = AlarmMcpClient("http://127.0.0.1:1/mcp", timeout_seconds=2)
    orchestrator = AlarmInvestigationOrchestrator(unreachable_client, rag_tool, AnswerOnlyLlm())

    result = await orchestrator.handle_message("What should I do about a pump alarm?")

    assert result.degraded
    assert any("mcp_server_unavailable" in r for r in result.degraded_reasons)
    assert "unreachable" in result.answer.lower()


@pytest.mark.asyncio
async def test_low_confidence_rag_result_is_surfaced(mcp_server_url, rag_tool):
    class OnlySearchDocsLlm(LlmProvider):
        def __init__(self):
            self.step = 0

        async def generate(self, system_prompt, messages, tools):
            self.step += 1
            if self.step == 1:
                return LlmTurn(content=None, tool_calls=[ToolCall(id="1", name="search_documents", arguments={"query": "quarterly financial earnings report"})])
            return LlmTurn(content="No relevant procedure was found for that query.", tool_calls=[])

    mcp_client = AlarmMcpClient(mcp_server_url)
    orchestrator = AlarmInvestigationOrchestrator(mcp_client, rag_tool, OnlySearchDocsLlm())

    result = await orchestrator.handle_message("What does the procedure say about quarterly earnings?")

    assert result.events[0].outcome == "low_confidence"
    assert result.citations == []


@pytest.mark.asyncio
async def test_provider_rejected_tool_call_self_corrects_instead_of_aborting(mcp_server_url, rag_tool):
    """Reproduces the real failure observed against Groq: the *provider's own*
    function-calling layer rejects a malformed tool call (e.g. a required
    field missing) before we ever see a ToolCall object, raising
    LlmToolCallValidationError instead of returning a normal LlmTurn.

    Before this fix, agent.py treated this exactly like a fatal
    LlmProviderError (auth failure, network error, etc.) and aborted the
    whole conversation turn immediately -- even though, unlike a real
    provider outage, the model could very plausibly get it right on a
    second attempt if told what was wrong. This test asserts the
    orchestrator now retries by feeding a corrective notice back to the
    model instead of giving up on the first rejection.
    """

    class RejectThenSucceedLlm(LlmProvider):
        def __init__(self):
            self.step = 0

        async def generate(self, system_prompt, messages, tools):
            self.step += 1
            if self.step == 1:
                raise LlmToolCallValidationError(
                    "provider rejected malformed tool call",
                    tool_name="correlate_alarms",
                    attempted_arguments={"asset_ids": ["AST-bdd640fb06"]},
                )
            # On retry, the model "corrects itself" and goes straight to a
            # final answer rather than re-attempting the tool.
            return LlmTurn(content="Correlation could not be run, but here is what I found otherwise.", tool_calls=[])

    mcp_client = AlarmMcpClient(mcp_server_url)
    orchestrator = AlarmInvestigationOrchestrator(mcp_client, rag_tool, RejectThenSucceedLlm())

    result = await orchestrator.handle_message("Correlate alarms for this asset")

    # The turn must complete (not abort as a fatal provider error), the
    # rejection must be visible in the trace/degraded reasons for the GUI,
    # and the model must have been given a second attempt.
    assert result.degraded
    assert any("provider_rejected_tool_call" in r for r in result.degraded_reasons)
    assert any(e.outcome == "invalid_arguments" and e.tool_name == "correlate_alarms" for e in result.events)
    assert "correlation could not be run" in result.answer.lower()
