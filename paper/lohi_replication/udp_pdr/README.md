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

`core_isl_hotspot_specific`

Runs the same two focus flows plus background UDP flows selected for a cleaner
ISL-bottleneck scenario. It starts from the `core_hotspot_specific`
middle-ISL overlap idea, but adds endpoint load controls so selected background
flows do not all terminate at the same ground-station endpoint. By default it
uses:

```text
endpoint_load_cap_ratio = 0.8
max_background_flows_per_dst = 1
max_background_flows_per_src = 1
hotspot_sample_count = 3
```

This keeps source and destination offered load below the configured GSL
capacity target while still selecting flows that share the baseline focus
middle-ISL corridor. The goal is to make baseline shortest-path routing stress
the ISL corridor, while leaving adaptive algorithms room to reroute around ISL
congestion rather than simply moving the bottleneck to a destination GSL.

`random_general`

Runs focus flows plus random endpoint traffic. This is intended for robustness
checks rather than a controlled hotspot.

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
`run_core_isl_hotspot_specific_load_1p2x_bg_flow_count_16_oneweb_isls_moving_udp_pdr`.

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
  --load-level 1.2 \
  --simulation-end-time-s 10 \
  --traffic-stop-time-s 8 \
  --background-flow-count 4 \
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr \
  --endpoint-load-cap-ratio 0.8 \
  --max-background-flows-per-dst 1 \
  --max-background-flows-per-src 1 \
  --dry-run
```

Generate short 10 s smoke runs for a background-flow-count sweep without
launching NS-3:

```bash
python step_1_generate_runs.py \
  --traffic-mode core_isl_hotspot_specific \
  --load-level 1.2 \
  --simulation-end-time-s 10 \
  --traffic-stop-time-s 8 \
  --background-flow-count 4 8 16 \
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr \
  --force
```

Then run and analyze that smoke case:

```bash
python step_2_run.py \
  --traffic-mode core_isl_hotspot_specific \
  --load-level 1.2 \
  --simulation-end-time-s 10 \
  --traffic-stop-time-s 8 \
  --background-flow-count 4 \
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr

python step_3_generate_plots.py \
  --traffic-mode core_isl_hotspot_specific \
  --load-level 1.2 \
  --simulation-end-time-s 10 \
  --traffic-stop-time-s 8 \
  --background-flow-count 4 \
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
runs/<run_name>/comparison_packet_delivery/physical_drop_summary.csv
runs/<run_name>/comparison_packet_delivery/gsl_queue_summary.csv
runs/<run_name>/comparison_packet_delivery/loss_attribution_summary.csv
runs/<run_name>/comparison_packet_delivery/max_queue_occupancy_by_algorithm.csv
```

Each run parent also includes:

```text
runs/<run_name>/schedule_summary.csv
```

This records `background_flow_count`, generated focus/background flow counts,
fixed `per_flow_rate_mbps`, and scheduled total/background/focus offered rates.
Use it to verify that increasing `background_flow_count` does not reduce the
per-flow UDP target rate.

For `core_isl_hotspot_specific`, step 1 also writes flow-selection diagnostics
under the parent run folder, and step 3 copies them into
`comparison_packet_delivery/` when present:

```text
runs/<run_name>/flow_selection_diagnostics.csv
runs/<run_name>/corridor_overlap_summary.csv
runs/<run_name>/gsl_load_by_endpoint.csv
runs/<run_name>/isl_corridor_load_summary.csv
```

Use `gsl_load_by_endpoint.csv` to verify selected source and destination
offered load stays below the endpoint cap/GSL capacity. Use
`corridor_overlap_summary.csv` and `isl_corridor_load_summary.csv` to check
that selected background flows still overlap the focus middle-ISL corridor and
that the estimated offered load on that corridor approaches or exceeds ISL
capacity. `flow_selection_diagnostics.csv` records selected and rejected
candidates, including edge-conflict flags, endpoint load ratios, selection
rank, and fallback phase if strict constraints were relaxed.

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
physical_drop_count_by_algorithm.png
physical_drop_by_link_type.png
gsl_queue_occupancy_by_algorithm.png
loss_attribution_breakdown.png
```

