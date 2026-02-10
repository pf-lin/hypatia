# Core values
dynamic_state_update_interval_ms = 100                          # 100 millisecond update interval
simulation_end_time_s = 200                                     # 200 seconds
pingmesh_interval_ns = 1 * 1000 * 1000                          # A ping every 1ms
enable_isl_utilization_tracking = True                          # Enable utilization tracking
isl_utilization_tracking_interval_ns = 1 * 1000 * 1000 * 1000   # 1 second utilization intervals
enable_link_queue_tracking = True                               # Enable link queue tracking

# Derivatives
dynamic_state_update_interval_ns = dynamic_state_update_interval_ms * 1000 * 1000
simulation_end_time_ns = simulation_end_time_s * 1000 * 1000 * 1000
dynamic_state = "dynamic_state"
routing_algorithm = "algorithm_tlr"
# routing_algorithm = "algorithm_queue_aware_over_isls"

# Chosen pairs:
# > Paris (744) to Moscow (741)
# > Chicago (757) to Zhengzhou (807)
# > Chicago (757) to Lagos (736)
# > Los-Angeles-Long-Beach-Santa-Ana (740) to Shanghai (722)
full_satellite_network_isls = "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls"
# full_satellite_network_isls = "iridium_780_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls"
chosen_pairs = [
    # ("oneweb_1200_isls", 744, 741, "TcpNewReno", full_satellite_network_isls),
    # ("oneweb_1200_isls", 744, 741, "TcpVegas", full_satellite_network_isls),
    # ("oneweb_1200_isls", 757, 807, "TcpNewReno", full_satellite_network_isls, routing_algorithm),
    # ("oneweb_1200_isls", 757, 807, "TcpVegas", full_satellite_network_isls),
    ("oneweb_1200_isls", 757, 736, "TcpNewReno", full_satellite_network_isls, routing_algorithm),
    # ("oneweb_1200_isls", 757, 736, "TcpVegas", full_satellite_network_isls),
    # ("oneweb_1200_isls", 740, 722, "TcpNewReno", full_satellite_network_isls),
    # ("oneweb_1200_isls", 740, 722, "TcpVegas", full_satellite_network_isls),
    # ("iridium_780_isls", 75, 68, "TcpNewReno", full_satellite_network_isls, routing_algorithm),
]


def get_tcp_dynamic_run_list():
    run_list = []
    for p in chosen_pairs:
        run_list += [
            {
                "name": p[0] + "_" + str(p[1]) + "_to_" + str(p[2]) + "_with_" + p[3] + "_at_10_Mbps_dynamic",
                "satellite_network": p[4],
                "dynamic_state": dynamic_state,
                "dynamic_state_algorithm": p[5],
                "dynamic_state_update_interval_ns": dynamic_state_update_interval_ns,
                "simulation_end_time_ns": simulation_end_time_ns,
                "data_rate_megabit_per_s": 10.0,
                "queue_size_pkt": 100,
                "enable_isl_utilization_tracking": enable_isl_utilization_tracking,
                "isl_utilization_tracking_interval_ns": isl_utilization_tracking_interval_ns,
                "enable_link_queue_tracking": enable_link_queue_tracking,
                "from_id": p[1],
                "to_id": p[2],
                "tcp_socket_type": p[3],
            },
        ]

    return run_list


def get_pings_dynamic_run_list():

    # TCP transport protocol does not matter for the ping run
    reduced_chosen_pairs = []
    for p in chosen_pairs:
        if not (p[0], p[1], p[2], p[4], p[5]) in reduced_chosen_pairs:
            reduced_chosen_pairs.append((p[0], p[1], p[2], p[4], p[5]))  # Stripped out p[3] = transport protocol

    run_list = []
    for p in reduced_chosen_pairs:
        run_list += [
            {
                "name": p[0] + "_" + str(p[1]) + "_to_" + str(p[2]) + "_pings" + "_dynamic",
                "satellite_network": p[3],
                "dynamic_state": dynamic_state,
                "dynamic_state_algorithm": p[4],
                "dynamic_state_update_interval_ns": dynamic_state_update_interval_ns,
                "simulation_end_time_ns": simulation_end_time_ns,
                "data_rate_megabit_per_s": 10000.0,
                "queue_size_pkt": 100000,
                "enable_isl_utilization_tracking": enable_isl_utilization_tracking,
                "isl_utilization_tracking_interval_ns": isl_utilization_tracking_interval_ns,
                "enable_link_queue_tracking": enable_link_queue_tracking,
                "from_id": p[1],
                "to_id": p[2],
                "pingmesh_interval_ns": pingmesh_interval_ns,
            }
        ]

    return run_list