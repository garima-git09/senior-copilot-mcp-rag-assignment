---
doc_id: MM-201
title: Centrifugal Pump Vibration and Bearing Maintenance Manual
doc_type: maintenance_manual
asset_types: [pump]
alarm_names: [High Vibration, Bearing Temperature High, Seal Leak Detected]
tags: [pump, bearing, vibration, maintenance, coupling alignment]
version: "3.1"
effective_date: 2025-11-20
---

# Centrifugal Pump Vibration and Bearing Maintenance Manual

## Scope

Covers root-cause diagnosis and corrective maintenance for recurring vibration and
bearing-temperature alarms on centrifugal pumps, including Boiler Feed Pump 101/102
and Boiler Feed Pump 201.

## Common Root Causes of High Vibration

| Symptom pattern | Likely cause | Corrective action |
|---|---|---|
| Vibration rises with low suction pressure | Cavitation | Increase suction head, check strainer for fouling |
| Vibration steady, bearing temp also elevated | Bearing wear | Replace bearing, check lubrication schedule |
| Vibration at 1x running speed | Coupling misalignment | Re-align coupling within 0.05 mm TIR |
| Vibration at 2x running speed | Looseness or worn foundation bolts | Torque-check baseplate bolts |
| Vibration increasing gradually over weeks | Progressive bearing wear | Schedule bearing replacement at next outage |

## Corrective Maintenance Procedure

1. Isolate and lock out the pump per SI-401 before any physical inspection.
2. Perform a vibration spectrum analysis; compare against the baseline signature on
   file for the asset.
3. Inspect bearing housings for lubricant contamination or discoloration.
4. If replacing a bearing, verify coupling alignment afterward before returning the
   pump to service.

## Recurrence Guidance

Pumps that generate three or more High Vibration alarms within a 90-day window should
be flagged as rationalization candidates and scheduled for a full bearing and
alignment inspection at the next planned outage, rather than continuing reactive
acknowledgement of each alarm.

## Related Documents

- OP-101 Boiler Feed Pump Normal Operation and Alarm Response
- SI-401 Lockout/Tagout Procedure
