---
doc_id: SI-402
title: High-Pressure System Safety Instruction
doc_type: safety_instruction
asset_types: [valve, tank, compressor, turbine]
alarm_names: [Fail to Open, High Level, Overspeed, Discharge Pressure High]
tags: [high pressure, safety, emergency valve, overspeed]
version: "2.1"
effective_date: 2025-10-18
---

# High-Pressure System Safety Instruction

## Purpose

Defines safe-response requirements for alarms on high-pressure or overspeed-critical
equipment where a delayed or incorrect response has personnel-safety consequences.

## Immediate Actions

1. A Fail to Open alarm on an emergency or relief valve during a demand event is a
   Priority 1 safety event -- do not delay response to investigate root cause first;
   follow the site emergency isolation procedure immediately.
2. An Overspeed alarm on a turbine requires immediate load rejection per the turbine
   control system's automatic trip logic; manual intervention should only supplement,
   never override, the automatic trip.
3. High Level alarms on pressurized storage tanks should be treated as an overfill
   protection event: stop inbound flow before investigating the root cause of the level
   discrepancy.

## Post-Event Requirements

Any Priority 1 safety event must be logged with full alarm and operator-action
timestamps and reviewed at the next shift handover, regardless of whether equipment
damage occurred.
