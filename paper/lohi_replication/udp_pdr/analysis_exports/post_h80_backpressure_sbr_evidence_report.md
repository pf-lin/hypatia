# Post-H80 Backpressure and SBR Evidence Report

Generated: 2026-06-30 (Asia/Taipei)

This report audits the repository evidence for the H80 60-second Backpressure reference experiment and the LHTR BR/SBR diagnostic analysis. It is written for thesis integration: what can be claimed, where the evidence lives, and which wording should remain conservative.

## 1. Executive Summary

The repository contains enough evidence to support a conservative thesis claim that LHTR outperforms a simplified queue-proxy Backpressure reference in the H80 60-second hotspot setting, while activating SBR decisions much more often on the congestion-relevant target corridor than in the global decision population.

The Backpressure implementation is not a full canonical multi-commodity Backpressure scheduler. It computes a queue-differential score between the current satellite and an ISL neighbor, uses a destination-proxy commodity model, and falls back to shortest path when no legal positive-pressure candidate remains. In the audited H80 run, the effective queue source is node-total queue bytes, fallback is shortest path, and the loop guard is forward-progress by hop count.

The paired H80 60-second result is strong at the experiment-output level:

| Metric | LHTR | Backpressure reference | Difference |
|---|---:|---:|---:|
| Aggregate PDR | 88.68% | 66.25% | Backpressure -22.44 percentage points |
| Focus-flow PDR | 92.93% | 44.39% | Backpressure -48.54 percentage points |
| Lost packets | 49,596 | 147,913 | Backpressure +98,317 |
| Mean RTT | 234.3 ms | 1230.0 ms | Backpressure +995.7 ms |
| p95 RTT | 310.3 ms | 1488.7 ms | Backpressure +1178.3 ms |
| ISL saturation-associated loss | 49,596 | 147,913 | Backpressure +98,317 |

The SBR mechanism evidence is strongest when measured on the congestion-relevant target corridor. In the H80 60-second run, the formal global SBR ratio is only 0.116%, but the target-corridor diagnostic ratio is 14.679%, and the top-25% congested-corridor-segment ratio is 15.633%. This supports the claim that SBR activation is concentrated in the hotspot corridor. It should not be overstated as proof that SBR alone caused the entire LHTR-vs-Backpressure PDR gap.

## 2. Repository State

Repository HEAD at audit time:

```text
b5c7bf873f51bcec3bb8a4ca9bf6c024e27eae93
```

Pre-existing uncommitted state observed before writing this report:

```text
 M .gitignore
?? codex_tasks/
```

The `codex_tasks/` directory contains the requested task document and related planning notes. Those files were already untracked. This audit creates only the following new output files:

```text
paper/lohi_replication/udp_pdr/analysis_exports/post_h80_backpressure_sbr_evidence_report.md
paper/lohi_replication/udp_pdr/analysis_exports/claim_evidence_addendum_backpressure_sbr.md
paper/lohi_replication/udp_pdr/analysis_exports/experiment_figures_manifest_backpressure_sbr.md
```

No source code, simulation runs, CSV outputs, plots, logs, thesis files, commits, or run artifacts were modified by this audit.

## 3. Backpressure Implementation Evidence

Primary implementation:

```text
satgenpy/satgen/dynamic_state/algorithm_backpressure_over_isls.py
```

Key implementation facts:

| Evidence item | Repository evidence | Interpretation |
|---|---|---|
| Algorithm name | `ALGORITHM_NAME = "algorithm_backpressure_over_isls"` | The implemented method is explicitly the ISL-only Backpressure variant used by routing generation. |
| Commodity model | `COMMODITY_MODE = "destination_proxy"` | It does not maintain full per-flow or per-destination satellite queues. Destination is represented through the routing decision target. |
| Default queue source | `queue_source=auto`; H80 audited run uses `node_total_bytes`, effective `node_total_queue_bytes` | The H80 result is a node-total queue proxy experiment, not per-commodity Backpressure. |
| Fallback | `fallback=shortest_path` | When no positive-pressure legal candidate exists, it can still route by shortest path. |
| Loop guard | H80 audited run uses `forward_progress_hop` | Candidate filtering requires progress toward destination by hop distance. |
| Candidate set | Active ISL neighbors, with direct GSL delivery when destination ground station is in range | The method is a satellite routing-state generator, not a MAC scheduler. |
| Decision score | `max(queue_current - queue_neighbor, 0) * link_capacity_bps` | Queue differential is the core positive-pressure signal. |
| Tie-breaking | Positive candidates sorted by descending score, then lower neighbor id | Deterministic selection among positive-pressure candidates. |
| Diagnostics | `algorithm_backpressure_over_isls/backpressure_diagnostics/` | Run-level evidence records queue source, fallback, loop guard, fallback ratio, path replay, and loop checks. |

