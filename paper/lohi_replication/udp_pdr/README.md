# UDP/PDR Dynamic Routing Experiment

This experiment is an isolated UDP/CBR packet-delivery testbed for comparing
dynamic routing algorithms under controlled congestion. It is intentionally
separate from `paper/lohi_replication/traffic_matrix`, which remains the TCP
traffic-matrix experiment.

## Purpose

The goal is to measure packet delivery rate directly:

```text
PDR = received_packets / sent_packets
```

TCP progress and goodput are useful, but they do not expose strict packet
delivery counts. This experiment uses the existing NS-3 `UdpBurstScheduler`,
which records sent and received UDP packets for every burst.

## Simple Backpressure Baseline

`algorithm_backpressure_over_isls` implements a simple original
Backpressure-inspired routing baseline for UDP/PDR comparisons. It is intended
as a queue-driven theoretical comparator, following the basic max-weight idea
from Tassiulas and Ephremides (1992) and Neely, Modiano, and Rohrs (2005):

```text
W_ij^c(t) = max(Q_i^c(t) - Q_j^c(t), 0) * C_ij(t)
```

For each routing snapshot, the algorithm considers only currently active ISL
neighbors as intermediate next-hop candidates. It selects the neighbor with the
largest positive queue differential weight. The final GSL hop to the
destination ground station is still allowed as delivery, and source ground
stations still attach through an in-range satellite; GSLs are not used as relay
candidates.

The current UDP/PDR simulator pipeline does not expose per-destination or
per-commodity internal queues (`Q_i^c`). It exposes directed ISL/interface
queue occupancy through `isl_queue_pkt.csv` and `isl_queue_byte.csv`, which
`calculate_routes.py` aggregates into per-directed-link queue maxima for the
next routing update. Therefore this implementation is not a full
multi-commodity Backpressure scheduler. It is a routing-level Backpressure
approximation using available queue occupancy feedback:

```text
queue_source = node_total_queue_bytes when byte queue data is available
queue_source = node_total_queue_packets when only packet queue data is available
commodity_mode = destination_proxy
backpressure_is_full_multi_commodity = false
```

`--backpressure-queue-source auto` chooses the best available proxy. Explicit
options are also accepted:

```text
auto
per_destination_bytes
per_destination_packets
node_total_bytes
node_total_packets
interface_bytes
interface_packets
```

The `per_destination_*` options are accepted for experiment identity, but the
current pipeline still records `per_destination_queue_available=false` and
falls back to the available proxy rather than pretending to provide true
multi-commodity queues.

### Restricted-route / loop-suppressed Backpressure variant

`algorithm_backpressure_over_isls` also supports a restricted-route /
loop-suppressed queue-proxy Backpressure variant:

```text
--backpressure-loop-guard none
--backpressure-loop-guard immediate_reverse
--backpressure-loop-guard forward_progress_hop
--backpressure-loop-guard forward_progress_distance
```

The default is `none`, preserving the legacy no-guard Backpressure baseline.
The practical smoke/formal candidate is:

```text
--backpressure-loop-guard forward_progress_hop
```

This mode filters candidate ISL neighbors before applying the same
queue-differential weight. For current satellite `i`, candidate neighbor `j`,
and destination `d`, the candidate is legal only when:

```text
dist_hop(j, d) < dist_hop(i, d)
```

The weight remains:

```text
weight(i, j) = max(Q_i - Q_j, 0) * C_ij
```

This is a restricted-route / loop-suppressed queue-proxy Backpressure variant.
It is inspired by desirable-route restrictions discussed in Backpressure
literature, but it is not a full multi-commodity Backpressure scheduler. It is
also not distance-based or hop-based Backpressure, because hop/distance is not
added to the weight; it is only a legal-candidate filter.

`immediate_reverse` is accepted as an explicit mode for diagnostics and
experiment identity, but the current Hypatia forwarding-state pipeline writes
`current_node + destination -> next_hop`. It cannot express a
previous-hop-dependent rule such as `A -> B -> A`, so this mode is not a true
forwarding guard without changing the routing-state interface.

Because Hypatia's dynamic state pipeline must write a forwarding state, the
default fallback is:

```text
--backpressure-fallback shortest_path
```

When no positive queue differential exists, the algorithm uses shortest-path
fallback and records the reason in diagnostics. Strict no-route mode is
available for diagnostics:

```text
--backpressure-fallback no_route
```

The baseline intentionally does not add distance, hop-count, delay,
traffic-light, cluster, or ML corrections to the Backpressure weight. This is
the point of the comparator: Queue-aware routing is the idealized
queue/delay-aware upper-bound style baseline, Backpressure is the original
queue-differential baseline, and LHTR is the proposed practical
traffic-light/hierarchical method.

Backpressure runs write diagnostics under:

```text
runs/<run_name>/algorithm_backpressure_over_isls/backpressure_diagnostics/
```

Expected files:

```text
backpressure_decision_log.csv
backpressure_summary.csv
backpressure_queue_source_summary.csv
backpressure_fallback_summary.csv
backpressure_path_stretch_summary.csv
backpressure_loop_check.csv
```

Run the 10 s H80 smoke test with:

```bash
cd paper/lohi_replication/udp_pdr

python step_1_generate_runs.py \
  --traffic-mode core_isl_hotspot_specific \
  --src-node-id 754 \
  --dst-node-id 785 \
  --load-level 1.6 \
  --simulation-end-time-s 10 \
  --traffic-stop-time-s 8 \
  --background-flow-count 32 \
  --per-flow-rate-reference-background-flow-count 4 \
  --isl-data-rate-megabit-per-s 10 \
  --gsl-data-rate-megabit-per-s 100 \
  --algorithms algorithm_backpressure_over_isls \
  --backpressure-queue-source auto \
  --backpressure-fallback shortest_path \
  --force

python step_2_run.py \
  --traffic-mode core_isl_hotspot_specific \
  --src-node-id 754 \
  --dst-node-id 785 \
  --load-level 1.6 \
  --simulation-end-time-s 10 \
  --traffic-stop-time-s 8 \
  --background-flow-count 32 \
  --per-flow-rate-reference-background-flow-count 4 \
  --isl-data-rate-megabit-per-s 10 \
  --gsl-data-rate-megabit-per-s 100 \
  --algorithms algorithm_backpressure_over_isls \
  --backpressure-queue-source auto \
  --backpressure-fallback shortest_path

python step_3_generate_plots.py \
  --traffic-mode core_isl_hotspot_specific \
  --src-node-id 754 \
  --dst-node-id 785 \
  --load-level 1.6 \
  --simulation-end-time-s 10 \
  --traffic-stop-time-s 8 \
  --background-flow-count 32 \
  --per-flow-rate-reference-background-flow-count 4 \
  --isl-data-rate-megabit-per-s 10 \
  --gsl-data-rate-megabit-per-s 100 \
  --algorithms algorithm_backpressure_over_isls \
  --backpressure-queue-source auto \
  --backpressure-fallback shortest_path \
  --enable-rtt-analysis \
  --enable-route-visualization \
  --rtt-sample-interval-s 5 \
  --route-plot-times 0,5,8
```

To include Backpressure in formal H80 comparisons without changing the
four-algorithm default, pass it explicitly:

```bash
python run_hotspot_5level_formal.py \
  --scenarios H80 \
  --simulation-end-time-s 60 \
  --traffic-stop-time-s 58 \
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr algorithm_backpressure_over_isls \
  --backpressure-queue-source auto \
  --backpressure-fallback shortest_path \
  --force

python run_hotspot_5level_formal.py \
  --scenarios H80 \
  --simulation-end-time-s 200 \
  --traffic-stop-time-s 198 \
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr algorithm_backpressure_over_isls \
  --backpressure-queue-source auto \
  --backpressure-fallback shortest_path \
  --force
```

