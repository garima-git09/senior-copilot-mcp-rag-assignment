"""Unit tests for a few small backend fixes made after real-world use with a
low-rate-limit free-tier LLM provider (Groq's free tier caps
openai/gpt-oss-20b at 8000 TPM), plus one for a leaked-tool-syntax fix:

1. `apps/backend/orchestrator/agent.py::_shrink_for_llm` -- bounds what gets
   re-sent to the LLM on every iteration, so a large `get_alarms` page
   doesn't make the conversation grow past a small provider's token limit.
2. `apps/backend/mcp_client/client.py::_preview` -- must always return a
   JSON-safe object (never a hand-truncated Python repr string), because the
   GUI passes it straight to `st.json()`, which re-parses string input as
   JSON and throws a "Json Parse Error" on a truncated/single-quoted repr.
3. `apps/backend/orchestrator/agent.py::_sanitize_answer` -- some models
   (observed with Groq's openai/gpt-oss models) occasionally leak fragments
   of their internal tool-call/channel syntax into the final answer text
   (e.g. "【assistant to=functions.search_documents】" or a stray
   "<|constrain|>" token). This strips that before the answer reaches the
   GUI, as a backstop to the system prompt's explicit instruction not to
   produce it in the first place.
"""

from __future__ import annotations

import json

from apps.backend.mcp_client.client import _preview
from apps.backend.orchestrator.agent import _MAX_LIST_ITEMS_FOR_LLM, _sanitize_answer, _shrink_for_llm


def _big_alarm_list(n: int) -> dict:
    return {"data": [{"alarm_id": f"ALM-{i}", "severity": "high", "description": "x" * 50} for i in range(n)], "pagination": {"page": 1, "total_items": n}}


def test_shrink_for_llm_truncates_large_list_fields():
    result = _big_alarm_list(50)
    shrunk_text = _shrink_for_llm(result)
    parsed = json.loads(shrunk_text)
    assert len(parsed["data"]) == _MAX_LIST_ITEMS_FOR_LLM
    assert "data_note" in parsed
    assert "50" in parsed["data_note"]


def test_shrink_for_llm_leaves_small_results_untouched():
    result = {"total_alarms": 3, "by_severity": {"high": 2, "critical": 1}}
    shrunk_text = _shrink_for_llm(result)
    assert json.loads(shrunk_text) == result


def test_shrink_for_llm_hard_truncates_pathologically_large_non_list_payload():
    result = {"summary": "x" * 10000}
    shrunk_text = _shrink_for_llm(result)
    assert len(shrunk_text) < 10000
    assert shrunk_text.endswith("(truncated)")


def test_preview_returns_json_safe_object_not_a_broken_string():
    result = _big_alarm_list(50)
    preview = _preview(result)
    # Must be a real dict (so the GUI's st.json() can render it directly,
    # with no re-parsing of a string involved).
    assert isinstance(preview, dict)
    assert len(preview["data"]) == 5
    assert "data_note" in preview
    # And it must actually be JSON-serializable end to end.
    json.dumps(preview)


def test_preview_small_result_is_returned_as_is():
    result = {"total_alarms": 3}
    assert _preview(result) == result


def test_preview_falls_back_to_truncated_string_only_for_huge_non_list_values():
    result = {"summary": "x" * 5000}
    preview = _preview(result)
    assert isinstance(preview, str)
    assert preview.endswith("...(truncated)")
    # Never the old single-quoted Python-repr style that broke st.json().
    assert "{'summary'" not in preview


def test_sanitize_answer_strips_leaked_bracketed_tool_call_block():
    text = "cavitation risk, which 【assistant to=functions.search_documents】 reads as vibration"
    cleaned = _sanitize_answer(text)
    assert "【" not in cleaned
    assert "】" not in cleaned
    assert "functions." not in cleaned
    assert cleaned == "cavitation risk, which reads as vibration"


def test_sanitize_answer_strips_pipe_delimited_special_tokens_inside_a_block():
    text = "derived from get_alarm_summary (grouped by alarm_name)【assistant to=functions.get_alarm_summary<|constrain|>json_output】."
    cleaned = _sanitize_answer(text)
    assert "<|" not in cleaned
    assert "json_output" not in cleaned
    assert cleaned == "derived from get_alarm_summary (grouped by alarm_name)."


def test_sanitize_answer_leaves_clean_text_untouched():
    text = "The operating procedure (OP-101) recommends checking suction pressure. Sources: search_assets, get_alarms."
    assert _sanitize_answer(text) == text


def test_sanitize_answer_handles_empty_string():
    assert _sanitize_answer("") == ""
