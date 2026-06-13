# Hotspot 5-Level 60s Formal Status

Fixed configuration: `src754 <-> dst785`, ISL 10 Mbps, GSL 100 Mbps, simulation 60 s, traffic stop 58 s, LoHi `control_plane_only`, LHTR diagnostics enabled.

## Scenario Status

| Scenario | Run folder | Step 1 | Step 2 | Step 3 | Status |
| --- | --- | --- | --- | --- | --- |
| H40 | `runs/run_core_isl_hotspot_specific_src754_dst785_load_1x_bg_flow_count_24_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr` | ok | ok | ok | complete |
| H60 | `runs/run_core_isl_hotspot_specific_src754_dst785_load_1p2x_bg_flow_count_32_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr` | ok | ok | ok | complete |
| H80 | `runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr` | ok | ok | ok | complete |
| H90 | `runs/run_core_isl_hotspot_specific_src754_dst785_load_2p2x_bg_flow_count_48_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr` | ok | ok | ok | complete |
| H100+ | `runs/run_core_isl_hotspot_specific_src754_dst785_load_2p8x_bg_flow_count_48_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr` | ok | ok | ok | complete |

## Completion

- Complete algorithm rows without warnings: 20/20
- Warnings: none