## Folder Structure

```text
paper/lohi_replication/udp_pdr/
  dynamic_run_list.py
  step_1_generate_runs.py
  step_2_run.py
  step_3_generate_plots.py
  calculate_routes.py
  analyze_packet_delivery.py
  analyze_isl_focused_calibration.py
  plot_packet_delivery_comparison.py
  run_isl_focused_calibration_sweep.py
  templates/template_config_ns3.properties
  runs/
```

Each generated run uses:

```text
runs/<run_name>/<algorithm>/
  config_ns3.properties
  udp_burst_schedule.csv
  run_metadata.json
  dynamic_state/
  lhtr_diagnostics/  # algorithm_lhtr only, when explicitly enabled
  backpressure_diagnostics/  # algorithm_backpressure_over_isls only
  logs_ns3/
  queue_stats/
  prev_output_cache/
```

## Traffic Modes

`focus_only`

Runs only the two focus flows:

```text
src_node_id -> dst_node_id
dst_node_id -> src_node_id
```

The default is `738 <-> 793`. Use `--src-node-id` and `--dst-node-id` to
select another top-100 ground-station pair.

`core_hotspot_specific`

Runs the focus flows plus background UDP flows selected by a baseline
shortest-path overlap heuristic. The selector prefers background pairs whose
paths overlap the focus pair's middle ISL corridor while avoiding the focus
first-hop and last-hop satellites.

`core_isl_hotspot_specific`

Runs the same two focus flows plus background UDP flows selected for a cleaner
ISL-bottleneck scenario. It starts from the `core_hotspot_specific`
middle-ISL overlap idea, but adds target-corridor concentration, endpoint load
controls, and satellite-interface load controls. The selector tries to load the
focus pair's middle ISL corridor without moving the bottleneck to incidental
non-focus ISLs or to a GSL/access interface. By default it uses:

```text
endpoint_load_cap_ratio = 0.8
satellite_interface_load_cap_ratio = 0.8
max_background_flows_per_dst = 1
max_background_flows_per_src = 1
min_middle_isl_overlap_score = 1
min_reachable_overlap_samples = 1
min_overlap_ratio = 0.0
selection_sample_horizon_s = 60.0
hotspot_sample_count = 3
```

Endpoint caps alone are not enough because many endpoints can still share the
same first-hop or last-hop satellite interface. The satellite-interface cap uses
the selected baseline first-hop and last-hop satellites as a proxy for
source-side and destination-side GSL/interface load. It is conservative when a
flow uses several sampled first/last satellites, but it helps keep access-side
queues from becoming the dominant bottleneck.

The selector separates directed and undirected middle-ISL overlap. Directed
overlap is recorded explicitly, while undirected overlap lets a flow count as
using the same physical corridor even if the sampled direction is reversed.
Zero-overlap fallback is intentionally delayed until after per-source/per-dest,
endpoint-cap, and corridor-threshold relaxations, because zero-overlap flows
can dilute high background-flow-count cases into unrelated non-focus edges.

The intended clean scenario has these properties:

```text
zero_overlap_selected_count = 0
top_loaded_edge_on_target_corridor = true
target_to_non_focus_load_ratio is high
endpoint and satellite-interface load ratios stay at or below their caps
fallback_phase_summary.csv shows strict or overlap-preserving relax phases
```

Flow selection samples a fixed baseline horizon by default, rather than the
simulation duration. This means a 10 s smoke generation, a 60 s sanity run, and
a 200 s formal run can share the same selected background pairs when their
traffic mode, load level, background-flow count, focus pair, seedless selection
settings, and per-flow-rate reference count are unchanged. Compare
`flow_selection_hash` and `selection_input_hash` in `schedule_summary.csv`,
`udp_burst_schedule.csv` metadata, or `run_metadata.json` to verify schedule
stability. If explicit duration-dependent sampling is desired, pass
`--selection-sample-times-s` and record those timestamps with the run.

`random_general`

Runs focus flows plus random endpoint traffic. This is intended for robustness
checks rather than a controlled hotspot.

## Focus Pair Configuration

The legacy default focus pair remains:

```text
738 <-> 793
Rio-de-Janeiro <-> Sankt-Peterburg-(Saint-Petersburg)
```

Step 1, step 2, and step 3 all accept:

```bash
--src-node-id 754 --dst-node-id 785
```

Both values must be different OneWeb top-100 ground-station node IDs in the
inclusive range `720-819`. The reciprocal focus flows are generated
automatically, so the example schedules both `754 -> 785` and `785 -> 754`.

New run names include the ordered focus-pair tag:

```text
run_core_isl_hotspot_specific_src754_dst785_load_1p4x_bg_flow_count_24_oneweb_isls_moving_udp_pdr
```

This prevents different focus-pair experiments from overwriting one another.
Step 2 and step 3 can still read old untagged run folders for the default
`738 <-> 793` pair when no tagged folder exists. Custom pairs never fall back
to an untagged folder. Cross-load and cross-background-count comparison plots
are also written under a `srcXXX_dstYYY` subdirectory.

The recommended main controlled-ISL pair is:

```text
754 <-> 785
Johannesburg <-> Kitakyushu-Fukuoka-M.M.A.
```

Start with `load=1.4`, `background-flow-count=24`,
`per-flow-rate-reference-background-flow-count=4`, and a 10 s smoke
generation (`traffic-stop-time-s=8`). Follow with a 60 s sanity run only after
the selection diagnostics are clean. Do not start with a 200 s formal run.

Use `--dry-run` to execute focus-pair validation and background-flow selection
without creating or overwriting a formal run directory and without launching
NS-3. The terminal summary reports the planned tagged run name, selected flow
count, strict/fallback counts, zero-overlap count, target/non-focus load ratio,
maximum endpoint and satellite-interface ratios, and selection hashes.

The generated `run_metadata.json`, `config_ns3.properties`,
`udp_burst_schedule.csv` metadata, `schedule_summary.csv`, and all
flow-selection diagnostic CSVs record the focus node IDs, names when
available, `focus_pair_tag`, and reciprocal direction count.

Only one focus pair can be selected per command invocation. Multi-pair list or
CSV sweep syntax is not currently implemented; invoke the command once per
pair. Tagged run names keep those invocations isolated.

## Load Mapping

For `focus_only` and `random_general`, the legacy mapping is still:

```text
aggregate_offered_rate_mbps = load_level * isl_data_rate_megabit_per_s
per_flow_rate_mbps = aggregate_offered_rate_mbps / N
```

For `core_hotspot_specific` and `core_isl_hotspot_specific`, background-flow
count sweeps keep the per-flow UDP rate fixed. The per-flow rate is computed
from a reference background-flow count, then reused for every generated
background-flow count:

```text
reference_flow_count = 2 focus flows + per_flow_rate_reference_background_flow_count
per_flow_rate_mbps = load_level * isl_data_rate_megabit_per_s / reference_flow_count
scheduled_total_offered_rate_mbps = per_flow_rate_mbps * generated_flow_count
```

The default reference background-flow count is `4`, so `--background-flow-count
4 8 16 32 64` increases total scheduled traffic while leaving each flow's
target rate unchanged. The generated run folder includes the count, e.g.
`run_core_isl_hotspot_specific_src738_dst793_load_1p2x_bg_flow_count_16_oneweb_isls_moving_udp_pdr`.

## ISL-Focused Congestion Calibration

The calibration workflow separates access capacity from the ISL capacity:

```text
--isl-data-rate-megabit-per-s 10
--gsl-data-rate-megabit-per-s 100
```

Both options default to `10` Mbps for backward compatibility. The ISL capacity
remains 10 Mbps because it is the controlled bottleneck and the reference scale
for `load_level`. A 100 Mbps GSL is recommended during calibration so endpoint
and satellite-access links have enough headroom and do not dominate loss or
queue saturation.

