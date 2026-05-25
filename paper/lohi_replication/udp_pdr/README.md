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
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr
```

Analyze and plot:

```bash
python step_3_generate_plots.py \
  --traffic-mode core_hotspot_specific \
  --load-level 1.0 \
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

Run-level comparison outputs:

```text
runs/<run_name>/comparison_packet_delivery/statistics.txt
runs/<run_name>/comparison_packet_delivery/per_flow_delivery.csv
runs/<run_name>/comparison_packet_delivery/summary_by_algorithm.csv
runs/<run_name>/comparison_packet_delivery/focus_flow_delivery.csv
runs/<run_name>/comparison_packet_delivery/pairwise_algorithm_comparison.csv
runs/<run_name>/comparison_packet_delivery/max_queue_occupancy_by_algorithm.csv
```

Basic plots:

```text
aggregate_pdr.png
focus_flow_pdr.png
per_flow_pdr_cdf.png
packet_loss_count.png
failed_flow_count.png
link_drop_heatmap.png
```

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
