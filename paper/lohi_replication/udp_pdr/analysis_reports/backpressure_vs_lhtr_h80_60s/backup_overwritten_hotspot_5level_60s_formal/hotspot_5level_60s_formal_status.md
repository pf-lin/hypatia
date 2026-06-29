# Hotspot Formal Status (60s)

Fixed configuration: `src754 <-> dst785`, ISL 10 Mbps, GSL 100 Mbps, simulation 60 s, traffic stop 58 s, LoHi `control_plane_only`, LHTR diagnostics enabled, RTT interval 0.1 s, route times `0,30,58`.

## Scenario Status

| Scenario | Run folder | Step 1 | Step 2 | Step 3 | Status |
| --- | --- | --- | --- | --- | --- |
| H40 | `runs/run_core_isl_hotspot_specific_src754_dst785_load_1x_bg_flow_count_24_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr` | ok | ok | ok | incomplete_warning |
| H60 | `runs/run_core_isl_hotspot_specific_src754_dst785_load_1p2x_bg_flow_count_32_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr` | ok | ok | ok | incomplete_warning |
| H80 | `runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr` | ok | ok | ok | incomplete_warning |
| H90 | `runs/run_core_isl_hotspot_specific_src754_dst785_load_2p2x_bg_flow_count_48_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr` | ok | ok | ok | incomplete_warning |
| H100+ | `runs/run_core_isl_hotspot_specific_src754_dst785_load_2p8x_bg_flow_count_48_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr` | ok | ok | ok | incomplete_warning |

## Completion

- Complete algorithm rows without warnings: 20/25
- Warnings:
  - H40/algorithm_backpressure_over_isls: missing packet-delivery summary; missing RTT summary; missing route plots; incomplete Backpressure diagnostics: backpressure_decision_log.csv,backpressure_summary.csv,backpressure_queue_source_summary.csv,backpressure_fallback_summary.csv,backpressure_path_stretch_summary.csv,backpressure_loop_check.csv
  - H60/algorithm_backpressure_over_isls: missing packet-delivery summary; missing RTT summary; missing route plots; incomplete Backpressure diagnostics: backpressure_decision_log.csv,backpressure_summary.csv,backpressure_queue_source_summary.csv,backpressure_fallback_summary.csv,backpressure_path_stretch_summary.csv,backpressure_loop_check.csv
  - H80/algorithm_backpressure_over_isls: missing packet-delivery summary; missing RTT summary; missing route plots; incomplete Backpressure diagnostics: backpressure_decision_log.csv,backpressure_summary.csv,backpressure_queue_source_summary.csv,backpressure_fallback_summary.csv,backpressure_path_stretch_summary.csv,backpressure_loop_check.csv
  - H90/algorithm_backpressure_over_isls: missing packet-delivery summary; missing RTT summary; missing route plots; incomplete Backpressure diagnostics: backpressure_decision_log.csv,backpressure_summary.csv,backpressure_queue_source_summary.csv,backpressure_fallback_summary.csv,backpressure_path_stretch_summary.csv,backpressure_loop_check.csv
  - H100+/algorithm_backpressure_over_isls: missing packet-delivery summary; missing RTT summary; missing route plots; incomplete Backpressure diagnostics: backpressure_decision_log.csv,backpressure_summary.csv,backpressure_queue_source_summary.csv,backpressure_fallback_summary.csv,backpressure_path_stretch_summary.csv,backpressure_loop_check.csv