Non-default capacities are part of the run identity:

```text
run_core_isl_hotspot_specific_src754_dst785_load_1x_bg_flow_count_16_isl10mbps_gsl100mbps_lohi_mgmt_legacy_oneweb_isls_moving_udp_pdr
```

The capacities are also recorded in `config_ns3.properties`,
`run_metadata.json`, `schedule_summary.csv`, and
`comparison_packet_delivery/core/summary_by_algorithm.csv`. This prevents
10/10 Mbps and 10/100 Mbps runs from overwriting or being mistaken for one
another.

`load_level` is an offered-load input, not an observed utilization percentage.
For background-flow sweeps, the current flow count can make total scheduled
traffic much larger than `load_level * ISL capacity`. Congestion labels must
therefore come from the measured ISL utilization produced by NS-3, not directly
from `load_level`.

Run the default short calibration sweep with:

```bash
python run_isl_focused_calibration_sweep.py --force
```

For a faster first-stage mapping sweep, run only the Queue-aware reference:

```bash
python run_isl_focused_calibration_sweep.py \
  --algorithms algorithm_queue_aware_over_isls \
  --force
```

This is sufficient to assign preliminary scenario levels. After selecting one
or more settings in each desired band, run those settings with Baseline and
Queue-aware together to validate improvement space. Only then promote them to
the four-algorithm 60 s experiment.

Its defaults are:

```text
focus pair: 754 <-> 785
traffic mode: core_isl_hotspot_specific
load levels: 1.0, 1.2, 1.4
background flow counts: 16, 24, 32
simulation duration: 10 s
traffic stop: 8 s
ISL/GSL capacity: 10/100 Mbps
algorithms: baseline and queue-aware
```

Use `--generation-only` to create all run directories without starting NS-3,
or `--dry-run` to print the commands only. Override `--algorithms` with all
four formal algorithms after useful congestion levels have been identified.

`step_3_generate_plots.py` automatically invokes the calibration analyzer for
`core_isl_hotspot_specific`. It writes per-run files under:

```text
comparison_packet_delivery/calibration/
  isl_focused_calibration_summary.csv
  isl_focused_calibration_by_algorithm.csv
  isl_focused_scenario_summary.csv
  isl_gsl_bottleneck_check.csv
  congestion_level_mapping.csv
  formal_scenario_recommendations.csv
  isl_utilization_vs_pdr.png
  gsl_vs_isl_saturation.png
  congestion_level_summary.png
  algorithm_congestion_outcomes.png
```

A multi-setting invocation also writes an aggregate directory such as:

```text
runs/comparison_calibration/src754_dst785_isl10mbps_gsl100mbps_10s/
```

ISL p50/p90/p95/max values use duration-weighted, active directed-link samples
from `logs_ns3/isl_utilization.csv` during the traffic-generation interval.
Their source is `measured_throughput`: the NS-3 ISL net device reports its
busy-time ratio for each interval. Target-corridor utilization filters those
samples to directed ISLs marked by `isl_corridor_load_summary.csv`.

There is currently no equivalent measured GSL throughput log. GSL p95/max
values therefore use:

```text
queue_packets / gsl_max_queue_size_pkts
```

and are explicitly marked `queue_occupancy_proxy`. They must not be described
as exact GSL link utilization.

Calibration uses two different congestion labels:

```text
scenario_congestion_label
  = congestion level measured under algorithm_queue_aware_over_isls

algorithm_congestion_label
  = congestion level observed separately for each routing algorithm
```

Queue-aware is the calibration reference because it can use alternate paths.
Baseline shortest-path routing is intentionally not used to define scenario
severity: it can overload one corridor while substantial path diversity remains
available. Baseline remains essential as an outcome and improvement-space
check. For example, one traffic setting can be a Queue-aware-reference `Light`
scenario while the Baseline algorithm outcome is `Overload`.

This is a Queue-aware-reference operational scale, not a routing-independent
theoretical network-capacity bound. Formal results must report both the fixed
scenario label and every algorithm's observed utilization/PDR.

Both labels use measured p95 active-ISL utilization:

```text
Light:     p95 < 0.50
Moderate:  0.50 <= p95 < 0.70
High:      0.70 <= p95 < 0.85
Severe:    0.85 <= p95 < 1.00
Overload:  p95 >= 1.00, or at least three directed ISLs reach 100%
```

For the scenario label, all thresholds and the saturated-link rule are applied
only to the Queue-aware reference row. For an algorithm label, they are applied
to that algorithm's own utilization. Neither label is derived directly from
`load_level`.

For compatibility with earlier calibration consumers,
`recommended_congestion_label` remains in the per-algorithm CSV but now aliases
`scenario_congestion_label`; use `algorithm_congestion_label` for the row's own
outcome.

`safe_for_isl_focused_experiment=true` requires a completed Queue-aware
reference with measured ISL utilization, actual target-corridor activity, no
GSL bottleneck evidence in the calibration algorithms, and no dominant mixed
loss association. A safe Light scenario does not need to reach 60% utilization;
its low Queue-aware utilization is the intended classification. Associated loss
remains a time/path correlation and is not physical-drop proof.

`recommended_for_formal=true` additionally requires Baseline improvement
space, detected from Baseline loss, a PDR gap, or a substantial utilization gap
relative to Queue-aware. This verifies that the traffic setting can distinguish
path concentration from adaptive load distribution without redefining scenario
severity from the Baseline result.

Choose 60 s formal candidates from
`formal_scenario_recommendations.csv`, which selects candidates using the
Queue-aware-reference fields. `isl_focused_scenario_summary.csv` contains one
row per traffic setting; `isl_focused_calibration_by_algorithm.csv` shows how
Baseline, Queue-aware, LoHi, and LHTR behave inside that fixed scenario. Prefer
one safe setting in each available band, then run all four algorithms. Recheck
the Queue-aware-reference label and GSL flag after extending duration. Only
promote stable 60 s settings to 200 s; do not assume a 10 s label remains
unchanged.

Suggested paper wording:

> To isolate the impact of ISL routing decisions, we configure the GSL capacity
> to be sufficiently larger than the ISL capacity. This prevents access links
> from becoming the dominant bottleneck and allows packet loss and congestion
> to primarily reflect ISL-level routing behavior.

## Traffic Timing and Drain Time

UDP traffic is generated during the active traffic interval:

```text
0 <= t < traffic_stop_time_s
```

The NS-3 simulation continues until:

```text
simulation_end_time_s
```

The difference is the drain interval:

```text
drain_time_s = simulation_end_time_s - traffic_stop_time_s
```

This matters because a UDP packet can be counted as sent shortly before the
simulation ends but still be in flight when NS-3 stops. Without a drain
interval, `sent_packets - received_packets` can overestimate true loss by
counting these tail in-flight packets as missing. With drain time enabled,
packets are generated only during the active interval, and received packets are
counted through the simulation end.

By default, `traffic_stop_time_s = simulation_end_time_s` for backward
compatibility, which means no drain interval. For formal UDP/PDR results, use:

```text
traffic_stop_time_s = simulation_end_time_s - 2
```

For example, use `--simulation-end-time-s 60 --traffic-stop-time-s 58` for a
60 s simulation with 2 s of drain time, or `--simulation-end-time-s 200
--traffic-stop-time-s 198` for the 200 s version.

## Usage

From this directory:

```bash
cd paper/lohi_replication/udp_pdr
```

Generate runs:

```bash
python step_1_generate_runs.py \
  --traffic-mode core_hotspot_specific \
  --load-level 1.0 \
  --simulation-end-time-s 60 \
  --traffic-stop-time-s 58 \
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr
```

Regenerate only this experiment's matching run directories:

