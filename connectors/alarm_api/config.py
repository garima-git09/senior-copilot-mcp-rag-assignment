"""Configuration for the Alarm Management API connector."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AlarmApiConfig:
    base_url: str = os.getenv("ALARM_API_BASE_URL", "http://localhost:8000")
    token: str = os.getenv("ALARM_API_TOKEN", "demo-token")
    timeout_seconds: float = float(os.getenv("ALARM_API_TIMEOUT_SECONDS", "10"))
    max_retries: int = int(os.getenv("ALARM_API_MAX_RETRIES", "3"))
    retry_backoff_seconds: float = float(os.getenv("ALARM_API_RETRY_BACKOFF_SECONDS", "0.5"))

    def redacted(self) -> dict:
        """Safe-to-log view of the config -- never includes the token."""
        return {
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "token": "***redacted***",
        }
