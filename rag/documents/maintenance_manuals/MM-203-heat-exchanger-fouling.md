---
doc_id: MM-203
title: Heat Exchanger Fouling and Differential Pressure Maintenance Manual
doc_type: maintenance_manual
asset_types: [heat_exchanger]
alarm_names: [Outlet Temperature High, Fouling Suspected, Differential Pressure High]
tags: [heat exchanger, fouling, differential pressure]
version: "1.4"
effective_date: 2025-12-05
---

# Heat Exchanger Fouling and Differential Pressure Maintenance Manual

## Scope

Diagnosis and cleaning guidance for shell-and-tube heat exchangers exhibiting fouling
symptoms (HX-4xx series).

## Recognizing Fouling

- Gradually rising differential pressure across the exchanger over days to weeks.
- Outlet temperature drifting away from design target despite stable inlet conditions.
- These two symptoms occurring together over a multi-day trend (not a single alarm
  spike) are the clearest fouling signature -- use the alarm trends tool to confirm a
  gradual trend rather than a step change.

## Corrective Action

1. Schedule a cleaning window once differential pressure exceeds 1.4x the clean-tube
   baseline.
2. Chemical or mechanical (hydroblast) cleaning per the exchanger's specific cleaning
   procedure card.
3. Re-baseline differential pressure and outlet temperature after cleaning.

## Distinguishing Fouling from Instrumentation Fault

A sudden step-change in differential pressure (rather than a gradual trend) is more
likely a transmitter fault or a partially closed block valve than fouling. Verify field
instrumentation before scheduling a cleaning outage.