```bash
python step_1_generate_runs.py \
  --traffic-mode core_hotspot_specific \
  --load-level 1.0 \
  --algorithms algorithm_free_one_only_over_isls algorithm_lhtr \
  --force
```

Run simulations:

```bash
python step_2_run.py \
  --traffic-mode core_hotspot_specific \
  --load-level 1.0 \
  --simulation-end-time-s 60 \
  --traffic-stop-time-s 58 \
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr
```

Analyze and plot:

```bash
python step_3_generate_plots.py \
  --traffic-mode core_hotspot_specific \
  --load-level 1.0 \
  --simulation-end-time-s 60 \
  --traffic-stop-time-s 58 \
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr
```

Small syntax/smoke generation check without running NS-3:

```bash
python step_1_generate_runs.py \
  --traffic-mode core_isl_hotspot_specific \
  --src-node-id 754 \
  --dst-node-id 785 \
  --load-level 1.4 \
  --simulation-end-time-s 10 \
  --traffic-stop-time-s 8 \
  --background-flow-count 24 \
  --per-flow-rate-reference-background-flow-count 4 \
  --algorithms algorithm_free_one_only_over_isls \
  --dry-run
```

Generate the recommended short 10 s focus-pair run without launching NS-3:

```bash
python step_1_generate_runs.py \
  --traffic-mode core_isl_hotspot_specific \
  --src-node-id 754 \
  --dst-node-id 785 \
  --load-level 1.4 \
  --simulation-end-time-s 10 \
  --traffic-stop-time-s 8 \
  --background-flow-count 24 \
  --per-flow-rate-reference-background-flow-count 4 \
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr \
  --force
```

Then run and analyze that smoke case:

```bash
python step_2_run.py \
  --traffic-mode core_isl_hotspot_specific \
  --src-node-id 754 \
  --dst-node-id 785 \
  --load-level 1.4 \
  --simulation-end-time-s 10 \
  --traffic-stop-time-s 8 \
  --background-flow-count 24 \
  --per-flow-rate-reference-background-flow-count 4 \
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr

python step_3_generate_plots.py \
  --traffic-mode core_isl_hotspot_specific \
  --src-node-id 754 \
  --dst-node-id 785 \
  --load-level 1.4 \
  --simulation-end-time-s 10 \
  --traffic-stop-time-s 8 \
  --background-flow-count 24 \
  --per-flow-rate-reference-background-flow-count 4 \
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr
```

For 60 s validation after the 10 s smoke succeeds:

```bash
ALGS="algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr"

for load in 1.2 1.4 1.6; do
  python step_1_generate_runs.py --traffic-mode core_isl_hotspot_specific --load-level "$load" --simulation-end-time-s 60 --traffic-stop-time-s 58 --background-flow-count 4 8 16 32 64 --algorithms $ALGS --force
  python step_2_run.py            --traffic-mode core_isl_hotspot_specific --load-level "$load" --simulation-end-time-s 60 --traffic-stop-time-s 58 --background-flow-count 4 8 16 32 64 --algorithms $ALGS
  python step_3_generate_plots.py --traffic-mode core_isl_hotspot_specific --load-level "$load" --simulation-end-time-s 60 --traffic-stop-time-s 58 --background-flow-count 4 8 16 32 64 --algorithms $ALGS
done
```

Backward-compatible no-drain runs can omit `--traffic-stop-time-s`, or set it
equal to `--simulation-end-time-s`.

## Outputs

NS-3 writes native UDP summaries:

```text
logs_ns3/udp_bursts_outgoing.csv
logs_ns3/udp_bursts_incoming.csv
```

`analyze_packet_delivery.py` merges them into:

```text
logs_ns3/udp_flows.csv
```

Important columns:

```text
flow_id, src, dst, start_time_ns, end_time_ns,
sent_packets, received_packets, lost_packets,
sent_bytes, received_bytes, pdr,
offered_rate_mbps, received_rate_mbps
```

In comparison outputs, `simulation_end_time_s`, `traffic_stop_time_s`,
`drain_time_s`, and `drain_time_enabled` are included so results can be traced
to the active traffic and drain timing.

PDR is interpreted as:

```text
packets received by simulation end / packets sent during the active traffic interval
```

Runs generated without drain time can still be useful as preliminary results,
but they can include tail in-flight artifacts. Do not directly mix old no-drain
PDR values with drain-aware formal values in the same comparison.

## Packet Delivery Output Guide

Step 3 uses the standard output layout by default:

```text
runs/<run_name>/comparison_packet_delivery/
  README.md
  output_manifest.csv
  core/
  diagnostics/
  legacy/
```

`core/` is the formal analysis entry point. Start with:

```text
core/summary_by_algorithm.csv
core/per_flow_delivery.csv
core/loss_attribution_breakdown_v3.csv
core/loss_attribution_detailed_v3.csv
core/congested_interfaces_summary.csv
core/path_replay_diagnostics.csv
core/physical_drop_summary.csv
core/loss_diagnostics.txt
```

`diagnostics/` contains exact event logs, queue evidence, flow-selection
details, and deep-dive plots. `legacy/` contains v1/v2 attribution,
misleading historical names, and old duplicate plots. Legacy files are not
generated by default and are not recommended for paper results.

Synthetic packet loss is:

```text
UDP sender count - UDP receiver count
```

This only means a packet did not reach the UDP application before simulation
end. It is not a physical link-drop trace.

v3 attribution separates three evidence levels:

1. **Exact attribution**: a queue/device or PHY callback, a routing/no-route
   trace, or a `Socket::SendTo()` failure identifies a packet event.
2. **Associated attribution**: dynamic path replay overlaps an at-capacity ISL
   or GSL queue in the same time window. This is inferred congestion evidence.
3. **Unclassified loss**: residual synthetic loss has neither an exact event
   nor a supported association.

Physical drop is best read as **exact traced link/device drop**. Queue
occupancy reaching the configured capacity, including `queue_pkt == 100`, is
only saturation evidence. Exact queue attribution requires enqueue rejection
and a `QueueDrop` or `DropBeforeEnqueue` callback. `UdpFlowTag` makes an event
flow-identifiable after it occurs; it does not cause an event. Exact drop
counts can therefore be zero even when synthetic loss and saturation exist.

ISL associated and GSL associated identify the link type in the replay-path
saturation overlap. Mixed associated means one flow's residual loss has both
ISL and GSL overlap evidence. Mixed is flow-level ambiguity: it does not prove
that every lost packet crossed both bottlenecks, identify the causal link type,
or divide the loss between ISL and GSL.

The default queue timeline is:

```text
diagnostics/queue_saturation_timeline_at_capacity.csv
```

It retains only `is_at_capacity=true` rows. The complete timeline can be
multiple gigabytes and is generated only with:

```bash
--write-full-queue-saturation-timeline
```

Other output controls are:

```bash
--output-layout standard
--write-legacy-outputs
--write-full-diagnostics
--no-write-full-diagnostics
```

`output_manifest.csv` records each output's category, status, description,
source inputs, paper recommendation, and notes. The run-local
`comparison_packet_delivery/README.md` gives the same definitions next to the
results.

Each run parent also includes:

```text
runs/<run_name>/schedule_summary.csv
```

This records `background_flow_count`, generated focus/background flow counts,
fixed `per_flow_rate_mbps`, and scheduled total/background/focus offered rates.
Use it to verify that increasing `background_flow_count` does not reduce the
per-flow UDP target rate.

For `core_isl_hotspot_specific`, step 1 also writes flow-selection diagnostics
under the parent run folder. Step 3 links them under
`comparison_packet_delivery/diagnostics/` when present:

```text
runs/<run_name>/flow_selection_diagnostics.csv
runs/<run_name>/corridor_overlap_summary.csv
runs/<run_name>/gsl_load_by_endpoint.csv
runs/<run_name>/isl_corridor_load_summary.csv
runs/<run_name>/fallback_phase_summary.csv
runs/<run_name>/corridor_concentration_summary.csv
runs/<run_name>/satellite_interface_load_summary.csv
```

