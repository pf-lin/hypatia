import argparse
import os


EXPERIMENT_NAME = "udp_pdr"

# Core values
dynamic_state_update_interval_ms = 100
simulation_end_time_s = 60
enable_isl_utilization_tracking = True
isl_utilization_tracking_interval_ns = 1 * 1000 * 1000 * 1000
enable_link_queue_tracking = True
enable_physical_link_drop_tracking = True

# Satellite network
full_satellite_network_isls = (
    "oneweb_1200_isls_plus_grid_ground_stations_top_100_"
    "algorithm_free_one_only_over_isls"
)
satellite_count = 720
endpoint_node_ids = list(range(720, 820))

# Traffic defaults
focus_src_node_id = 738
focus_dst_node_id = 793
default_background_flow_count = 10
default_random_flow_count = 20
default_packet_trace_flow_count = 2

# Link/load defaults
data_rate_megabit_per_s = 10.0
queue_size_pkt = 100
default_load_level = 1.0
default_load_levels = [0.6, 0.8, 1.0, 1.2, 1.4, 1.8]
smoke_load_level = 0.1

# Algorithms available in this repository. Keep the default broad enough for
# comparisons, while CLI callers can always pass a smaller subset.
default_algorithms = [
    "algorithm_free_one_only_over_isls",
    "algorithm_queue_aware_over_isls",
    "algorithm_lohi",
    "algorithm_tlr",
    "algorithm_lhtr",
]

traffic_modes = ["focus_only", "core_hotspot_specific", "random_general"]
traffic_mode_selections = traffic_modes + ["all"]
default_traffic_mode_selection = "core_hotspot_specific"


def repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))


def experiment_dir():
    return os.path.dirname(os.path.abspath(__file__))


def satellite_network_dir():
    return os.path.join(
        repo_root(),
        "paper",
        "satellite_networks_state",
        "gen_data",
        full_satellite_network_isls,
    )


def load_level_to_tag(load_level):
    return ("%.3gx" % float(load_level)).replace(".", "p")


def parse_load_levels(values):
    if values is None:
        return [default_load_level]
    if isinstance(values, str):
        values = [values]

    result = []
    for value in values:
        if str(value).lower() == "all":
            result.extend(default_load_levels)
        elif str(value).lower() == "smoke":
            result.append(smoke_load_level)
        else:
            load_level = float(value)
            if load_level <= 0:
                raise ValueError("Load level must be positive: %s" % value)
            result.append(load_level)

    deduped = []
    seen = set()
    for item in result:
        key = "%.10f" % item
        if key not in seen:
            deduped.append(item)
            seen.add(key)
    return deduped


def get_traffic_modes(selected_mode=default_traffic_mode_selection):
    if selected_mode is None:
        selected_mode = default_traffic_mode_selection
    if selected_mode == "all":
        return list(traffic_modes)
    if selected_mode in traffic_modes:
        return [selected_mode]
    raise ValueError(
        "Invalid traffic mode '%s'. Expected one of: %s"
        % (selected_mode, ", ".join(traffic_mode_selections))
    )


def normalize_algorithms(algorithms=None):
    if algorithms is None or len(algorithms) == 0:
        return list(default_algorithms)
    return list(algorithms)


def seconds_to_ns(seconds):
    return int(round(float(seconds) * 1000 * 1000 * 1000))


def add_traffic_mode_argument(parser):
    parser.add_argument(
        "--traffic-mode",
        choices=traffic_mode_selections,
        default=None,
        help=(
            "Traffic mode to use: focus_only, core_hotspot_specific, "
            "random_general, or all. Default: %s"
        ) % default_traffic_mode_selection,
    )


def add_load_level_argument(parser):
    parser.add_argument(
        "--load-level",
        nargs="+",
        default=None,
        help=(
            "One or more offered-load multipliers. Use 'all' for %s or "
            "'smoke' for %.2f. Default: %.1f"
        ) % (default_load_levels, smoke_load_level, default_load_level),
    )


def add_algorithms_argument(parser):
    parser.add_argument(
        "--algorithms",
        nargs="+",
        default=None,
        help="Routing algorithms to run. Default: %s" % " ".join(default_algorithms),
    )


def add_runtime_override_arguments(parser):
    parser.add_argument(
        "--simulation-end-time-s",
        type=float,
        default=None,
        help="Override simulation duration in seconds.",
    )
    parser.add_argument(
        "--traffic-stop-time-s",
        type=float,
        default=None,
        help=(
            "Stop generating UDP traffic at this simulation time. "
            "Default: simulation_end_time_s (no drain interval)."
        ),
    )
    parser.add_argument(
        "--dynamic-state-update-interval-ms",
        type=float,
        default=None,
        help="Override closed-loop route update interval in milliseconds.",
    )
    parser.add_argument(
        "--queue-size-pkt",
        type=int,
        default=None,
        help="Override ISL/GSL queue size in packets.",
    )
    parser.add_argument(
        "--background-flow-count",
        type=int,
        default=None,
        help="Override number of background flows for core_hotspot_specific.",
    )
    parser.add_argument(
        "--random-flow-count",
        type=int,
        default=None,
        help="Override number of flows for random_general.",
    )


def add_common_run_arguments(parser):
    add_traffic_mode_argument(parser)
    add_load_level_argument(parser)
    add_algorithms_argument(parser)
    add_runtime_override_arguments(parser)