For single-count runs, plot generation also writes copies with an explicit
`bg_flow_count_<N>` suffix. When multiple background-flow counts are analyzed
together, cross-count plots and `summary_across_background_flow_counts.csv`
are written under:

```text
runs/comparison_packet_delivery_across_background_flow_counts/
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

GSL/access queue tracking is enabled for UDP/PDR runs through
`enable_link_queue_tracking=true`. It writes:

```text
logs_ns3/gsl_queue_pkt.csv
logs_ns3/gsl_queue_byte.csv
```

These files use the same interval format as the ISL queue logs:
`from,to,interval_start_ns,interval_end_ns,value`. GSL interfaces are shared
access interfaces rather than fixed point-to-point links, so `to=-1` means the
destination peer is not fixed at the queue object. Routing algorithms still
consume only the ISL `queue_stats/*.csv`; GSL queues are for analysis and loss
attribution only.

Physical drop tracing is enabled by
`enable_physical_link_drop_tracking=true`. It writes:

```text
logs_ns3/physical_link_drops.csv
logs_ns3/udp_send_failures.csv
logs_ns3/udp_bursts_outgoing_send_summary.csv
```

`physical_link_drops.csv` records queue `DropBeforeEnqueue` plus
`PhyTxDrop`/`PhyRxDrop` callbacks on tracked ISL and GSL net devices.
`MacTxDrop` is not counted separately in this first pass because queue overflow
also triggers `MacTxDrop` in these devices, which would double-count the same
drop. `udp_send_failures.csv` is header-only when all `Socket::SendTo()` calls
are accepted.

## Current Limitations

PDR remains the primary end-to-end metric. The synthetic loss value
`sent_packets - received_packets` says that a packet did not reach the UDP
receiver by simulation end; it is not, by itself, a physical link drop.

The analysis now compares synthetic loss against physical drop trace events and
UDP send failures:

```text
unexplained_loss = synthetic_lost_packets
                 - physical_drop_packets
                 - send_failed_packets
```

`unexplained_loss` can remain positive when loss occurs in an untraced layer,
for example no-route/forwarding drops, socket/internal buffering, or a trace
hook not covered by the first pass. It can also become negative if future trace
coverage double-counts the same packet, so the diagnostics should be read
together with the stated coverage.

`link_drops.csv` and `synthetic_link_drops.csv` remain synthetic flow-loss
summaries for backward compatibility. True physical events are reported in
`physical_link_drops.csv` and summarized in `physical_drop_summary.csv`.

Queue attribution for routing still uses `queue_stats/*.csv` to report max
queue occupancy per ISL. GSL/access queues are summarized separately in
`gsl_queue_summary.csv` and are not fed back into queue-aware routing.

`loss_diagnostics.txt` and `statistics.txt` explicitly record the current
attribution scope:

```text
physical_drop_trace_available = true/false
loss_attribution = physical_drop_trace or synthetic_sent_minus_received
max_queue_scope = sampled/event-derived ISL net-device queue; GSL queue summarized separately when available
physical_drop_trace_coverage = DropBeforeEnqueue queue callbacks and PhyTxDrop/PhyRxDrop on tracked ISL/GSL NetDevices
gsl_queue_tracking_available = true/false
udp_send_failure_trace_available = true/false
```

PDR remains an end-to-end delivery metric. Queue occupancy and utilization logs
are supporting congestion evidence only; packet loss should not be described as
physical ISL queue overflow unless physical drop tracing is enabled. Destination
loss aggregation can reveal possible GSL/access bottlenecks; the stronger claim
requires matching GSL queue buildup or GSL physical drop events, and remaining
`unexplained_loss` should be treated as an attribution gap.