Use `gsl_load_by_endpoint.csv` to verify selected source and destination
offered load stays below the endpoint cap/GSL capacity. Use
`satellite_interface_load_summary.csv` to check the first-hop/last-hop
satellite-interface proxy load; `over_satellite_interface_load_cap=true`
indicates a selected schedule may recreate a GSL/interface bottleneck even if
endpoint load is spread out.

Use `corridor_overlap_summary.csv` to compare directed overlap, undirected
overlap, overlap ratio, and non-focus middle edges for each candidate. Use
`isl_corridor_load_summary.csv` to check per-edge estimated offered load,
`on_target_focus_corridor`, `selected_flow_ids_using_edge`, and
`edge_rank_by_load`. `corridor_concentration_summary.csv` is the quick
scenario-quality check: the top loaded edge should ideally be on the target
focus corridor, `zero_overlap_selected_count` should be zero, and
`target_to_non_focus_load_ratio` should be high enough that non-focus spillover
is not the dominant story.

`fallback_phase_summary.csv` reports how many flows were selected by each phase:

```text
strict
relax_per_src_dst_limit
relax_endpoint_cap
relax_corridor_threshold
relax_edge_conflict
fallback_allow_zero_overlap
fallback_insufficient_candidates
```

Treat `fallback_allow_zero_overlap` and `fallback_insufficient_candidates` as
warnings for formal runs. They mean the requested background-flow count could
not be filled while preserving target-corridor overlap under the active caps.

`flow_selection_diagnostics.csv` records selected and rejected candidates,
including directed/undirected overlap, fallback reason, relaxed constraints,
endpoint load ratios, satellite-interface load ratios, candidate ranks before
and after fallback, and the added target/non-focus load estimates. The
`flow_selection_hash` identifies the selected pair set independent of
simulation duration; `selection_input_hash` identifies the selector settings
and sampled baseline timestamps.

## LHTR Traffic-Light Diagnostics

LHTR diagnostics are disabled by default. Enable them for an LHTR run with:

```bash
LHTR_ENABLE_DIAGNOSTICS=1 python step_2_run.py <the usual run arguments>
```

The optional `LHTR_DIAGNOSTICS_DIR` variable changes the run-local relative
directory. Its default is `lhtr_diagnostics`, producing:

```text
runs/<run_name>/algorithm_lhtr/lhtr_diagnostics/
  lhtr_qor_tqor_samples.csv
  lhtr_traffic_light_color_summary.csv
  lhtr_br_sbr_decision_log.csv
  lhtr_br_sbr_summary.csv
  lhtr_decision_reason_summary.csv
  lhtr_fstate_decision_consistency.csv
```

`lhtr_qor_tqor_samples.csv` records each directional ISL's QOR, its next-hop
satellite TQOR, and the resulting maximum-severity color. QOR is the current
outgoing direction's queue occupancy divided by its configured packet-buffer
capacity. TQOR is **Total Queue Occupancy Rate**: the sum of all outgoing
queue packets at the next-hop satellite divided by that satellite's total
outgoing packet-buffer capacity (`degree * buffer size`). TQOR is not a
temporal occupancy metric.

`lhtr_traffic_light_color_summary.csv` gives GREEN/YELLOW/RED counts per
routing snapshot and reports how often TQOR escalated the QOR-only color.
`lhtr_br_sbr_decision_log.csv` records BR, SBR, selected route type, colors,
costs, path stretch, decision reason, available candidate path information,
and the installed fstate next hop. Local candidate paths are reconstructed
within the current PID. Border-pair paths currently contain only the selected
inter-PID border ISL, so target-corridor intersection fields remain `unknown`
until a post-processing step joins them with the scenario corridor data.

`lhtr_br_sbr_summary.csv` aggregates BR/SBR/fallback/no-route usage by
snapshot. `lhtr_decision_reason_summary.csv` aggregates reasons over the whole
run. `lhtr_fstate_decision_consistency.csv` performs exact selected-next-hop
checks for local decisions and for border decisions made while already at the
selected border; conceptual border targets are explicitly marked as not
directly comparable to an immediate fstate next hop.

Step 3 copies the four compact summary/consistency tables into:

```text
runs/<run_name>/comparison_packet_delivery/diagnostics/
```

It does not copy the potentially large per-link and per-decision raw tables.
Missing diagnostics are accepted and produce empty summary tables with stable
headers. When diagnostics are disabled, `algorithm_lhtr/lhtr_diagnostics/`
and its raw CSV files are not created.

These outputs are diagnostics only. Enabling them does not change LHTR's
routing policy, traffic-light thresholds, BR/SBR selector, or delay cost.

Core plots:

```text
core/aggregate_pdr.png
core/focus_flow_pdr.png
core/per_flow_pdr_cdf.png
core/loss_attribution_breakdown_v3.png
core/top_congested_interfaces.png
core/queue_saturation_by_link_type.png
core/queue_saturation_timeline.png
core/top_loss_flows.png
core/destination_loss_summary.png
core/destination_offered_rate_vs_gsl_capacity.png
```

Single-run plots are generated once under their canonical unsuffixed names.
Historical `_bg_flow_count_<N>.png` copies are preserved under
`legacy/duplicates/` during migration but are no longer generated. When
multiple background-flow counts are analyzed together, cross-count plots and
`summary_across_background_flow_counts.csv` are written under:

```text
runs/comparison_packet_delivery_across_background_flow_counts/
```

`affected_flows.csv` lists every flow with synthetic sent-minus-received loss,
while `top_loss_flows.csv` keeps the largest loss contributors. The
destination aggregate report compares offered rate into each destination
against the configured GSL/access capacity when `gsl_data_rate_megabit_per_s`
is available.

`diagnostics/max_queue_occupancy_top_links.png` is based on
sampled/event-derived ISL queue
occupancy from `max_queue_occupancy_by_algorithm.csv`. It is not a physical
packet-drop heatmap. The old `legacy/link_drop_heatmap.png` name is deprecated
and is produced only with `--write-legacy-outputs`.

## Dynamic Closed Loop

The run flow remains:

```text
step_2_run.py -> fstate_0.txt -> NS-3 main_satnet
NS-3 -> calculate_routes.py -> NS-3 -> calculate_routes.py ...
```

Queue statistics are read from `logs_ns3/isl_queue_pkt.csv` and summarized into
`queue_stats/queue_stats_<time_ns>.csv` for queue-aware algorithms. The
`isl_queue_pkt.csv` and `isl_queue_byte.csv` files contain only the current
routing-update window and are overwritten every window.

### Delay-based queue cost

`algorithm_queue_aware_over_isls`, LoHi, and LHTR use delay as the default
queue-aware link cost:

```text
D_prop  = distance_m / 299792458
D_trans = packet_size_bytes * 8 / isl_capacity_bps
D_queue = queue_bytes * 8 / isl_capacity_bps
Cost    = D_prop + D_trans + D_queue
```

All terms and the final cost are in seconds. This avoids the former mix of
physical distance, packet count, alpha weights, and a maximum synthetic
penalty distance. Dijkstra and the queue-aware border scoring therefore compare
one physical unit.

The route calculator reads `isl_data_rate_megabit_per_s` from
`config_ns3.properties` and passes it as the ISL capacity. Outside this
experiment path, the fallback is `QUEUE_DEFAULT_ISL_CAPACITY_BPS`, defaulting
to 1 Gbit/s. Transmission delay is included by default and uses
`QUEUE_DEFAULT_PACKET_SIZE_BYTES=1500`; set
`QUEUE_INCLUDE_TRANSMISSION_DELAY=false` to omit the per-link serialization
term.