def describe_selection(args):
    selected_traffic_mode = (
        args.traffic_mode
        if args.traffic_mode is not None
        else default_traffic_mode_selection
    )
    selected_traffic_modes = get_traffic_modes(selected_traffic_mode)
    selected_load_levels = parse_load_levels(args.load_level)
    selected_algorithms = normalize_algorithms(args.algorithms)
    return selected_traffic_mode, selected_traffic_modes, selected_load_levels, selected_algorithms


def run_name_for(traffic_mode, load_level):
    return "run_%s_load_%s_oneweb_isls_moving_udp_pdr" % (
        traffic_mode,
        load_level_to_tag(load_level),
    )


def get_udp_pdr_run_list(
    selected_mode=default_traffic_mode_selection,
    load_levels=None,
    algorithms=None,
    simulation_end_time_s_override=None,
    traffic_stop_time_s_override=None,
    update_interval_ms_override=None,
    queue_size_pkt_override=None,
    background_flow_count_override=None,
    random_flow_count_override=None,
):
    load_levels = parse_load_levels(load_levels)
    algorithms = normalize_algorithms(algorithms)
    sim_end_s = (
        simulation_end_time_s
        if simulation_end_time_s_override is None
        else float(simulation_end_time_s_override)
    )
    traffic_stop_s = (
        sim_end_s
        if traffic_stop_time_s_override is None
        else float(traffic_stop_time_s_override)
    )
    update_ms = (
        dynamic_state_update_interval_ms
        if update_interval_ms_override is None
        else float(update_interval_ms_override)
    )
    queue_pkts = (
        queue_size_pkt
        if queue_size_pkt_override is None
        else int(queue_size_pkt_override)
    )
    background_flow_count = (
        default_background_flow_count
        if background_flow_count_override is None
        else int(background_flow_count_override)
    )
    random_flow_count = (
        default_random_flow_count
        if random_flow_count_override is None
        else int(random_flow_count_override)
    )

    if sim_end_s <= 0:
        raise ValueError("simulation_end_time_s must be positive")
    if traffic_stop_s < 0 or traffic_stop_s > sim_end_s:
        raise ValueError(
            "traffic_stop_time_s must satisfy 0 <= traffic_stop_time_s <= "
            "simulation_end_time_s (got traffic_stop_time_s=%s, "
            "simulation_end_time_s=%s)"
            % (traffic_stop_s, sim_end_s)
        )
    if update_ms <= 0:
        raise ValueError("dynamic_state_update_interval_ms must be positive")
    if queue_pkts <= 0:
        raise ValueError("queue_size_pkt must be positive")
    if background_flow_count < 0:
        raise ValueError("background_flow_count must be non-negative")
    if random_flow_count <= 0:
        raise ValueError("random_flow_count must be positive")

    sim_end_ns = seconds_to_ns(sim_end_s)
    traffic_stop_ns = seconds_to_ns(traffic_stop_s)
    if traffic_stop_ns > sim_end_ns:
        raise ValueError(
            "traffic_stop_time_ns must be <= simulation_end_time_ns "
            "(got traffic_stop_time_ns=%d, simulation_end_time_ns=%d)"
            % (traffic_stop_ns, sim_end_ns)
        )
    drain_time_ns = sim_end_ns - traffic_stop_ns
    drain_time_s = drain_time_ns / 1e9

    run_list = []
    for traffic_mode in get_traffic_modes(selected_mode):
        for load_level in load_levels:
            for algorithm in algorithms:
                run_list.append({
                    "name": run_name_for(traffic_mode, load_level),
                    "traffic_mode": traffic_mode,
                    "movement": "moving",
                    "satellite_network": full_satellite_network_isls,
                    "dynamic_state": "dynamic_state",
                    "dynamic_state_algorithm": algorithm,
                    "dynamic_state_update_interval_ns": int(update_ms * 1000 * 1000),
                    "simulation_end_time_ns": sim_end_ns,
                    "simulation_end_time_s": sim_end_s,
                    "traffic_stop_time_ns": traffic_stop_ns,
                    "traffic_stop_time_s": traffic_stop_s,
                    "drain_time_ns": drain_time_ns,
                    "drain_time_s": drain_time_s,
                    "drain_time_enabled": drain_time_ns > 0,
                    "data_rate_megabit_per_s": data_rate_megabit_per_s,
                    "queue_size_pkt": queue_pkts,
                    "load_level": float(load_level),
                    "background_flow_count": background_flow_count,
                    "random_flow_count": random_flow_count,
                    "enable_isl_utilization_tracking": enable_isl_utilization_tracking,
                    "isl_utilization_tracking_interval_ns": isl_utilization_tracking_interval_ns,
                    "enable_link_queue_tracking": enable_link_queue_tracking,
                    "enable_physical_link_drop_tracking": enable_physical_link_drop_tracking,
                    "src_node_id": focus_src_node_id,
                    "dst_node_id": focus_dst_node_id,
                    "packet_trace_flow_count": default_packet_trace_flow_count,
                })
    return run_list


def add_force_and_dry_run_arguments(parser):
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite run directories inside this new udp_pdr experiment.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned runs without creating files.",
    )


def build_arg_parser(description):
    parser = argparse.ArgumentParser(description=description)
    add_common_run_arguments(parser)
    return parser
