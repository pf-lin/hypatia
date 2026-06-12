# Congestion Mapping Notes

## Official traffic-load definition

`offered_isl_resource_load_percent = 100 * sum(flow_rate_mbps * time-averaged baseline ISL hops) / (directed_ISL_count * ISL_capacity_mbps)`

The official reference replays the existing one-second Baseline/free-one-only
forwarding-state snapshots over the 0-8 s traffic-generation window. The
supplemental fixed reference uses the first snapshot at `t=0`.

The official denominator is all 2,880 directed ISLs at 10 Mbps each. This is a
global constellation resource-demand fraction. It is intentionally independent
of Baseline PDR and Queue-aware PDR, but it can strongly dilute a geographically
localized hotspot.

## Supplemental diagnostics

- `reference_active_capacity_load_percent` normalizes the same hop demand by
  the capacity of directed ISLs touched by the Baseline reference paths.
- `peak_reference_link_offered_load_percent` is the largest per-snapshot
  reference-path offered demand on one directed ISL.
- Neither supplemental metric replaces the official global traffic label.

## Observed pressure

Observed pressure is reported per algorithm. The mapping table uses the
Queue-aware row only as adaptive validation because Queue-aware is the only
algorithm available for all 30 settings. It does not define
`traffic_load_label`.

- Non-congested: target-corridor active p95 < 0.60, no link reaches 80%, and
  no ISL queue sample reaches capacity.
- Localized congestion: target-corridor active p95 >= 0.60, at least one link
  reaches 80%, or a nonzero number of ISL queue samples reaches capacity.
- Sustained congestion: at least 1,000 ISL queue samples reach capacity, or
  the first-to-last saturation observation span is at least 4 s while at least
  one link reaches 90%.
- Overloaded: at least 25,000 ISL queue samples reach capacity, or the
  saturation observation span is at least 6 s while at least three links reach
  90%.

The saturation duration is a first-to-last observation-span proxy from the
existing congestion summary, not proof of uninterrupted queue saturation.
Utilization comes from measured throughput. GSL utilization is not treated as
throughput; GSL safety uses queue saturation and associated-loss diagnostics.
Associated loss is time/path correlation, not physical-drop proof.

## PDR role

PDR is joined only after traffic labels and observed-pressure conditions have
been assigned. It is an algorithm outcome and never participates in either
definition.
