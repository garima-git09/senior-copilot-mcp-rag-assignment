"""Configuration for the Alarm Management API simulator.

All values come from environment variables so the service can be configured
without code changes (12-factor style). No secret ever has a hard-coded
production value here -- only a safe local-dev default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    auth_token: str = os.getenv("ALARM_API_TOKEN", "demo-token")
    seed: int = int(os.getenv("ALARM_API_SEED", "42"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    days_of_history: int = int(os.getenv("ALARM_API_HISTORY_DAYS", "90"))
    # Fixed (not "now"-relative) history window so the dataset is fully
    # reproducible and matches the time_range used throughout the reference
    # Postman collections (2026-05-01 .. 2026-07-01).
    history_start: str = os.getenv("ALARM_API_HISTORY_START", "2026-05-01T00:00:00Z")
    history_end: str = os.getenv("ALARM_API_HISTORY_END", "2026-07-01T00:00:00Z")


settings = Settings()
