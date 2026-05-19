# Core values
dynamic_state_update_interval_ms = 100                           # 100 millisecond update interval
simulation_end_time_s = 200                                      # 200 seconds
enable_isl_utilization_tracking = True                           # Enable utilization tracking
isl_utilization_tracking_interval_ns = 1 * 1000 * 1000 * 1000    # 1 second utilization intervals
enable_link_queue_tracking = True                                # Enable link queue tracking

# Derivatives
dynamic_state_update_interval_ns = dynamic_state_update_interval_ms * 1000 * 1000
simulation_end_time_ns = simulation_end_time_s * 1000 * 1000 * 1000
dynamic_state = "dynamic_state"

# Satellite network
full_satellite_network_isls = "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls"

# Routing algorithm (same as lohi_replication/a_b)
# algorithm_queue_aware_over_isls / algorithm_tlr / algorithm_lohi / algorithm_lhtr
routing_algorithm = "algorithm_lhtr"

# Traffic modes and movement modes (mirrors ns3_experiments/traffic_matrix)
traffic_modes = ["specific", "general"]
movement_modes = ["moving"]  # Only dynamic (moving) makes sense here; static is handled separately if needed
traffic_mode_selections = ["specific", "general", "both"]
default_traffic_mode_selection = "both"


def get_traffic_modes(selected_mode=default_traffic_mode_selection):
    if selected_mode is None:
        selected_mode = default_traffic_mode_selection

    if selected_mode == "both":
        return list(traffic_modes)
    if selected_mode in traffic_modes:
        return [selected_mode]
    raise ValueError(
        "Invalid traffic mode '%s'. Expected one of: %s"
        % (selected_mode, ", ".join(traffic_mode_selections))
    )


def add_traffic_mode_argument(parser):
    parser.add_argument(
        "--traffic-mode",
        choices=traffic_mode_selections,
        default=None,
        help=(
            "Traffic matrix mode to run: specific, general, or both. "
            "Default: %s"
        ) % default_traffic_mode_selection,
    )


def describe_traffic_mode_selection(selected_mode=None):
    if selected_mode is None:
        selected_mode = default_traffic_mode_selection
    return selected_mode, get_traffic_modes(selected_mode)


def get_tm_dynamic_run_list(selected_mode=default_traffic_mode_selection):
    run_list = []
    for traffic_mode in get_traffic_modes(selected_mode):
        for movement in movement_modes:
            run_list.append({
                "name": "run_%s_tm_pairing_oneweb_isls_%s_dynamic" % (traffic_mode, movement),
                "traffic_mode": traffic_mode,
                "movement": movement,
                "satellite_network": full_satellite_network_isls,
                "dynamic_state": dynamic_state,
                "dynamic_state_algorithm": routing_algorithm,
                "dynamic_state_update_interval_ns": dynamic_state_update_interval_ns,
                "simulation_end_time_ns": simulation_end_time_ns,
                "data_rate_megabit_per_s": 10.0,
                "queue_size_pkt": 100,
                "enable_isl_utilization_tracking": enable_isl_utilization_tracking,
                "isl_utilization_tracking_interval_ns": isl_utilization_tracking_interval_ns,
                "enable_link_queue_tracking": enable_link_queue_tracking,
                # Focus pair (same as ns3_experiments/traffic_matrix)
                "src_node_id": 738,
                "dst_node_id": 793,
            })
    return run_list