Supporting dispatch/configuration files:

```text
satgenpy/satgen/dynamic_state/generate_dynamic_state.py
paper/lohi_replication/udp_pdr/calculate_routes.py
paper/lohi_replication/udp_pdr/step_1_generate_runs.py
paper/lohi_replication/udp_pdr/step_2_run.py
paper/lohi_replication/udp_pdr/udp_rtt_analysis.py
```

The routing dispatcher imports `algorithm_backpressure_over_isls` and passes `backpressure_queue_source`, `backpressure_fallback`, `backpressure_loop_guard`, diagnostic flags, and diagnostic pairs. The UDP/RTT analysis label maps this algorithm to `Backpressure`, so thesis figures may use the shorter label if the text defines it as a simplified reference.

### How the Queue-Differential Decision Works

For each candidate ISL neighbor, the implementation computes:

```text
queue_diff = max(queue_current - queue_neighbor, 0)
weight = queue_diff * link_capacity_bps
```

The current and neighbor queues come from the configured queue source. In the audited H80 run, that source is node-total queue bytes, so the comparison is between total outgoing queue occupancy at the current satellite and total outgoing queue occupancy at the neighbor satellite.

If at least one legal candidate has positive weight, the algorithm selects the maximum-weight candidate. If no positive-pressure candidate survives the loop guard and legality filters, the H80 run falls back to shortest path.

### Why This Is a Simplified Backpressure Reference

The implementation is Backpressure-inspired because it uses positive queue differential as the routing preference. It should nevertheless be described conservatively:

Strong thesis wording:

```text
We compare LHTR against a simplified Backpressure reference that uses node-total queue occupancy as a proxy pressure signal and applies shortest-path fallback when no positive-pressure forward-progress candidate is available.
```

Avoid:

```text
LHTR outperforms full multi-commodity Backpressure.
```

Reasons:

- The H80 audited run uses node-total queue bytes, not per-destination or per-flow queues.
- `per_destination_available=False` appears in the queue-source diagnostics for the audited run.
- The method writes forwarding-state snapshots for ns-3, rather than performing per-slot MAC-layer max-weight scheduling.
- Shortest-path fallback is heavily used.
- The loop guard is a route-validity filter and changes the legal candidate set.

## 4. LHTR vs Backpressure Difference

Primary LHTR implementation:

```text
satgenpy/satgen/dynamic_state/algorithm_lhtr.py
```

LHTR combines hierarchical routing, queue-aware link costs, and traffic-light BR/SBR selection. The traffic-light state is built from queue occupancy:

```text
link QOR = queue_packets / TRAFFIC_LIGHT_BUFFER_SIZE
node TQOR = outgoing_queue_packets / (degree * TRAFFIC_LIGHT_BUFFER_SIZE)
```

Thresholds in the implementation:

| Threshold | Value |
|---|---:|
| Link green/yellow QOR | 0.6 |
| Link yellow/red QOR | 0.8 |
| Node green/yellow TQOR | 1/3 |
| Node yellow/red TQOR | 2/3 |

LHTR first identifies the best route candidate (`BR`) and an admissible second-best candidate (`SBR`). Traffic-light logic then chooses SBR when the BR path is yellow/red and an admissible alternative is better under the traffic-light rules. Diagnostics record selected route type, colors, costs, path stretch, and decision reason.

Main conceptual contrast:

| Dimension | LHTR | Backpressure reference |
|---|---|---|
| Congestion signal | Queue-derived traffic-light state plus queue-aware costs | Queue differential between current satellite and candidate neighbor |
| Candidate structure | BR/SBR hierarchical candidate routes | Next-hop ISL neighbor candidates |
| Alternative-path logic | Explicit SBR choice when BR is congested and alternative is admissible | No BR/SBR concept; picks max positive pressure or fallback |
| Fallback in audited run | No fallback/no-route decisions in LHTR diagnostics | Shortest-path fallback used for most decisions |
| Mechanism diagnostics | `lhtr_br_sbr_decision_log.csv`, `lhtr_br_sbr_summary.csv` | `backpressure_decision_log.csv`, `backpressure_summary.csv`, queue/fallback/path-stretch summaries |

This distinction is important for thesis framing. LHTR's advantage can be described as a traffic-light-guided route-selection policy that selectively uses SBR on the congestion-relevant corridor. Backpressure should be framed as a queue-proxy reference route generator, not the same mechanism class.

## 5. H80 60-Second Comparison Results

Primary paired run:

```text
paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_bp_qnodebytes_fbsp_lgfwphop_oneweb_isls_moving_udp_pdr
```

Primary analysis report:

```text
paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/analysis_report_zh.md
```

Primary summary CSV:

```text
paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_summary.csv
```

### 5.1 Delivery and RTT

| Metric | LHTR | Backpressure reference | Thesis-use interpretation |
|---|---:|---:|---|
| Aggregate PDR | 0.8868255193 | 0.6624732444 | LHTR delivers 22.44 p.p. more packets. |
| Focus PDR | 0.9293195748 | 0.4439056560 | LHTR is much stronger on the hotspot focus pair. |
| Background PDR | 0.8841696408 | 0.6761337187 | LHTR also protects background traffic better. |
| Minimum flow PDR | 0.8123981690 | 0.1681278610 | Backpressure reference has a severe worst-flow degradation. |
| p5 flow PDR | 0.8395104353 | 0.2875242455 | LHTR improves lower-tail delivery. |
| Lost packets | 49,596 | 147,913 | Backpressure reference loses 98,317 more packets. |
| Mean RTT | 234.309 ms | 1230.030 ms | Backpressure reference has much higher queueing delay. |
| p95 RTT | 310.345 ms | 1488.676 ms | Backpressure reference has a much worse tail. |
| Mean propagation RTT | 169.681 ms | 154.230 ms | Backpressure's RTT penalty is not propagation distance alone. |
| Mean queue delay | 64.628 ms | 1075.800 ms | Queueing delay dominates Backpressure reference RTT. |

The RTT component evidence supports the narrative that the Backpressure reference suffers from queue accumulation rather than simply choosing longer propagation paths.

### 5.2 Loss Attribution

Loss evidence:

```text
paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_loss.csv
paper/lohi_replication/udp_pdr/runs/.../comparison_packet_delivery/core/loss_attribution_breakdown_v3.csv
```

For both LHTR and the Backpressure reference, exact physical queue/PHY/routing/send-failure categories are zero in the available attribution summary. The dominant category is `isl_saturation_associated_loss`, with full coverage and medium confidence:

| Algorithm | Synthetic lost packets | ISL saturation-associated loss | Confidence |
|---|---:|---:|---|
| LHTR | 49,596 | 49,596 | Medium |
| Backpressure reference | 147,913 | 147,913 | Medium |

Safe thesis wording:

```text
The loss attribution associates the observed sent-minus-received loss with ISL saturation windows, but the diagnostic should be interpreted as association evidence rather than a physical proof of every packet drop location.
```

Avoid:

```text
Every lost packet was physically dropped by a saturated ISL queue.
```

### 5.3 Backpressure Diagnostics

Backpressure diagnostic CSV:

```text
paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_diagnostics_h80_60s.csv
```

Key values:

| Diagnostic | Value |
|---|---:|
| Requested queue source | `node_total_bytes` |
| Effective queue source | `node_total_queue_bytes` |
| Fallback | `shortest_path` |
| Loop guard | `forward_progress_hop` |
| Commodity mode | `destination_proxy` |
| Restricted implementation | `true` |
| Full multi-commodity | `false` |
| Total decisions | 43,200,000 |
| Fallback decisions | 41,370,317 |
| Fallback ratio | 95.765% |
| Positive-pressure decisions | 1,741,087 |
| Positive-pressure ratio | 4.030% |
| Candidate filter ratio | 52.278% |
| Forward-progress success ratio | 47.722% |
| Queue-file exists ratio | 99.833% |
| Loop-detected ratio | 0.000% |
| Reached-destination ratio | 100.000% |
| Average path stretch | 1.0028 |
| p95 path stretch | 1.0526 |
| Two-hop ping-pong decisions | 11,758 |
| Path replay success ratio | 100.000% |

Focus direction asymmetry:

| Flow | PDR |
|---|---:|
| 754 -> 785 | 0.1681278610 |
| 785 -> 754 | 0.7196834510 |

The diagnostic shows that the loop guard prevents path replay loops in the audited Backpressure reference run, but the algorithm mostly falls back because no positive-pressure forward-progress candidate is available after filtering.

### 5.4 LHTR Diagnostics

LHTR diagnostic CSV:

```text
paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/lhtr_diagnostics_h80_60s.csv
```

Key values:

| Diagnostic | Value |
|---|---:|
| Traffic-light scoring mode | `categorical` |
| BR selected count | 79,369,810 |
| SBR selected count | 92,289 |
| SBR selection ratio | 0.116% |
| Fallback count | 0 |
| No-route count | 0 |
| Yellow decisions | 161,229 |
| Red decisions | 33,077 |
| SBR due to yellow | 77,589 |
| SBR due to red | 14,670 |
| No admissible SBR count | 21,432,306 |
| Average yellow links | 32.4317 |
| Average red links | 12.2867 |
| Max yellow/red links | 60 / 25 |
| F-state exact-match ratio | 99.9175% |
| Path replay success ratio | 99.9949% |

Top decision reasons:

| Reason | Share |
|---|---:|
| `br_green` | 72.910% |
| `no_alternative_candidate` | 24.784% |
| `sbr_stretch_too_high` | 2.188% |
| `sbr_due_to_yellow` | 0.098% |
| `sbr_due_to_red` | 0.018% |

Focus direction PDR:

| Flow | PDR |
|---|---:|
| 754 -> 785 | 0.8949491815 |
| 785 -> 754 | 0.9636899682 |

### 5.5 Run-Completion and Sanity Checks

All five algorithm subdirectories in the paired Backpressure-tagged run contain:

```text
logs_ns3/finished.txt: Yes
```

Algorithms:

```text
algorithm_backpressure_over_isls
algorithm_free_one_only_over_isls
algorithm_lhtr
algorithm_lohi
algorithm_queue_aware_over_isls
```

Additional sanity evidence:

- Each algorithm console log contains 599 occurrences of `Python script finished without errors`, one for each routing update.
- Console logs show no matches for exception, traceback, segmentation, aborted, assert, fatal, failed assertion, or missing result patterns.
- `summary_by_algorithm.csv` reports `failed_flow_count = 0` for all five methods.
- `path_replay_diagnostics.csv` reports Backpressure path replay success 19720/19720 and LHTR 19719/19720 with one loop.
- `lhtr_sanity_check_old_vs_new_h80_60s.csv` reports all 13/13 checked metrics matching between the old and new LHTR baseline, including schedule and flow-selection hashes.

This makes the paired H80 60-second comparison suitable as a thesis evidence baseline, with the caveat that it is a single scenario/configuration and should not be generalized beyond the tested regime without additional runs.

## 6. Target-Corridor SBR Diagnostics

Primary script:

```text
paper/lohi_replication/udp_pdr/analyze_lhtr_congested_segment_sbr_ratio.py
```

Primary analysis report:

```text
paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/analysis_report_zh.md
```

Primary summary table:

```text
paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/tables/lhtr_congested_segment_sbr_ratio_summary.csv
```

### 6.1 Definitions

The target corridor is not defined after the fact by observed saturation alone. It is defined from the scenario-generation output:

```text
isl_corridor_load_summary.csv
```

Rows with `on_target_focus_corridor=true` are treated as target-corridor directed ISL edges. These edges come from the focus pair's middle-ISL corridor and the background-flow selection logic for the hotspot scenario.

