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
routing_algorithm = "algorithm_tlr"

# Traffic modes and movement modes (mirrors ns3_experiments/traffic_matrix)
traffic_modes = ["specific", "general"]
movement_modes = ["moving"]  # Only dynamic (moving) makes sense here; static is handled separately if needed


def get_tm_dynamic_run_list():
    run_list = []
    for traffic_mode in traffic_modes:
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