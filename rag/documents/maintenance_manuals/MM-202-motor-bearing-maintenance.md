---
doc_id: MM-202
title: Motor Trip and Winding Temperature Maintenance Manual
doc_type: maintenance_manual
asset_types: [motor]
alarm_names: [Motor Trip, Winding Temperature High, Overcurrent, Bearing Vibration High]
tags: [motor, winding, overcurrent, bearing]
version: "2.0"
effective_date: 2025-09-10
---

# Motor Trip and Winding Temperature Maintenance Manual

## Scope

Root-cause diagnosis for motor protection trips and winding/bearing alarms on
process motors (M-5xx series).

## Diagnostic Priority After a Motor Trip

1. Read the protection relay's trip flag before resetting -- resetting first destroys
   the diagnostic evidence.
2. Ground fault flag: inspect insulation resistance before re-energizing.
3. Overcurrent flag: check driven equipment (pump/fan) for a mechanical jam or
   increased load before re-energizing the motor.
4. Thermal overload flag: confirm winding temperature has returned below 40 degC
   before restart.

## Winding Temperature High

- Verify cooling fan / ventilation path is not obstructed.
- Check for repeated start/stop cycling in the recent alarm history -- frequent
  restarts accelerate winding heating.

## Bearing Vibration High on Motors

Follow the same diagnostic table as MM-201 (misalignment, looseness, bearing wear),
substituting motor bearing housings for pump bearing housings.

## Recurrence Guidance

A motor with recurring Overcurrent alarms alongside high vibration on a coupled asset
(e.g. a compressor or pump on the same unit) should be investigated as a single
combined mechanical issue rather than two independent alarms -- correlate using the
alarm correlation tool before dispatching separate work orders.
