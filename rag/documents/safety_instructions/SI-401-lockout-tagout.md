---
doc_id: SI-401
title: Lockout/Tagout (LOTO) Procedure for Rotating Equipment
doc_type: safety_instruction
asset_types: [pump, compressor, motor, fan, turbine]
alarm_names: [Seal Leak Detected, Motor Trip, Bearing Vibration High]
tags: [lockout tagout, LOTO, safety, isolation]
version: "4.0"
effective_date: 2025-06-01
---

# Lockout/Tagout (LOTO) Procedure for Rotating Equipment

## Purpose

Ensures rotating equipment (pumps, compressors, motors, fans, turbines) is safely
isolated from all energy sources before any physical inspection or maintenance,
including inspections triggered by a safety-type alarm such as Seal Leak Detected.

## Procedure

1. Notify the control room and obtain a permit-to-work before beginning isolation.
2. Isolate electrical supply at the local disconnect and apply a personal lock and tag.
3. Isolate and depressurize process connections; bleed residual pressure to a safe
   location.
4. Verify zero energy state (electrical, mechanical, and stored pressure) before
   removing any guard or seal housing.
5. Only after verified isolation may a technician approach a leaking seal, a tripped
   motor's terminal box, or a bearing housing flagged for vibration inspection.

## Safety-Critical Alarm Handling

Any alarm classified as `alarm_type: safety` (Seal Leak Detected, Motor Trip, Fail to
Open, Surge Detected, Overspeed) requires this LOTO procedure to be referenced before
any hands-on response, even if the immediate operator action is only to acknowledge and
observe from the control room initially.
