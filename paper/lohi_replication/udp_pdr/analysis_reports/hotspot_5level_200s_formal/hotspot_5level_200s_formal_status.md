# Hotspot Formal Status (200s)

Fixed configuration: `src754 <-> dst785`, ISL 10 Mbps, GSL 100 Mbps, simulation 200 s, traffic stop 198 s, LoHi `control_plane_only`, LHTR diagnostics enabled, RTT interval 1 s, route times `0,30,60,90,120,150,180,198`, route variants `original,world_map,world_map_zoomed`.

## Scenario Status

| Scenario | Run folder | Step 1 | Step 2 | Step 3 | Status |
| --- | --- | --- | --- | --- | --- |
| H80 | `runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim200s_stop198s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr` | ok | ok | ok | complete |

## Completion

- Complete algorithm rows without warnings: 4/4
- Warnings: none