The top congested segments are a subset of target-corridor segments ranked by measured LHTR utilization over the traffic window. The default analysis uses the top 25% of target-corridor segments, with ranking based primarily on weighted p95 utilization and tie-breakers including mean utilization, max utilization, scheduled load ratio, and red/yellow sample count.

SBR ratios use several denominators:

| Ratio | Meaning |
|---|---|
| Formal global ratio | All LHTR BR/SBR/fallback/no-route counters from `lhtr_br_sbr_summary.csv`. |
| Sample global ratio | Diagnostic-sample rows from `lhtr_br_sbr_decision_log.csv`. |
| Target-corridor ratio | Diagnostic rows whose BR path intersects any target-corridor segment. |
| Top-25% segment ratio | Diagnostic rows whose BR path intersects top congested target-corridor segments. |
| Selected-path top-25% ratio | Auxiliary denominator using selected path intersection. |
| BR-or-selected top-25% ratio | Auxiliary denominator using either BR path or selected path intersection. |

### 6.2 H80 60-Second SBR Evidence

H80 60-second summary:

| Metric | Value |
|---|---:|
| Formal global SBR ratio | 0.116% |
| Sample global SBR ratio | 3.076% |
| Target-corridor decision count | 254,500 |
| Target-corridor SBR selected | 37,359 |
| Target-corridor SBR ratio | 14.679% |
| Top-25% segment decision count | 155,528 |
| Top-25% segment SBR selected | 24,314 |
| Top-25% segment SBR ratio | 15.633% |
| Selected-path top-25% ratio | 13.574% |
| BR-or-selected top-25% ratio | 20.762% |
| Target-corridor share of sample global SBR | 40.480% |
| Target-corridor share of diagnostic decisions | 8.483% |

Top congested target-corridor segments listed for H80 60s:

```text
176->136
136->176
175->135
135->175
135->95
95->135
96->136
55->95
136->96
15->55
643->683
604->644
684->15
```

The key thesis interpretation is concentration: SBR is rare in the global decision population but frequent on the hotspot corridor where congestion matters.

### 6.3 H80 200-Second SBR Evidence

The 200-second H80 diagnostic is useful as a longer-duration mechanism check:

| Metric | Value |
|---|---:|
| Formal global SBR ratio | 0.105% |
| Formal global decision count | 265,031,557 |
| Sample global SBR ratio | 2.779% |
| Sample decision count | 10,000,000 |
| Target-corridor SBR ratio by BR path | 13.927% |
| Target-corridor decision count | 840,805 |
| Top-25% segment SBR ratio by BR path | 13.530% |
| Top-25% segment decision count | 515,017 |
| Selected-path top-25% ratio | 12.180% |
| Selected-path top-25% decision count | 507,102 |
| BR-or-selected top-25% ratio | 18.134% |
| BR-or-selected top-25% decision count | 543,986 |
| Top segment count | 13 / 50 |

This independently supports the same mechanism pattern: the corridor-relevant SBR rate remains around 14% even though the formal global SBR rate is around 0.1%.

### 6.4 Cross-Level Pattern

60-second hotspot levels:

| Hotspot level | Formal global SBR ratio | Target-corridor SBR ratio |
|---|---:|---:|
| H40 | 0.001% | 0.330% |
| H60 | 0.012% | 3.117% |
| H80 | 0.116% | 14.679% |
| H90 | 1.001% | 43.260% |
| H100+ | 1.529% | 49.387% |

This monotonic pattern supports a mechanism claim: as hotspot stress increases, SBR is activated more often on the target corridor. It does not by itself isolate SBR from all other LHTR components, because LHTR also includes queue-aware costs and traffic-light penalties.

## 7. Figures and CSVs

Recommended thesis figures:

