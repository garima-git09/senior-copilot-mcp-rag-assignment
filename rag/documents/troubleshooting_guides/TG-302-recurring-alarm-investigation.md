---
doc_id: TG-302
title: Recurring Alarm Investigation and Rationalization Guide
doc_type: troubleshooting_guide
asset_types: [pump, compressor, motor, heat_exchanger, fan, valve, tank, turbine]
alarm_names: []
tags: [recurring alarms, rationalization, nuisance alarms, investigation workflow]
version: "1.0"
effective_date: 2026-01-05
---

# Recurring Alarm Investigation and Rationalization Guide

## Purpose

A general workflow for investigating why an alarm keeps recurring on an asset, and
deciding whether it should be rationalized (re-tuned or suppressed) rather than
repeatedly acknowledged.

## Investigation Workflow

1. Resolve the asset name to an asset_id and pull its metadata (type, criticality,
   related assets).
2. Retrieve alarm history for the asset over a representative window (90 days is the
   standard investigation window).
3. Summarize alarms grouped by alarm_name to find the recurrence count and average
   acknowledgement delay for the specific alarm in question.
4. Run alarm correlation across the asset and its related assets to check whether the
   alarm co-occurs with alarms on neighboring equipment (a possible shared root cause).
5. Check rationalization candidates: an alarm recurring 5 or more times in the window,
   or with a consistently long acknowledgement delay, is a rationalization candidate.
6. Retrieve the applicable operating procedure or maintenance manual for the asset type
   and alarm name, and compare its guidance with the priority score and recommended
   actions returned by the alarm system.

## Deciding Between "Fix the Equipment" and "Rationalize the Alarm"

- If the underlying condition (vibration, pressure, temperature) is trending toward a
  genuine equipment fault, prioritize maintenance action over rationalization.
- If the alarm fires repeatedly at a value close to its setpoint without a clear
  equipment fault (nuisance behavior), it is a stronger candidate for setpoint
  rationalization or alarm-band widening, subject to safety review.

## Documentation

Every rationalization decision should reference the specific occurrence count, average
acknowledgement delay, and the maintenance/operating guidance considered, so the
decision is auditable later.