The per-window summary now combines `isl_queue_pkt.csv` and
`isl_queue_byte.csv`, producing `packet_max` and `byte_max`. Routing prefers
`byte_max`. Old summaries containing only `packet_max` remain supported and
use:

```text
queued_bits = packet_max * QUEUE_DEFAULT_PACKET_SIZE_BYTES * 8
```

The former alpha / virtual-distance model is retained only for comparisons:

```bash
QUEUE_COST_MODE=legacy_penalty
```

The default is `QUEUE_COST_MODE=delay`. LoHi and LHTR keep their hierarchy,
border policy, and holdover behavior unchanged. LHTR also expresses its
traffic-light scoring additions in seconds in delay mode; traffic-light
occupancy thresholds are unchanged.

EWMA smoothing is intentionally not implemented in this change. The shared
cost helper contains the extension point for adding an EWMA-smoothed queue
delay later if route flapping becomes significant.

Queue tracking also appends every completed window to full-history files:

```text
logs_ns3/isl_queue_pkt_history.csv
logs_ns3/isl_queue_byte_history.csv
logs_ns3/gsl_queue_pkt_history.csv
logs_ns3/gsl_queue_byte_history.csv
```

After both scratch and history files are written, the ISL and GSL trackers are
reset to begin a new measurement window. Resetting the trackers does not clear
the actual NetDevice queues; the new window is initialized with the current
queue occupancy. Routing consumes the per-window ISL packet and byte scratch
files, so `queue_stats/queue_stats_<time_ns>.csv` remains a per-window maximum
rather than a cumulative maximum.

GSL/access queue tracking is enabled for UDP/PDR runs through
`enable_link_queue_tracking=true`. Its per-window scratch files are:

```text
logs_ns3/gsl_queue_pkt.csv
logs_ns3/gsl_queue_byte.csv
```

These files use the same interval format as the ISL queue logs:
`from,to,interval_start_ns,interval_end_ns,value`. GSL interfaces are shared
access interfaces rather than fixed point-to-point links, so `to=-1` means the
destination peer is not fixed at the queue object. Routing algorithms still
consume only the ISL `queue_stats/*.csv`; GSL queues are for analysis and loss
attribution only. v3 attribution requires the append-only history files and
does not fall back to reset-per-window scratch files.

Physical drop tracing is enabled by
`enable_physical_link_drop_tracking=true`. It writes:

```text
logs_ns3/physical_link_drops.csv
logs_ns3/interface_queue_drops.csv
logs_ns3/routing_drops.csv
logs_ns3/udp_send_failures.csv
logs_ns3/udp_bursts_outgoing_send_summary.csv
```

`physical_link_drops.csv` records queue `DropBeforeEnqueue` plus
`MacTxDrop`, `PhyTxDrop`, and `PhyRxDrop` callbacks on tracked ISL and GSL net
devices. `interface_queue_drops.csv` keeps the queue-facing subset of those
events. `MacTxDrop` is useful diagnostic coverage, but queue overflow in the
current ISL/GSL devices also triggers queue `DropBeforeEnqueue`, so analysis
does not add `MacTxDrop` to physical queue-drop counts when queue events are
present. `routing_drops.csv` records arbiter route lookup failures from
`RouteOutput` and `RouteInput`. `udp_send_failures.csv` is header-only when all
`Socket::SendTo()` calls are accepted.

Every UDP burst packet also carries an `UdpFlowTag` PacketTag containing the
UDP burst id (the experiment flow id) and packet sequence number. PacketTags do
not alter the wire payload or packet size and survive packet copies through
routing, queues, and NetDevices. Drop traces read the tag without removing it.
The native ns-3 packet UID is logged as an additional diagnostic key.

The drop trace schema includes:

```text
time_ns, link_type, interface_type, from_node, to_node,
satellite_id, ground_station_id, interface_key,
drop_source, drop_reason, packet_size_bytes,
queue_occupancy_pkt_if_available,
queue_occupancy_byte_if_available,
queue_capacity_pkt_if_available,
flow_id_if_available, packet_sequence_if_available,
packet_uid_if_available, flow_tag_available, trace_hook
```

`interface_key` uses `LINK:from->to`, for example `ISL:240->241` or
`GSL:720->-1`. GSL queues are shared access queues, so `to=-1` means the queue
object is not tied to a fixed peer. If the queue is attached to a satellite
side GSL interface, `from` is the satellite node id. If it is attached to a
ground-station side interface, `from` is the endpoint node id and
`ground_station_id` is the local ground-station index when available.

`forced_receive_error_rate` is a test-only configuration parameter for
exercising the PHY receive-drop trace. It defaults to `0.0`; formal experiment
templates leave it unset. A nonzero value installs receive error models on
tracked ISL and GSL devices and should be used only for short validation runs.

## Detailed Loss Attribution

The original attribution view was intentionally simple:

```text
physical_drop_packets
send_failed_packets
unexplained_loss
```

That view is available only with `--write-legacy-outputs`, and it cannot answer
whether remaining end-to-end loss correlates with ISL or GSL queue saturation.
The legacy v2 diagnostics split the remaining loss into physical trace categories and
conservative association categories:

```text
Physical Queue Drop
Physical PHY Drop
UDP Send Failure
Routing / No-route Drop
IPv4 L3 Drop
ISL Queue Saturation Associated Loss
GSL Queue Saturation Associated Loss
Mixed Queue Saturation Associated Loss
Tail / Drain Possible Loss
Unclassified Unexplained Loss
```

Only an actual trace event such as `DropBeforeEnqueue` is called a physical
queue drop. Queue occupancy reaching configured capacity is reported as
`queue_saturation_associated_loss`, not as physical proof. This warning is
written into `loss_diagnostics.txt`:

```text
Queue-saturation-associated loss is a conservative correlation based on queue
occupancy and flow/path context. It should not be interpreted as a physical drop
proof unless matching physical drop trace events are present.
```

`legacy/loss_attribution_detailed.csv` is flow-level. For each lossy flow it records
synthetic loss, per-flow trace counts when a flow id is available, ISL/GSL/mixed
queue-saturation-associated loss, tail/drain possible loss, unclassified loss,
the dominant association, and the associated interface keys.

`core/congested_interfaces_summary.csv` is interface-level. It lists every interface
that reached configured packet capacity, the first and last saturation times,
max/mean queue occupancy, how many samples were at capacity, and the flow ids
that may have passed that interface when existing diagnostics can provide them.

`diagnostics/queue_saturation_timeline_at_capacity.csv` is the default
interval-level output. It records only at-capacity ISL/GSL rows and estimated
active and lossy flow counts. The full `queue_saturation_timeline.csv` is
optional because it can be multiple gigabytes.

`legacy/loss_attribution_breakdown_v2.csv` is algorithm-level. Its
`attribution_coverage_ratio` is:

```text
1 - unclassified_unexplained_loss / synthetic_lost_packets
```

When `synthetic_lost_packets` is zero, coverage is reported as `1.0`.

## Time-aware Loss Attribution v3

v3 accumulates every `dynamic_state/fstate_<time_ns>.txt` delta in timestamp
order. For a time `t`, it uses the latest snapshot with
`snapshot_time <= t`, then replays the directional path from each flow source
to destination. Replay reports normal paths and explicit diagnostics for
missing entries, no route, loops, invalid next hops, hop-limit exhaustion, and
missing snapshots.

ISL hops map to `ISL:from->to`. GSL queue keys map to the existing shared
channel form `GSL:from->-1`; the actual replay hop is retained separately, and
the output notes that the queue key cannot identify a unique shared-channel
receiver.

The v3 outputs are:

```text
diagnostics/flow_path_timeline.csv
core/path_replay_diagnostics.csv
diagnostics/tag_coverage_diagnostics.csv
core/loss_attribution_detailed_v3.csv
core/loss_attribution_breakdown_v3.csv
core/loss_attribution_breakdown_v3.png
diagnostics/tag_coverage_diagnostics.png
diagnostics/saturation_overlap_by_algorithm.png
```

