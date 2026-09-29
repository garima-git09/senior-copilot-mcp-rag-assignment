"""Unit tests for the replaceable-LLM-provider factory."""

from __future__ import annotations

import pytest

from apps.backend.config.settings import Settings
from apps.backend.llm.anthropic_provider import AnthropicProvider
from apps.backend.llm.base import LlmProviderError
from apps.backend.llm.factory import get_llm_provider
from apps.backend.llm.openai_provider import OpenAiProvider


def _settings(**overrides) -> Settings:
    base = {"llm_provider": "anthropic", "llm_api_key": "test-key", "llm_model": "claude-sonnet-4-5-20250929"}
    base.update(overrides)
    return Settings(**base)


def test_anthropic_provider_is_selected():
    provider = get_llm_provider(_settings(llm_provider="anthropic"))
    assert isinstance(provider, AnthropicProvider)


def test_openai_provider_is_selected():
    provider = get_llm_provider(_settings(llm_provider="openai"))
    assert isinstance(provider, OpenAiProvider)


def test_unsupported_provider_raises():
    with pytest.raises(LlmProviderError):
        get_llm_provider(_settings(llm_provider="not-a-real-provider"))


def test_missing_api_key_raises():
    with pytest.raises(LlmProviderError):
        get_llm_provider(_settings(llm_provider="anthropic", llm_api_key=""))


def test_switching_provider_requires_no_code_change_only_settings():
    """Demonstrates the 'replaceable LLM provider' requirement: the same
    factory function, given different Settings, returns a different
    concrete provider with no orchestrator code touched.
    """
    anthropic = get_llm_provider(_settings(llm_provider="anthropic"))
    openai = get_llm_provider(_settings(llm_provider="openai", llm_model="gpt-4o"))
    assert type(anthropic) is not type(openai)
