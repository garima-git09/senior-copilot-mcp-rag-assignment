"""Factory that constructs the configured LLM provider.

This is the single switch point for "replaceable LLM provider": change
LLM_PROVIDER (+ LLM_API_KEY, LLM_MODEL) in the environment and the
orchestrator picks up the new provider with no code change.
"""

from __future__ import annotations

from apps.backend.config.settings import Settings
from apps.backend.llm.base import LlmProvider, LlmProviderError


def get_llm_provider(settings: Settings) -> LlmProvider:
    provider = settings.llm_provider.lower().strip()
    if provider == "anthropic":
        from apps.backend.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=settings.llm_api_key, model=settings.llm_model)
    if provider == "openai":
        from apps.backend.llm.openai_provider import OpenAiProvider

        return OpenAiProvider(api_key=settings.llm_api_key, model=settings.llm_model)
    if provider == "groq":
        # Groq implements the OpenAI chat-completions API shape, so it reuses
        # OpenAiProvider with a different base_url -- no new SDK/class needed.
        from apps.backend.llm.openai_provider import OpenAiProvider

        return OpenAiProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url="https://api.groq.com/openai/v1",
        )
    raise LlmProviderError(f"Unsupported LLM_PROVIDER '{settings.llm_provider}'. Supported: anthropic, openai, groq")