Exact queue, PHY, routing, and socket-submission events are deduplicated by the
stable flow/sequence packet key. `MacTxDrop` remains diagnostic because it can
describe the same queue overflow as `DropBeforeEnqueue`. Inferred saturation
association is assigned only when a successful replay path and a saturated
interface from `*_queue_pkt_history.csv` overlap in time. This is correlation,
not physical drop proof.

For every flow and algorithm, analysis checks:

```text
exact attributed
+ inferred saturation associated
+ tail in flight possible
+ unclassified
= synthetic lost
```

Any mismatch or exact-event overflow is written to `reconciliation_error`; it
is never silently discarded. v3 also reports path-replay success, flow-tag
coverage, attribution coverage, confidence, and explanatory notes.

## UDP/PDR RTT and Route Visualization

Step 3 also produces focus-flow route and estimated RTT analysis without
rerunning NS-3. The focus pair is read from `run_metadata.json`, with
`udp_burst_schedule.csv`, the step 3 CLI, and the legacy `738 <-> 793` pair as
fallbacks.

Forward and reverse paths are reconstructed by cumulatively applying every
`dynamic_state/fstate_<time_ns>.txt` delta up to each sample time. The shared
`dynamic_path_replay.py` helper detects missing entries, explicit no-route
entries, loops, invalid next hops, and hop-limit exhaustion. Both directions
are retained because UDP/PDR routes can be asymmetric.

The propagation-only estimate is:

```text
propagation_only_rtt
  = forward_path_distance / 299792458
  + reverse_path_distance / 299792458
```

The queue-aware estimate is:

```text
queue_aware_rtt
  = propagation_only_rtt
  + forward_transmission_delay
  + reverse_transmission_delay
  + forward_queue_delay
  + reverse_queue_delay
```

Transmission delay is computed per hop as
`packet_size_bits / link_capacity_bps`. ISL and GSL capacities come from
`config_ns3.properties`. Packet size follows
`QUEUE_DEFAULT_PACKET_SIZE_BYTES` when set and otherwise uses the routing-cost
default of 1500 bytes.

Queue delay uses the latest completed queue-history interval satisfying
`interval_end_ns <= RTT sample time`. Byte histories are preferred:

```text
D_queue = queue_bytes * 8 / link_capacity_bps
```

If a byte history is unavailable for an interface, packet history is used:

```text
D_queue = queue_packets * packet_size_bytes * 8 / link_capacity_bps
```

The CSV records `queue_bytes`, `queue_packets_fallback`, and
`missing_queue_data` sources. A missing hop contributes zero queue delay and is
counted in `queue_samples_missing_count`; this makes the estimate a documented
lower bound rather than causing analysis to fail.

These values are path-replay and queue-occupancy estimates. They are not
packet-level measured RTT. In particular, the queue histories contain
per-window maxima, and the estimate does not model application processing,
retransmission, or the exact queue occupancy seen by an individual packet.
This differs from the TCP `traffic_matrix` RTT output, which primarily sums
forward and reverse propagation distance and does not add UDP/PDR queue
occupancy.

The default step 3 invocation writes RTT CSVs and plots every 100 ms, matching
the default dynamic forwarding-state update interval. It also samples the
traffic stop time:

```bash
python step_3_generate_plots.py \
  --traffic-mode core_isl_hotspot_specific \
  --src-node-id 754 \
  --dst-node-id 785 \
  --load-level 1.4 \
  --background-flow-count 16 \
  --algorithms \
    algorithm_free_one_only_over_isls \
    algorithm_queue_aware_over_isls \
    algorithm_lohi \
    algorithm_lhtr \
  --enable-rtt-analysis \
  --rtt-sample-interval-s 0.1
```

The RTT-over-time plots always start their Y-axis at zero. Use
`--rtt-sample-times 0,10,20,30,40,50,58` only when an intentionally sparse
diagnostic view is desired. Route PNGs remain separately sampled and optional
to avoid producing hundreds of figures:

```bash
python step_3_generate_plots.py <same run selection arguments> \
  --enable-route-visualization \
  --route-plot-times 0,30,58
```

The visualization flag generates both variants from the same replayed paths
and timestamps. Use `--route-plot-variants original` or
`--route-plot-variants world_map` only when intentionally regenerating one
variant (for example, to backfill world maps without touching existing
original figures).

With the standard output layout, the generated files are:

```text
comparison_packet_delivery/
  core/
    udp_rtt_summary_by_algorithm.csv
    udp_rtt_components_by_algorithm.csv
    focus_rtt_over_time.png
    focus_queue_aware_rtt_over_time.png
    rtt_summary_by_algorithm.png
    rtt_component_breakdown.png
    focus_forward_reverse_hop_count.png
  diagnostics/
    udp_focus_rtt_timeseries.csv
    udp_focus_path_timeseries.csv
    udp_rtt_diagnostics.txt
  graphical_routes/
    <algorithm>_focus_forward_path_t<time>s.png
    <algorithm>_focus_reverse_path_t<time>s.png
    <algorithm>_focus_round_trip_path_t<time>s.png
  graphical_routes_world_map/
    <algorithm>_focus_forward_path_t<time>s.png
    <algorithm>_focus_reverse_path_t<time>s.png
    <algorithm>_focus_round_trip_path_t<time>s.png
```

Start with the two summary CSVs and RTT comparison plots. Use the timeseries
CSVs to inspect path asymmetry, hop counts, component delays, replay failures,
and queue-data quality. `graphical_routes/` keeps the lightweight
longitude/latitude view. `graphical_routes_world_map/` adds the Cartopy world
map, the full satellite constellation and ground-station set, and highlighted
labels for every satellite and ground station used by the selected path.

## LoHi Management Satellite Modes

UDP/PDR accepts:

```bash
--lohi-management-mode legacy
--lohi-management-mode control_plane_only
--lohi-management-mode strict_physical_waypoint
```

`legacy` preserves the existing LoHi forwarding behavior: each current
satellite participates directly in border selection and packets are not
required to visit the PID management satellite.

`control_plane_only` uses the management satellite's intra-PID distance field
when selecting the border pair. The physical forwarding state still routes the
current satellite directly toward that selected border. This is
**manager-assisted border selection**, not manager waypoint routing. It does
not necessarily increase hop count or RTT and does not make the manager a
physical queue hotspot; those metrics change only indirectly if a different
border/path is selected.

`strict_physical_waypoint` is intentionally fail-closed in the current
implementation. The NS-3 `ArbiterSingleForward` table is indexed only by final
destination, so it cannot distinguish a packet traveling toward the manager
from the same packet traveling from the manager toward a border. A safe strict
implementation needs a waypoint phase or route-segment packet tag and an
extended fstate/arbiter format. Selecting strict mode writes diagnostics and
then stops before generating an ambiguous forwarding state.

Management mode is recorded in `run_metadata.json`,
`config_ns3.properties`, and the run name:

```text
lohi_mgmt_legacy
lohi_mgmt_control_plane_only
lohi_mgmt_strict_waypoint
```

LoHi writes focus-pair diagnostics beside, not inside, `dynamic_state/`:

```text
lohi_manager_diagnostics/
  lohi_manager_mode_summary.csv
  lohi_manager_waypoint_compliance.csv
  lohi_manager_path_segments.csv
  lohi_manager_hotspot_summary.csv
  lohi_manager_loop_check.csv
```

Use a short smoke before longer experiments:

