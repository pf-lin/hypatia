# Hotspot Reference Load Mapping Notes

## Dual load definition

The `core_isl_hotspot_specific` experiment reports two load percentages:

1. `global_offered_isl_load_percent` divides time-averaged Baseline
   reference-path hop demand by all 2,880 directed ISLs at 10 Mbps.
2. `hotspot_reference_load_percent` divides the same numerator by the
   capacity of the directed ISLs touched by that setting's Baseline reference
   paths during the 0-8 s traffic window.

The global metric remains necessary because it describes constellation-wide
resource demand. The hotspot metric is the primary scenario label for this
deliberately localized traffic placement.

## Hotspot labels

- Hotspot-Light: < 50%
- Hotspot-Moderate: 50% to < 70%
- Hotspot-High: 70% to < 85%
- Hotspot-Severe: 85% to < 100%
- Hotspot-Overload: >= 100%

These thresholds are fixed before joining PDR outcomes.

## Target-corridor diagnostic

`target_corridor_offered_load_percent` is recomputed by replaying the Baseline
shortest path at one-second snapshots over 0-8 s and summing only demand on the
fixed target-corridor directed edge set. The target edge counts observed in
these runs are: 50. This avoids treating every edge in a multi-snapshot path
union as if it carried every flow simultaneously.

## Methodological caveat

The active-reference denominator is setting-specific. Adding flows can expand
the union of touched directed ISLs, so hotspot-reference load is not guaranteed
to be monotonic in `load_level` or background-flow count. For example,
`load=1.0,bg=16` is 50.0% while `load=1.0,bg=24` is approximately 47.36%.

To avoid cherry-picking:

- the Baseline reference algorithm, 0-8 s window, one-second snapshots, and
  label thresholds are fixed for all settings;
- the active directed-ISL count and capacity are reported for every setting;
- global load, fixed target-corridor load, and peak-link demand are retained;
- candidate selection uses all GSL-safe settings in each predeclared band;
- PDR is joined only as an outcome and never changes a scenario label.

## Observed pressure and PDR

Queue-aware throughput and queue-pressure metrics validate whether congestion
appears under an adaptive route, but they do not define the hotspot load.
Associated loss remains a time/path correlation rather than physical-drop
proof. PDR is an algorithm outcome only.
