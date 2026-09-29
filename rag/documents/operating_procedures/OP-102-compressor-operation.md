---
doc_id: OP-102
title: Reciprocating and Centrifugal Compressor Operating Procedure
doc_type: operating_procedure
asset_types: [compressor]
alarm_names: [Discharge Pressure High, Discharge Temperature High, Surge Detected, Lube Oil Pressure Low, Vibration High]
tags: [compressor, surge, discharge pressure, lube oil]
version: "1.8"
effective_date: 2026-02-01
---

# Reciprocating and Centrifugal Compressor Operating Procedure

## Purpose

Defines normal operation, monitoring limits, and first-response actions for
process compressors (C-3xx series).

## Normal Operating Envelope

- Discharge pressure: within 5% of design set point per compression stage
- Discharge temperature: below 150 degC
- Lube oil pressure: above 1.5 barg differential across bearings
- Surge margin: minimum 10% above the surge line at all times

## Response to Surge Detected Alarm

Surge Detected is always treated as critical severity.

1. Immediately verify the anti-surge valve has opened automatically; if not, open it
   manually from the control room.
2. Reduce compressor load in line with the anti-surge control curve.
3. Inspect suction and discharge piping for unexpected restrictions (closed valves,
   fouled strainers) once load has stabilized.
4. Do not attempt to increase load again until three consecutive surge-free minutes
   have been confirmed.

## Response to Discharge Pressure High / Discharge Temperature High

1. Check for downstream blockage before adjusting compressor speed.
2. A simultaneous Discharge Temperature High and Discharge Pressure High alarm on the
   same asset within a short window is a strong indicator of a fouled aftercooler;
   schedule inspection per MM-203.

## Response to Lube Oil Pressure Low

This is a device-safety alarm. Do not continue running if lube oil pressure remains
below the alarm setpoint for more than 5 minutes -- initiate a controlled shutdown to
prevent bearing damage.

## Recurring Alarms

If the same compressor alarm has recurred more than 5 times in a 60-day window, raise a
rationalization candidate per TG-302 rather than repeatedly acknowledging the alarm.