```bash
COMMON="--traffic-mode core_isl_hotspot_specific --src-node-id 754 \
--dst-node-id 785 --load-level 1.4 --simulation-end-time-s 10 \
--traffic-stop-time-s 8 --background-flow-count 16 \
--per-flow-rate-reference-background-flow-count 4 \
--algorithms algorithm_lohi"

python step_1_generate_runs.py $COMMON \
  --lohi-management-mode control_plane_only --force
python step_2_run.py $COMMON \
  --lohi-management-mode control_plane_only
python step_3_generate_plots.py $COMMON \
  --lohi-management-mode control_plane_only
```

Do not start with a 200-second strict run. Implement and validate NS-3 waypoint
phase support first, then run 10-second and 60-second loop/no-route and manager
compliance checks.

## Hotspot Formal Runner Duration

The Johannesburg-Fukuoka formal workflow uses the five
hotspot-reference candidates selected by
`analysis_reports/hotspot_reference_load_mapping/hotspot_formal_candidate_table.csv`.
It does not use PDR to reselect scenarios:

```text
H40   load=1.0 bg=24 hotspot=47.359%  Hotspot-Light
H60   load=1.2 bg=32 hotspot=59.154%  Hotspot-Moderate
H80   load=1.6 bg=32 hotspot=78.873%  Hotspot-High
H90   load=2.2 bg=48 hotspot=91.171%  Hotspot-Severe
H100+ load=2.8 bg=48 hotspot=116.036% Hotspot-Overload
```

Use the duration-aware runner from this directory. The simulation defaults to
60 s, and `traffic_stop_time_s` defaults to
`simulation_end_time_s - 2`, so the normal command only needs one duration
argument:

```bash
python run_hotspot_5level_formal.py --dry-run
python run_hotspot_5level_formal.py --generation-only --force
python run_hotspot_5level_formal.py --scenarios H40 --force
python run_hotspot_5level_formal.py --force
python run_hotspot_5level_formal.py --aggregate-only
```

`run_hotspot_5level_60s_formal.py` remains as a backward-compatible entry
point with the same 60/58 defaults.

Prepare H80 at 200 s without running NS-3:

```bash
python run_hotspot_5level_formal.py \
  --scenarios H80 \
  --simulation-end-time-s 200 \
  --dry-run

python run_hotspot_5level_formal.py \
  --scenarios H80 \
  --simulation-end-time-s 200 \
  --generation-only \
  --force
```

Run H80 manually after inspecting the generated inputs:

```bash
python run_hotspot_5level_formal.py \
  --scenarios H80 \
  --simulation-end-time-s 200 \
  --force
```

H100+ can later be added to the same 200 s report set:

```bash
python run_hotspot_5level_formal.py \
  --scenarios H100+ \
  --simulation-end-time-s 200 \
  --force
```

Every scenario uses ISL 10 Mbps, GSL 100 Mbps, LoHi
`control_plane_only`, and `LHTR_ENABLE_DIAGNOSTICS=1`. Run identity includes
both simulation end and traffic stop, so 60/58 and 200/198 cannot overwrite
each other:

```text
run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_
sim200s_stop198s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_
oneweb_isls_moving_udp_pdr
```

Normal two-second-drain reports are grouped by simulation duration, not by
individual scenario. This lets an H80-only run and a later H100+ run accumulate
under the same 200 s folder:

```text
runs/hotspot_5level_60s_formal_manifest.csv
analysis_reports/hotspot_5level_60s_formal/
runs/hotspot_5level_200s_formal_manifest.csv
analysis_reports/hotspot_5level_200s_formal/
analysis_reports/hotspot_5level_60s_comparison/
analysis_reports/hotspot_5level_200s_comparison/
```

If traffic stop is explicitly changed from the normal two-second drain, the
folder label also includes the stop time, for example
`hotspot_5level_200s_stop195s_formal`. Manifest, formal summary, comparison
summary, and output catalog record `scenario_set`, simulation end, traffic
stop, and duration label.

RTT and route visualization defaults scale with duration:

- Up to 60 s: RTT interval 0.1 s.
- Longer runs: RTT interval 1 s. For 200/198 this gives about 199 samples,
  avoiding the sparse 40-sample shape produced by a 5 s interval without the
  roughly 1,981 samples produced by 0.1 s.
- Route plots are sampled every 30 s, include traffic stop, and are capped at
  10 timestamps. For 200/198 the timestamps are
  `0,30,60,90,120,150,180,198`.
- Override these choices with `--rtt-sample-interval-s` and
  `--route-plot-times`.

Analyze any completed subset. Missing scenarios produce warnings instead of
blocking H80-only analysis:

```bash
python analyze_hotspot_5level_formal.py \
  --scenarios H80 \
  --simulation-end-time-s 200
```

After adding H100+, rerun with both scenarios to expand the same comparison
folder:

```bash
python analyze_hotspot_5level_formal.py \
  --scenarios H80,H100+ \
  --simulation-end-time-s 200
```

The runner's `--aggregate-only` mode remains read-only with respect to run
data. Packet-delivery analysis still scans large queue-history CSVs in chunks
and retains only saturation rows needed by the formal diagnostics.

## Current Limitations

PDR remains the primary end-to-end metric. The synthetic loss value
`sent_packets - received_packets` says that a packet did not reach the UDP
receiver by simulation end; it is not, by itself, a physical link drop.

The compatibility analysis still compares synthetic loss against physical drop
trace events and UDP send failures:

```text
unexplained_loss = synthetic_lost_packets
                 - physical_drop_packets
                 - send_failed_packets
```

`unexplained_loss` can remain positive when loss occurs in an untraced layer,
for example generic IPv4 L3 drops, socket/internal buffering, or a trace hook
not covered by the current pass. It can also become negative if future trace
coverage double-counts the same packet, so the diagnostics should be read
together with the stated coverage. Use the v3 CSV files above for time-aware
path correlation and tagged exact attribution; v2 remains available for
compatibility.

`legacy/link_drops.csv` and `legacy/synthetic_link_drops.csv` are optional
synthetic flow-loss summaries for backward compatibility. True physical events
are reported in `diagnostics/physical_link_drops.csv` and summarized in
`core/physical_drop_summary.csv`.

Queue attribution for routing still uses `queue_stats/*.csv` to report max
queue occupancy per ISL. GSL/access queues are summarized separately in
`diagnostics/gsl_queue_summary.csv`,
`core/congested_interfaces_summary.csv`, and
`diagnostics/queue_saturation_timeline_at_capacity.csv`; they are not fed back
into queue-aware routing.

The compatibility v2 association still uses corridor and access-side proxy
diagnostics. v3 instead replays accumulated forwarding-state deltas and
requires same-window path/history overlap. Packet timing for residual synthetic
loss is not available for every packet, so saturation remains an inferred
flow-level association after exact tagged events are removed. Missing or failed
replay stays unclassified rather than being forced into ISL or GSL.

`core/loss_diagnostics.txt` and `diagnostics/statistics.txt` explicitly record the current
attribution scope:

```text
physical_drop_trace_available = true/false
loss_attribution = physical_drop_trace or synthetic_sent_minus_received
max_queue_scope = sampled/event-derived ISL net-device queue; GSL queue summarized separately when available
physical_drop_trace_coverage = DropBeforeEnqueue queue callbacks, MacTxDrop diagnostics, and PhyTxDrop/PhyRxDrop on tracked ISL/GSL NetDevices
gsl_queue_tracking_available = true/false
udp_send_failure_trace_available = true/false
routing_drop_trace_available = true/false
ipv4_l3_drop_trace_available = true/false
```

PDR remains an end-to-end delivery metric. Queue occupancy and utilization logs
are supporting congestion evidence only; packet loss should not be described as
physical ISL queue overflow unless physical drop tracing is enabled. Destination
loss aggregation can reveal possible GSL/access bottlenecks; the stronger claim
requires matching GSL queue buildup or GSL physical drop events, and remaining
`unexplained_loss` should be treated as an attribution gap.
