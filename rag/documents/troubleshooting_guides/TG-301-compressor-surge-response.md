---
doc_id: TG-301
title: Compressor Surge Troubleshooting Guide
doc_type: troubleshooting_guide
asset_types: [compressor]
alarm_names: [Surge Detected, Discharge Pressure High, Vibration High]
tags: [compressor, surge, troubleshooting]
version: "1.2"
effective_date: 2026-03-01
---

# Compressor Surge Troubleshooting Guide

## When to Use This Guide

Use this guide when a compressor has raised a Surge Detected alarm, or when Discharge
Pressure High and Vibration High alarms occur together on the same compressor within a
short window (a pre-surge pattern).

## Step-by-Step Diagnosis

1. Pull the last 24 hours of alarm history for the asset and any correlated assets in
   the same unit.
2. Confirm whether the anti-surge valve opened automatically at the time of the event.
3. Check for a recent process upset upstream (feed composition change, upstream
   compressor trip) that could have pushed the machine toward its surge line.
4. If surge recurs more than twice in a week, treat the anti-surge control tuning as
   suspect and involve process control engineering.

## Related Alarms to Check

- Lube Oil Pressure Low on the same asset (may indicate an unrelated but concurrent
  mechanical issue).
- Vibration High on downstream or upstream assets in the same unit (possible
  propagated disturbance).

## Escalation Path

Two or more surge events on the same compressor within 24 hours should be escalated to
the process engineer on call, in addition to the standard operator response in OP-102.
