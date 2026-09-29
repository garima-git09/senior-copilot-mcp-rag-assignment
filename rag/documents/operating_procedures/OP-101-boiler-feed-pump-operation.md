---
doc_id: OP-101
title: Boiler Feed Pump Normal Operation and Alarm Response
doc_type: operating_procedure
asset_types: [pump]
alarm_names: [High Vibration, Low Suction Pressure, High Discharge Pressure, Bearing Temperature High, Seal Leak Detected]
tags: [boiler feed pump, pump, vibration, suction pressure]
version: "2.3"
effective_date: 2026-01-15
---

# Boiler Feed Pump Normal Operation and Alarm Response

## Purpose

This procedure defines normal startup, running checks, and first-response actions for
boiler feed pumps (BFP-1xx series) when a process alarm is raised.

## Normal Operating Envelope

- Discharge pressure: 90-130 barg
- Suction pressure: minimum 4 barg (cavitation risk below this)
- Bearing temperature: below 85 degC
- Vibration (velocity RMS): below 4.5 mm/s normal, 7.1 mm/s alarm, 11.0 mm/s trip

## Response to High Vibration Alarm

1. Do not immediately trip the pump unless vibration exceeds the trip setpoint.
2. Check suction pressure trend for the preceding 30 minutes -- a drop below 4 barg
   commonly causes cavitation, which reads as high-frequency vibration.
3. Confirm coupling alignment log was not flagged during the last maintenance window.
4. If vibration correlates with a simultaneous Low Suction Pressure alarm on the same
   asset, treat cavitation as the probable cause and open the minimum-flow recirculation
   valve before reducing pump speed.
5. If vibration is sustained and NOT correlated with suction pressure, dispatch
   mechanical maintenance to inspect bearings per MM-201.

## Response to High Discharge Pressure Alarm

1. Verify downstream control valve position; a valve stuck near closed will raise
   discharge pressure and should be checked before assuming a pump fault.
2. Cross-check with any Motor Overcurrent or Overload alarms on the same pump -- these
   often accompany a blocked discharge line.

## Response to Bearing Temperature High Alarm

1. Verify lube oil / grease schedule compliance for the asset.
2. If temperature continues to climb after 15 minutes, reduce load and prepare for a
   controlled shutdown; do not wait for a trip.

## Escalation

Any Seal Leak Detected alarm is safety-critical: refer immediately to SI-401 (Lockout/
Tagout) before any hands-on inspection, and notify the shift supervisor.