| Figure | Path | Use |
|---|---|---|
| H80 PDR/RTT comparison | `paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/figures/backpressure_vs_lhtr_h80_60s_pdr_rtt.png` | Main result figure for LHTR vs simplified Backpressure reference. |
| H80 overview | `paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/figures/backpressure_vs_lhtr_h80_60s_overview.png` | Supplementary overview including delivery/RTT/congestion summary. |
| Global vs target-corridor SBR | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/figures/lhtr_global_vs_target_corridor_sbr_ratio_60s_hotspot_levels.png` | Main mechanism figure showing corridor concentration. |
| SBR denominator comparison | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/figures/lhtr_sbr_ratio_by_denominator_across_levels.png` | Methodology/support figure for denominator sensitivity. |
| H80 200s denominator comparison | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/figures/h80_200s_sbr_ratio_by_denominator.png` | Longer-duration mechanism check. |
| H80 200s top congested segments | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/figures/h80_200s_top_congested_segments_sbr_ratio.png` | Segment-level support for corridor activation. |
| H80 200s SBR concentration | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/figures/h80_200s_sbr_decision_concentration_on_segments.png` | Shows concentration of SBR decisions on congested segments. |

Recommended thesis data tables or appendix sources:

```text
paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_summary.csv
paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_rtt.csv
paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_loss.csv
paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_diagnostics_h80_60s.csv
paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/lhtr_diagnostics_h80_60s.csv
paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/lhtr_sanity_check_old_vs_new_h80_60s.csv
paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/tables/lhtr_congested_segment_sbr_ratio_summary.csv
paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/tables/h80_200s_top_congested_segments.csv
paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/tables/h80_200s_congested_segment_decision_samples.csv
```

No standalone conceptual Backpressure figure was found in the audited outputs. If the thesis needs a conceptual diagram, it should be drawn manually from the implementation formula and clearly labeled as an explanatory schematic, not as a simulation result.

## 8. Thesis Impact

Recommended thesis claim hierarchy:

### Strong Claims

1. In the H80 60-second hotspot scenario, LHTR achieves higher aggregate and focus-flow PDR than the simplified node-total-queue Backpressure reference.
2. The Backpressure reference run mostly falls back to shortest path because positive-pressure forward-progress candidates are often unavailable after filtering.
3. LHTR's SBR activation is concentrated on the target corridor: global SBR is rare, but target-corridor SBR is substantial.
4. RTT component analysis indicates that Backpressure reference delay is dominated by queueing delay rather than propagation RTT.

### Conservative Claims

1. The loss attribution links synthetic sent-minus-received loss to ISL saturation windows with medium confidence.
2. Target-corridor SBR evidence supports mechanism activation, not isolated causal attribution for the full PDR improvement.
3. H80 60-second results are a focused scenario baseline, not a full parameter sweep.

### Claims to Avoid

1. LHTR beats full canonical multi-commodity Backpressure.
2. SBR alone explains the entire H80 PDR improvement.
3. Every lost packet was physically dropped at a saturated ISL queue.
4. The result generalizes to all loads, all seeds, all topologies, or all queue models without additional experiments.

## 9. Claim Boundary

Safe wording for the main thesis text:

```text
We use a simplified Backpressure-inspired reference that computes an ISL next-hop pressure score from queue-differential information. In the H80 hotspot scenario, this reference uses node-total queue bytes, shortest-path fallback, and a forward-progress loop guard. Under this configuration, LHTR improves aggregate PDR from 66.25% to 88.68% and focus-flow PDR from 44.39% to 92.93%, while reducing mean RTT from 1230.0 ms to 234.3 ms. Diagnostics show that the Backpressure reference relies on fallback for 95.77% of decisions, whereas LHTR's SBR decisions are rare globally but concentrated on the target corridor, reaching 14.68% in the H80 60-second diagnostic sample.
```

Optional caveat paragraph:

```text
These results should be interpreted as evidence against this restricted queue-proxy Backpressure reference, not against full multi-commodity Backpressure. The loss diagnostics provide medium-confidence association with ISL saturation windows, and the SBR diagnostics establish where LHTR changes route choices, but they do not isolate SBR as the only causal factor behind the observed delivery improvement.
```

Suggested thesis placement:

- Experiment setup: define Backpressure reference, queue source, fallback, loop guard, and why it is restricted.
- Results section: use PDR/RTT figure and summary table.
- Mechanism subsection: use target-corridor SBR figure and explain the denominator difference.
- Threats to validity: include the simplified Backpressure caveat, medium-confidence loss attribution, and limited scenario coverage.

