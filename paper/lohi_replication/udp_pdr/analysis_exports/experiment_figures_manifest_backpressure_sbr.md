# Experiment Figures Manifest: Backpressure Reference and SBR Diagnostics

Generated: 2026-06-30 (Asia/Taipei)

This manifest lists figures and source tables that are useful for moving the Backpressure/SBR evidence into the thesis repository. The `Copy to thesis img folder?` column distinguishes main-text figures from optional appendix/support artifacts.

## Figure Manifest

| Figure / table | Current path | Copy to thesis img folder? | Suggested thesis filename | Suggested caption | Supported claim | Required explanation / caveat |
|---|---|---|---|---|---|---|
| H80 PDR/RTT comparison | `paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/figures/backpressure_vs_lhtr_h80_60s_pdr_rtt.png` | Yes | `fig:h80_lhtr_vs_backpressure_pdr_rtt.png` | H80 hotspot delivery and delay comparison between LHTR and the simplified Backpressure reference. LHTR improves both aggregate/focus PDR and mean/p95 RTT. | LHTR outperforms the simplified Backpressure reference in H80 60s. | Define Backpressure as the node-total-queue, destination-proxy, shortest-path-fallback reference. |
| H80 overview | `paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/figures/backpressure_vs_lhtr_h80_60s_overview.png` | Optional | `fig:h80_lhtr_vs_backpressure_overview.png` | Overview of H80 hotspot performance and congestion diagnostics for LHTR and the simplified Backpressure reference. | Supports delivery, RTT, and congestion narrative in one visual. | Use as appendix if the PDR/RTT figure already appears in the main text. Avoid duplicating the same numbers twice. |
| Global vs target-corridor SBR across hotspot levels | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/figures/lhtr_global_vs_target_corridor_sbr_ratio_60s_hotspot_levels.png` | Yes | `fig:sbr_global_vs_target_corridor_hotspot_levels.png` | SBR decisions are rare globally but become frequent on the congestion-relevant target corridor as hotspot intensity increases. | SBR activation is concentrated where congestion is injected. | Explain the denominator difference: formal global counters vs target-corridor diagnostic rows whose BR path intersects the scenario-defined corridor. |
| SBR ratio by denominator across hotspot levels | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/figures/lhtr_sbr_ratio_by_denominator_across_levels.png` | Optional | `fig:sbr_ratio_denominator_sensitivity.png` | SBR ratio measured under different denominators, showing that corridor-restricted denominators expose mechanism activity hidden by global counts. | Denominator choice matters for interpreting SBR diagnostics. | Present as methodology/support, not as a new performance metric. |
| H80 200s SBR denominator comparison | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/figures/h80_200s_sbr_ratio_by_denominator.png` | Optional | `fig:h80_200s_sbr_denominator_comparison.png` | In the longer H80 diagnostic, target-corridor and top-congested-segment SBR ratios remain much higher than the formal global ratio. | Longer-duration support for SBR concentration. | This is a 200-second mechanism diagnostic, not the paired H80 60-second Backpressure performance comparison. |
| H80 200s top congested segments SBR ratio | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/figures/h80_200s_top_congested_segments_sbr_ratio.png` | Optional | `fig:h80_200s_top_segments_sbr_ratio.png` | Segment-level SBR activity on the most congested target-corridor segments in the H80 200-second diagnostic. | SBR selection concentrates on heavily utilized corridor segments. | Explain that top segments are selected from target-corridor edges using measured LHTR utilization. |
| H80 200s SBR decision concentration | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/figures/h80_200s_sbr_decision_concentration_on_segments.png` | Optional | `fig:h80_200s_sbr_decision_concentration.png` | Distribution of SBR decisions across congested target-corridor segments in the H80 200-second diagnostic. | SBR activity is spatially concentrated rather than uniformly spread. | Use as appendix/support unless the thesis has a dedicated mechanism-analysis subsection. |
| Corridor concentration diagnostic plot | `paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_bp_qnodebytes_fbsp_lgfwphop_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/diagnostics/corridor_concentration_summary.png` | Optional | `fig:h80_corridor_concentration_summary.png` | Scenario-construction diagnostic showing how offered load is concentrated on the focus-pair target corridor. | The hotspot scenario intentionally loads the target corridor. | Use only if the figure exists in the local run directory and is visually clear; otherwise use the CSV evidence. |
| LHTR route plots | `paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_bp_qnodebytes_fbsp_lgfwphop_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/graphical_routes/algorithm_lhtr/` | Optional | `fig:h80_lhtr_route_example_*.png` | Example LHTR route snapshots for the H80 hotspot focus pair. | Visual illustration of routing behavior. | Route snapshots are illustrative; quantitative claims should cite CSV metrics and diagnostics. |
| Backpressure route plots | `paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_bp_qnodebytes_fbsp_lgfwphop_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/graphical_routes/algorithm_backpressure_over_isls/` | Optional | `fig:h80_backpressure_route_example_*.png` | Example route snapshots for the simplified Backpressure reference in the H80 hotspot run. | Visual context for comparator routing behavior. | Do not infer performance from a route snapshot alone; pair with PDR/RTT and diagnostics. |

## Source Tables for Thesis Numbers

These CSV files should be copied to a thesis data folder or archived as experiment provenance if the thesis repository separates figures from raw evidence.

| Table | Current path | Copy to thesis data folder? | Used for |
|---|---|---|---|
| H80 Backpressure vs LHTR summary | `paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_summary.csv` | Yes | PDR, loss count, RTT, queue delay, and route replay metrics. |
| H80 RTT breakdown | `paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_rtt.csv` | Yes | Mean/p95 RTT and propagation vs queue-delay components. |
| H80 loss attribution | `paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_loss.csv` | Yes | Medium-confidence ISL-saturation-associated loss statement. |
| H80 Backpressure diagnostics | `paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_diagnostics_h80_60s.csv` | Yes | Queue source, fallback ratio, positive-pressure ratio, loop-guard and path-replay evidence. |
| H80 LHTR diagnostics | `paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/lhtr_diagnostics_h80_60s.csv` | Yes | BR/SBR counts, traffic-light state, LHTR path-replay evidence. |
| LHTR old-vs-new sanity check | `paper/lohi_replication/udp_pdr/analysis_reports/backpressure_vs_lhtr_h80_60s/lhtr_sanity_check_old_vs_new_h80_60s.csv` | Optional | Confirms the paired Backpressure run did not alter the LHTR baseline. |
| SBR corridor ratio summary | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/tables/lhtr_congested_segment_sbr_ratio_summary.csv` | Yes | Global, target-corridor, and top-congested-segment SBR ratios across hotspot levels. |
| H80 200s top congested segments | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/tables/h80_200s_top_congested_segments.csv` | Optional | Segment-level mechanism evidence for the longer H80 diagnostic. |
| H80 200s congested segment samples | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/tables/h80_200s_congested_segment_decision_samples.csv` | Optional | Example diagnostic rows for selected congested segments. |
| All target corridor segments | `paper/lohi_replication/udp_pdr/analysis_reports/lhtr_congested_segment_sbr_ratio/tables/all_target_corridor_segments.csv` | Optional | Documents the target-corridor edge set used by the SBR analysis. |

