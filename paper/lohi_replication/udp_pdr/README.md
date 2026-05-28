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

## Folder Structure

```text
paper/lohi_replication/udp_pdr/
  dynamic_run_list.py
  step_1_generate_runs.py
  step_2_run.py
  step_3_generate_plots.py
  calculate_routes.py
  analyze_packet_delivery.py
  plot_packet_delivery_comparison.py
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
  logs_ns3/
  queue_stats/
  prev_output_cache/
```

## Traffic Modes

`focus_only`

Runs only the two focus flows:

```text
738 -> 793
793 -> 738
```

`core_hotspot_specific`

Runs the focus flows plus background UDP flows selected by a baseline
shortest-path overlap heuristic. The selector prefers background pairs whose
paths overlap the focus pair's middle ISL corridor while avoiding the focus
first-hop and last-hop satellites.

`random_general`

Runs focus flows plus random endpoint traffic. This is intended for robustness
checks rather than a controlled hotspot.

## Load Mapping

For a run with `N` UDP flows:

```text
aggregate_offered_rate_mbps = load_level * isl_data_rate_megabit_per_s
per_flow_rate_mbps = aggregate_offered_rate_mbps / N
```

With the default 10 Mbps links and `load_level=1.0`, all UDP flows together
offer about 10 Mbps along the selected workload. Higher load levels such as
`1.4` intentionally push the bottleneck harder.

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
  --traffic-mode focus_only \
  --load-level smoke \
  --simulation-end-time-s 1 \
  --algorithms algorithm_free_one_only_over_isls \
  --dry-run
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

Run-level comparison outputs:

```text
runs/<run_name>/comparison_packet_delivery/statistics.txt
runs/<run_name>/comparison_packet_delivery/per_flow_delivery.csv
runs/<run_name>/comparison_packet_delivery/summary_by_algorithm.csv
runs/<run_name>/comparison_packet_delivery/focus_flow_delivery.csv
runs/<run_name>/comparison_packet_delivery/pairwise_algorithm_comparison.csv
runs/<run_name>/comparison_packet_delivery/affected_flows.csv
runs/<run_name>/comparison_packet_delivery/top_loss_flows.csv
runs/<run_name>/comparison_packet_delivery/destination_loss_summary.csv
runs/<run_name>/comparison_packet_delivery/loss_diagnostics.txt
runs/<run_name>/comparison_packet_delivery/synthetic_link_drops.csv
runs/<run_name>/comparison_packet_delivery/link_drops.csv
runs/<run_name>/comparison_packet_delivery/max_queue_occupancy_by_algorithm.csv
```

Basic plots:

```text
aggregate_pdr.png
focus_flow_pdr.png
per_flow_pdr_cdf.png
packet_loss_count_by_algorithm.png
failed_flow_count.png
top_loss_flows.png
destination_loss_summary.png
destination_offered_rate_vs_gsl_capacity.png
max_queue_occupancy_top_links.png
```

`affected_flows.csv` lists every flow with synthetic sent-minus-received loss,
while `top_loss_flows.csv` keeps the largest loss contributors. The
destination aggregate report compares offered rate into each destination
against the configured GSL/access capacity when `gsl_data_rate_megabit_per_s`
is available.

`max_queue_occupancy_top_links.png` is based on sampled/event-derived ISL queue
occupancy from `max_queue_occupancy_by_algorithm.csv`. It is not a physical
packet-drop heatmap. The old `link_drop_heatmap.png` name is deprecated if it
appears in older comparison folders; rerunning plots may overwrite it with a
deprecation notice for backward compatibility.

## Dynamic Closed Loop

The run flow remains:

```text
step_2_run.py -> fstate_0.txt -> NS-3 main_satnet
NS-3 -> calculate_routes.py -> NS-3 -> calculate_routes.py ...
```

Queue statistics are read from `logs_ns3/isl_queue_pkt.csv` and summarized into
`queue_stats/queue_stats_<time_ns>.csv` for queue-aware algorithms.

## Current Limitations

The first version prioritizes correct UDP sent/received/lost packet summaries.
It does not add a new NS-3 queue-drop trace hook. If `logs_ns3/link_drops.csv`
does not already exist, analysis writes a synthetic flow-loss summary where
`drop_reason=udp_sent_minus_received`. That is useful for PDR accounting, but it
is not true per-link drop attribution.

Queue attribution currently uses `queue_stats/*.csv` to report max queue
occupancy per ISL. A future NS-3 trace hook can replace the synthetic drop file
with real queue-overflow records.

`loss_diagnostics.txt` and `statistics.txt` explicitly record the current
attribution scope:

```text
physical_drop_trace_available = false
loss_attribution = synthetic_sent_minus_received
max_queue_scope = sampled/event-derived ISL queue
gsl_queue_tracking_available = false
```

PDR remains an end-to-end delivery metric. Queue occupancy and utilization logs
are supporting congestion evidence only; packet loss should not be described as
physical ISL queue overflow unless physical drop tracing is enabled. Destination
loss aggregation can reveal possible GSL/access bottlenecks, but it is still an
inference until GSL queue tracking or physical drop traces confirm it.
