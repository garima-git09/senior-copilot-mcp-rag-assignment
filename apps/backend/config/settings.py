"""Central, environment-driven configuration for the copilot backend.

Every setting is read from the environment (see .env.example at the repo
root) so the LLM provider, MCP server location, and vector store can all be
swapped without touching code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    mcp_server_url: str = os.getenv("MCP_SERVER_URL", "http://localhost:9000/mcp")

    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20250929")

    vector_store_url: str = os.getenv("VECTOR_STORE_URL", "./rag/index/chroma")
    document_path: str = os.getenv("DOCUMENT_PATH", "./rag/documents")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "5"))
    rag_min_score: float = float(os.getenv("RAG_MIN_SCORE", "0.35"))

    host: str = os.getenv("COPILOT_BACKEND_HOST", "0.0.0.0")
    port: int = int(os.getenv("COPILOT_BACKEND_PORT", "8080"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
