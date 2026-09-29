"""Configuration for the alarm-management MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class McpServerSettings:
    host: str = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    port: int = int(os.getenv("MCP_SERVER_PORT", "9000"))
    transport: str = os.getenv("MCP_SERVER_TRANSPORT", "streamable-http")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = McpServerSettings()
