"""Deterministic synthetic data generator for the Alarm Management API simulator.

No real plant data exists for this assignment, so we generate a consistent,
reproducible dataset (fixed random seed) that covers assets, asset metadata,
and ~90 days of alarm history across multiple sites and units. The shapes of
every record match the fields referenced by the Postman reference collections
(asset_id, alarm_id, severity, status, start_time, etc.).
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings

SITES = ["NorthPlant", "SouthPlant", "EastRefinery"]
UNITS = ["Unit 1", "Unit 2", "Unit 3", "Unit 4", "Unit 5"]

ASSET_TEMPLATES: list[dict[str, Any]] = [
    {"name": "Boiler Feed Pump 101", "type": "pump", "site": "NorthPlant", "unit": "Unit 1"},
    {"name": "Boiler Feed Pump 102", "type": "pump", "site": "NorthPlant", "unit": "Unit 1"},
    {"name": "Boiler Feed Pump 201", "type": "pump", "site": "SouthPlant", "unit": "Unit 3"},
    {"name": "Compressor C-301", "type": "compressor", "site": "EastRefinery", "unit": "Unit 2"},
    {"name": "Compressor C-302", "type": "compressor", "site": "EastRefinery", "unit": "Unit 2"},
    {"name": "Compressor C-303", "type": "compressor", "site": "SouthPlant", "unit": "Unit 4"},
    {"name": "Motor M-501", "type": "motor", "site": "NorthPlant", "unit": "Unit 5"},
    {"name": "Motor M-502", "type": "motor", "site": "NorthPlant", "unit": "Unit 5"},
    {"name": "Motor M-503", "type": "motor", "site": "EastRefinery", "unit": "Unit 5"},
    {"name": "Heat Exchanger HX-401", "type": "heat_exchanger", "site": "SouthPlant", "unit": "Unit 4"},
    {"name": "Heat Exchanger HX-402", "type": "heat_exchanger", "site": "EastRefinery", "unit": "Unit 3"},
    {"name": "Cooling Tower Fan CT-601", "type": "fan", "site": "NorthPlant", "unit": "Unit 2"},
    {"name": "Reactor Feed Valve V-701", "type": "valve", "site": "EastRefinery", "unit": "Unit 1"},
    {"name": "Storage Tank T-801", "type": "tank", "site": "SouthPlant", "unit": "Unit 2"},
    {"name": "Turbine TG-901", "type": "turbine", "site": "EastRefinery", "unit": "Unit 4"},
]

ALARM_LIBRARY: dict[str, list[dict[str, Any]]] = {
    "pump": [
        {"alarm_name": "High Vibration", "alarm_type": "process", "severity_pool": ["high", "critical"]},
        {"alarm_name": "High Discharge Pressure", "alarm_type": "process", "severity_pool": ["medium", "high"]},
        {"alarm_name": "Low Suction Pressure", "alarm_type": "process", "severity_pool": ["medium", "high"]},
        {"alarm_name": "Bearing Temperature High", "alarm_type": "device", "severity_pool": ["high", "critical"]},
        {"alarm_name": "Seal Leak Detected", "alarm_type": "safety", "severity_pool": ["high", "critical"]},
    ],
    "compressor": [
        {"alarm_name": "Discharge Pressure High", "alarm_type": "process", "severity_pool": ["high", "critical"]},
        {"alarm_name": "Discharge Temperature High", "alarm_type": "process", "severity_pool": ["medium", "high"]},
        {"alarm_name": "Surge Detected", "alarm_type": "safety", "severity_pool": ["critical"]},
        {"alarm_name": "Lube Oil Pressure Low", "alarm_type": "device", "severity_pool": ["high", "critical"]},
        {"alarm_name": "Vibration High", "alarm_type": "process", "severity_pool": ["high", "critical"]},
    ],
    "motor": [
        {"alarm_name": "Motor Trip", "alarm_type": "safety", "severity_pool": ["critical"]},
        {"alarm_name": "Winding Temperature High", "alarm_type": "device", "severity_pool": ["medium", "high"]},
        {"alarm_name": "Overcurrent", "alarm_type": "process", "severity_pool": ["high", "critical"]},
        {"alarm_name": "Bearing Vibration High", "alarm_type": "device", "severity_pool": ["medium", "high"]},
    ],
    "heat_exchanger": [
        {"alarm_name": "Outlet Temperature High", "alarm_type": "process", "severity_pool": ["medium", "high"]},
        {"alarm_name": "Fouling Suspected", "alarm_type": "process", "severity_pool": ["low", "medium"]},
        {"alarm_name": "Differential Pressure High", "alarm_type": "process", "severity_pool": ["medium", "high"]},
    ],
    "fan": [
        {"alarm_name": "Vibration High", "alarm_type": "device", "severity_pool": ["medium", "high"]},
        {"alarm_name": "Motor Overload", "alarm_type": "process", "severity_pool": ["medium", "high"]},
    ],
    "valve": [
        {"alarm_name": "Valve Position Deviation", "alarm_type": "device", "severity_pool": ["medium", "high"]},
        {"alarm_name": "Fail to Open", "alarm_type": "safety", "severity_pool": ["high", "critical"]},
    ],
    "tank": [
        {"alarm_name": "High Level", "alarm_type": "process", "severity_pool": ["medium", "high"]},
        {"alarm_name": "Low Level", "alarm_type": "process", "severity_pool": ["low", "medium"]},
    ],
    "turbine": [
        {"alarm_name": "Overspeed", "alarm_type": "safety", "severity_pool": ["critical"]},
        {"alarm_name": "Vibration High", "alarm_type": "process", "severity_pool": ["high", "critical"]},
        {"alarm_name": "Exhaust Temperature High", "alarm_type": "process", "severity_pool": ["medium", "high"]},
    ],
}

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _short_id(prefix: str, rng: random.Random) -> str:
    return f"{prefix}-{uuid.UUID(int=rng.getrandbits(128)).hex[:10]}"


class SeedDatabase:
    """In-memory, deterministically generated dataset for the simulator."""

    def __init__(
        self,
        seed: int = settings.seed,
        history_start: str = settings.history_start,
        history_end: str = settings.history_end,
    ) -> None:
        self.rng = random.Random(seed)
        self.history_start = datetime.fromisoformat(history_start.replace("Z", "+00:00"))
        self.history_end = datetime.fromisoformat(history_end.replace("Z", "+00:00"))
        self.assets: dict[str, dict[str, Any]] = {}
        self.alarms: dict[str, dict[str, Any]] = {}
        self._generate_assets()
        self._generate_alarm_history()

    # ------------------------------------------------------------------ #
    # Generation
    # ------------------------------------------------------------------ #
    def _generate_assets(self) -> None:
        for template in ASSET_TEMPLATES:
            asset_id = _short_id("AST", self.rng)
            related_pool = [a["name"] for a in ASSET_TEMPLATES if a["unit"] == template["unit"] and a["name"] != template["name"]]
            self.assets[asset_id] = {
                "asset_id": asset_id,
                "asset_name": template["name"],
                "asset_type": template["type"],
                "site": template["site"],
                "unit": template["unit"],
                "criticality": self.rng.choice(["low", "medium", "high"]),
                "manufacturer": self.rng.choice(["Flowserve", "Siemens", "GE", "Sulzer", "ABB"]),
                "installed_on": (_now() - timedelta(days=self.rng.randint(400, 4000))).date().isoformat(),
                "related_assets": related_pool[:3],
                "tags": [template["type"], template["unit"], template["site"]],
            }

    def _generate_alarm_history(self) -> None:
        start = self.history_start
        end = self.history_end
        for asset_id, asset in self.assets.items():
            catalog = ALARM_LIBRARY.get(asset["asset_type"], [])
            if not catalog:
                continue
            # Recurring alarm pattern: pick 1-2 "favorite" alarm defs per asset
            # that fire repeatedly, plus occasional one-offs -- this is what
            # makes correlation / rationalization / recurring_rate meaningful.
            recurring_defs = self.rng.sample(catalog, k=min(2, len(catalog)))
            num_events = self.rng.randint(15, 45)
            for _ in range(num_events):
                definition = self.rng.choice(recurring_defs) if self.rng.random() < 0.7 else self.rng.choice(catalog)
                alarm_id = _short_id("ALM", self.rng)
                offset_seconds = self.rng.randint(0, int((end - start).total_seconds()))
                start_time = start + timedelta(seconds=offset_seconds)
                severity = self.rng.choice(definition["severity_pool"])
                duration_minutes = self.rng.randint(2, 240)
                is_active = self.rng.random() < 0.08
                cleared_time = None if is_active else start_time + timedelta(minutes=duration_minutes)
                ack_delay_minutes = round(self.rng.uniform(0.5, 25.0), 1)
                acknowledged_time = start_time + timedelta(minutes=ack_delay_minutes)
                self.alarms[alarm_id] = {
                    "alarm_id": alarm_id,
                    "asset_id": asset_id,
                    "asset_name": asset["asset_name"],
                    "site": asset["site"],
                    "unit": asset["unit"],
                    "alarm_name": definition["alarm_name"],
                    "alarm_type": definition["alarm_type"],
                    "severity": severity,
                    "status": "active" if is_active else "cleared",
                    "start_time": start_time.isoformat().replace("+00:00", "Z"),
                    "cleared_time": cleared_time.isoformat().replace("+00:00", "Z") if cleared_time else None,
                    "acknowledged_time": acknowledged_time.isoformat().replace("+00:00", "Z"),
                    "ack_delay_minutes": ack_delay_minutes,
                    "value": round(self.rng.uniform(50, 150), 2),
                    "threshold": round(self.rng.uniform(40, 140), 2),
                }

    # ------------------------------------------------------------------ #
    # Convenience accessors used by the routers
    # ------------------------------------------------------------------ #
    def alarms_sorted(self) -> list[dict[str, Any]]:
        return sorted(self.alarms.values(), key=lambda a: a["start_time"])


DB = SeedDatabase()
