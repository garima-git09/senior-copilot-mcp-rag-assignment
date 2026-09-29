"""Streamlit GUI for the Alarm Investigation and Procedure Guidance Copilot.

Talks only to the copilot backend's HTTP API (apps/backend/main.py) -- it
never calls the Alarm Management API or the MCP server directly, keeping the
GUI a thin presentation layer over the orchestrator.
"""

from __future__ import annotations

import contextlib
import os
import uuid

import requests
import streamlit as st

BACKEND_URL = os.getenv("COPILOT_BACKEND_URL", "http://localhost:8080")

st.set_page_config(page_title="Alarm Investigation Copilot", page_icon="🛑", layout="wide")

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid.uuid4())
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # list of {"role": ..., "content": ..., "response": ChatResponse|None}


def backend_get(path: str, timeout: float = 10.0):
    return requests.get(f"{BACKEND_URL}{path}", timeout=timeout)


# A full investigation can involve several LLM turns plus several MCP tool
# calls. On a free-tier LLM provider with tight rate limits (e.g. Groq's free
# tier), the SDK's own retry-with-backoff on 429s can add tens of seconds per
# turn, so the default read timeout here is generous rather than tight.
CHAT_TIMEOUT_SECONDS = float(os.getenv("COPILOT_CHAT_TIMEOUT_SECONDS", "600"))


def backend_post(path: str, json: dict, timeout: float = CHAT_TIMEOUT_SECONDS):
    return requests.post(f"{BACKEND_URL}{path}", json=json, timeout=timeout)


OUTCOME_BADGE = {
    "success": "✅ success",
    "low_confidence": "⚠️ low confidence",
    "invalid_arguments": "🚫 invalid arguments",
    "tool_not_found": "❓ tool not found",
    "execution_error": "❌ execution error",
    "unavailable": "🔌 unavailable",
}


def render_sidebar() -> None:
    st.sidebar.title("Alarm Investigation Copilot")
    st.sidebar.caption("MCP + RAG copilot for plant alarm investigation")

    st.sidebar.subheader("Backend status")
    try:
        health = backend_get("/health", timeout=3).json()
        st.sidebar.success(f"Backend: {health.get('status', 'unknown')}")
    except requests.RequestException as exc:
        st.sidebar.error(f"Backend unreachable: {exc}")

    st.sidebar.subheader("MCP tool discovery")
    try:
        tools_resp = backend_get("/tools", timeout=5)
        if tools_resp.status_code == 200:
            payload = tools_resp.json()
            st.sidebar.caption(f"Server: {payload['mcp_server_url']}")
            for tool in payload["tools"]:
                with st.sidebar.expander(tool["name"]):
                    st.write(tool["description"])
        else:
            st.sidebar.warning(f"MCP server unavailable ({tools_resp.status_code})")
    except requests.RequestException as exc:
        st.sidebar.warning(f"Could not list MCP tools: {exc}")

    if st.sidebar.button("Reset conversation"):
        with contextlib.suppress(requests.RequestException):
            backend_post(f"/conversations/{st.session_state.conversation_id}/reset", json={})
        st.session_state.chat_history = []
        st.session_state.conversation_id = str(uuid.uuid4())
        st.rerun()


def render_preview(value) -> None:
    """Render a tool-result preview safely.

    The backend's result_preview is normally a real dict/list (JSON-safe).
    In the rare case a value was too large even after shrinking, the backend
    falls back to a truncated *string* that is not valid JSON -- passing that
    straight to st.json() makes Streamlit try to re-parse it and throw a
    "Json Parse Error" in the UI. Render non-dict/list values as plain text
    instead.
    """
    if isinstance(value, (dict, list)):
        st.json(value, expanded=False)
    else:
        st.code(str(value), language="text")


def render_alarm_summary_panel(events: list[dict]) -> None:
    alarm_events = [e for e in events if e["tool_name"] in ("get_alarms", "get_alarm_summary") and e["outcome"] == "success"]
    if not alarm_events:
        return
    st.subheader(" Alarm summary")
    for e in alarm_events:
        st.caption(f"from `{e['tool_name']}` (trace_id={e.get('trace_id') or 'n/a'})")
        render_preview(e["result_preview"])