## Recommended Main-Text Figure Set

Use two main-text figures if space is tight:

1. `fig:h80_lhtr_vs_backpressure_pdr_rtt.png`
2. `fig:sbr_global_vs_target_corridor_hotspot_levels.png`

Then place the following in an appendix or supplementary experiment section:

1. `fig:h80_lhtr_vs_backpressure_overview.png`
2. `fig:sbr_ratio_denominator_sensitivity.png`
3. `fig:h80_200s_sbr_denominator_comparison.png`
4. `fig:h80_200s_top_segments_sbr_ratio.png`

## Caption Caveat Text

Suggested reusable caveat:

```text
The Backpressure label in these figures denotes the implemented simplified Backpressure reference with destination-proxy commodities, node-total queue bytes in the H80 run, shortest-path fallback, and a forward-progress loop guard. It should not be read as full multi-commodity Backpressure.
```

Suggested reusable SBR denominator note:

```text
The global SBR ratio is computed over all LHTR route decisions, whereas the target-corridor ratio is computed only over diagnostic decisions whose BR path intersects the scenario-defined target corridor. The latter is intended as a mechanism diagnostic for hotspot traffic, not a replacement for the global algorithm counter.
```

## Missing or Manual Figure Work

No standalone conceptual Backpressure schematic was found in the audited output directories. If the thesis needs a conceptual figure, create a new explanatory diagram from the implemented decision rule:

```text
weight(current, neighbor) = max(Q_current - Q_neighbor, 0) * link_capacity
```

Label the schematic as an explanatory diagram and keep it separate from simulation-result figures.

