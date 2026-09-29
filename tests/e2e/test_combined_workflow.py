"""End-to-end test: a GUI-equivalent request through the copilot backend's
HTTP API, exercising MCP tool discovery/invocation, the Alarm Management
API (in-process), RAG retrieval with citations, and a grounded final
response -- the mandatory end-to-end acceptance scenario from the
assignment brief (Boiler Feed Pump 101 investigation).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import apps.backend.main as backend_main
from apps.backend.llm.base import LlmProvider, LlmTurn, ToolCall
from apps.backend.mcp_client.client import AlarmMcpClient
from apps.backend.rag_client.tool import RagTool
from rag.ingestion.index_builder import build_index
from rag.retrieval.retriever import DocumentRetriever
from rag.tests.fake_embedder import fake_embed_fn

pytestmark = pytest.mark.e2e

DOCS_PATH = Path(__file__).resolve().parents[2] / "rag" / "documents"


class ScriptedInvestigationLlm(LlmProvider):
    """Scripts exactly the mandatory acceptance scenario's tool sequence:
    asset resolution -> alarm retrieval -> correlation -> document retrieval
    -> grounded answer with citations.
    """

    def __init__(self) -> None:
        self.step = 0

    async def generate(self, system_prompt, messages, tools):
        self.step += 1
        if self.step == 1:
            return LlmTurn(content=None, tool_calls=[ToolCall(id="1", name="search_assets", arguments={"query": "Boiler Feed Pump 101"})])
        if self.step == 2:
            last = json.loads(messages[-1].content)
            asset_id = last["results"][0]["asset_id"]
            return LlmTurn(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="2",
                        name="get_alarm_summary",
                        arguments={
                            "time_range": {"start_time": "2026-05-01T00:00:00Z", "end_time": "2026-07-01T00:00:00Z"},
                            "asset_ids": [asset_id],
                            "severity": ["high", "critical"],
                        },
                    )
                ],
            )
        if self.step == 3:
            return LlmTurn(
                content=None,
                tool_calls=[ToolCall(id="3", name="search_documents", arguments={"query": "boiler feed pump high vibration operating procedure"})],
            )
        return LlmTurn(
            content=(
                "Boiler Feed Pump 101 shows recurring high-severity vibration alarms over the last 90 days "
                "(see alarm summary). The operating procedure (OP-101) recommends checking suction pressure "
                "for cavitation and inspecting bearings per MM-201 if vibration persists. "
                "Sources: search_assets, get_alarm_summary, search_documents (OP-101, MM-201)."
            ),
            tool_calls=[],
        )


@pytest.fixture()
def rag_index(tmp_path_factory) -> str:
    index_dir = tmp_path_factory.mktemp("e2e_rag_index")
    build_index(str(DOCS_PATH), str(index_dir), embed_fn=fake_embed_fn)
    return str(index_dir)


def test_end_to_end_boiler_feed_pump_investigation(monkeypatch, mcp_server_url, rag_index):
    """Drives the backend's public HTTP API exactly as the Streamlit GUI would."""
    # The app's lifespan calls _ensure_index() -> DocumentRetriever(...) before
    # the test doubles below get a chance to override app.state.retriever, so
    # it would otherwise try to download the real sentence-transformers model
    # (network access, not available/needed in this deterministic test). Make
    # it use the same fast, network-free fake embedder the fixtures use.
    monkeypatch.setattr("rag.retrieval.retriever.load_embedder", lambda model_name: fake_embed_fn)
    monkeypatch.setattr("rag.ingestion.index_builder.load_embedder", lambda model_name: fake_embed_fn)
    with TestClient(backend_main.app) as client:
        # Overrides must happen AFTER entering the TestClient context: entering
        # it runs the app's lifespan, which (re)builds these from settings and
        # would otherwise clobber the test doubles set beforehand.
        backend_main.app.state.mcp_client = AlarmMcpClient(mcp_server_url)
        retriever = DocumentRetriever(rag_index, embed_fn=fake_embed_fn)
        backend_main.app.state.retriever = retriever
        backend_main.app.state.rag_tool = RagTool(retriever, top_k=5, min_score=0.35)
        backend_main.app.state.llm_provider = ScriptedInvestigationLlm()
        backend_main.app.state.llm_error = None
        backend_main.app.state.orchestrator = None

        health = client.get("/health")
        assert health.status_code == 200

        tools_resp = client.get("/tools")
        assert tools_resp.status_code == 200
        assert len(tools_resp.json()["tools"]) == 14

        chat_resp = client.post(
            "/chat",
            json={
                "message": (
                    "Investigate recurring high-severity alarms for Boiler Feed Pump 101 over the last 90 days, "
                    "identify likely contributing factors, retrieve the relevant operating procedure, and "
                    "recommend actions with source evidence."
                ),
                "conversation_id": "e2e-test",
            },
        )
        assert chat_resp.status_code == 200
        payload = chat_resp.json()

        # 1. Asset resolution through an MCP tool
        assert payload["events"][0]["tool_name"] == "search_assets"
        assert payload["events"][0]["tool_kind"] == "mcp"

        # 2. Alarm Management API chaining through MCP
        assert payload["events"][1]["tool_name"] == "get_alarm_summary"

        # 3. Document retrieval through RAG
        assert payload["events"][2]["tool_kind"] == "rag"

        # 4. Combined reasoning + 5. Citations
        assert payload["citations"], "expected document citations in the combined answer"
        assert not payload["degraded"]

        # 6. GUI output (the response the GUI renders)
        assert "OP-101" in payload["answer"] or "MM-201" in payload["answer"]

        # 7. MCP execution trace
        assert all("duration_ms" in e for e in payload["events"])
        assert all(e["outcome"] == "success" for e in payload["events"])