def render_recommendations_panel(events: list[dict]) -> None:
    rec_events = [
        e
        for e in events
        if e["tool_name"] in ("get_operator_recommendations", "score_alarm_priority", "get_rationalization_candidates", "correlate_alarms")
        and e["outcome"] == "success"
    ]
    if not rec_events:
        return
    st.subheader(" Likely causes & recommendations")
    for e in rec_events:
        st.caption(f"from `{e['tool_name']}`")
        render_preview(e["result_preview"])


def render_citations_panel(citations: list[dict]) -> None:
    st.subheader(" Document citations")
    if not citations:
        st.info("No document passages were retrieved above the confidence threshold for this answer.")
        return
    for c in citations:
        st.markdown(f"- **{c['doc_id']}** — {c['title']} · _{c['section']}_ (score {c['score']})")


def render_trace_panel(events: list[dict]) -> None:
    st.subheader(" MCP execution trace")
    if not events:
        st.info("No tools were called for this turn.")
        return
    for e in events:
        badge = OUTCOME_BADGE.get(e["outcome"], e["outcome"])
        title = f"Step {e['step']}: {e['tool_name']} [{e['tool_kind']}] — {badge} ({e['duration_ms']} ms)"
        with st.expander(title):
            st.markdown("**Request (arguments)**")
            st.json(e["arguments"])
            st.markdown("**Response**")
            if e["error"]:
                st.error(e["error"])
            else:
                render_preview(e["result_preview"])
            if e.get("trace_id"):
                st.caption(f"trace_id: `{e['trace_id']}`")


def render_degraded_banner(degraded: bool, reasons: list[str]) -> None:
    if degraded:
        st.warning("⚠️ This answer is degraded: one or more tools failed, were unavailable, or returned low-confidence results.")
        for r in reasons:
            st.caption(f"- {r}")


def main() -> None:
    render_sidebar()

    st.title("Alarm Investigation and Procedure Guidance Copilot")
    st.caption(
        "Ask about active alarms, recurring issues, priority, related assets, or applicable procedures. "
        "Every answer is backed by MCP tool calls to the Alarm Management API and RAG citations from the document corpus."
    )

    for turn in st.session_state.chat_history:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])
            if turn["role"] == "assistant" and turn.get("response"):
                resp = turn["response"]
                render_degraded_banner(resp["degraded"], resp["degraded_reasons"])
                tabs = st.tabs(["Alarm summary", "Recommendations", "Citations", "MCP trace"])
                with tabs[0]:
                    render_alarm_summary_panel(resp["events"])
                with tabs[1]:
                    render_recommendations_panel(resp["events"])
                with tabs[2]:
                    render_citations_panel(resp["citations"])
                with tabs[3]:
                    render_trace_panel(resp["events"])

    user_input = st.chat_input("e.g. Investigate recurring high-severity alarms for Boiler Feed Pump 101 over the last 90 days")
    if not user_input:
        return

    st.session_state.chat_history.append({"role": "user", "content": user_input, "response": None})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Investigating (discovering MCP tools, querying the Alarm Management API, retrieving procedures)..."):
            try:
                resp = backend_post("/chat", json={"message": user_input, "conversation_id": st.session_state.conversation_id})
            except requests.RequestException as exc:
                st.error(f"Could not reach the copilot backend: {exc}")
                st.session_state.chat_history.append({"role": "assistant", "content": f"Error: {exc}", "response": None})
                return

            if resp.status_code != 200:
                st.error(f"Backend returned {resp.status_code}: {resp.text}")
                st.session_state.chat_history.append({"role": "assistant", "content": f"Backend error {resp.status_code}", "response": None})
                return

            payload = resp.json()
            st.markdown(payload["answer"])
            render_degraded_banner(payload["degraded"], payload["degraded_reasons"])

            tabs = st.tabs(["Alarm summary", "Recommendations", "Citations", "MCP trace"])
            with tabs[0]:
                render_alarm_summary_panel(payload["events"])
            with tabs[1]:
                render_recommendations_panel(payload["events"])
            with tabs[2]:
                render_citations_panel(payload["citations"])
            with tabs[3]:
                render_trace_panel(payload["events"])

            st.session_state.chat_history.append({"role": "assistant", "content": payload["answer"], "response": payload})


if __name__ == "__main__":
    main()
