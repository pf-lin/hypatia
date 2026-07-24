import argparse
import csv
import json
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
default_background_flow_count = 4
default_background_flow_count_sweep = [4, 8, 16, 32, 64]
default_per_flow_rate_reference_background_flow_count = 4
default_random_flow_count = 20
default_packet_trace_flow_count = 2
default_endpoint_load_cap_ratio = 0.8
default_max_background_flows_per_dst = 1
default_max_background_flows_per_src = 1
default_satellite_interface_load_cap_ratio = 0.8
default_min_middle_isl_overlap_score = 1
default_min_reachable_overlap_samples = 1
default_min_overlap_ratio = 0.0
default_selection_sample_horizon_s = 60.0

# Link/load defaults
default_isl_data_rate_megabit_per_s = 10.0
default_gsl_data_rate_megabit_per_s = 10.0
# Backward-compatible alias used by older helpers for the ISL-based load scale.
data_rate_megabit_per_s = default_isl_data_rate_megabit_per_s
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

traffic_modes = [
    "focus_only",
    "core_hotspot_specific",
    "core_isl_hotspot_specific",
    "random_general",
]
background_flow_traffic_modes = {
    "core_hotspot_specific",
    "core_isl_hotspot_specific",
}
traffic_mode_selections = traffic_modes + ["all"]
default_traffic_mode_selection = "core_hotspot_specific"

lohi_management_modes = [
    "legacy",
    "control_plane_only",
    "strict_physical_waypoint",
]
default_lohi_management_mode = "legacy"

backpressure_algorithm = "algorithm_backpressure_over_isls"
backpressure_queue_sources = [
    "auto",
    "per_destination_bytes",
    "per_destination_packets",
    "node_total_bytes",
    "node_total_packets",
    "interface_bytes",
    "interface_packets",
    "interface_nonreturn_avg_bytes",
    "interface_nonreturn_min_bytes",
]
backpressure_fallback_policies = [
    "shortest_path",
    "no_route",
]
backpressure_loop_guard_modes = [
    "none",
    "immediate_reverse",
    "forward_progress_hop",
    "forward_progress_distance",
]
default_backpressure_queue_source = "auto"
default_backpressure_fallback = "shortest_path"
default_backpressure_loop_guard = "none"
default_backpressure_diagnostics = True
default_backpressure_diagnostics_sample_limit = 2000


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


def ground_station_info_by_node_id():
    path = os.path.join(satellite_network_dir(), "ground_stations.txt")
    result = {}
    with open(path, newline="") as f_in:
        for row in csv.reader(f_in):
            if not row:
                continue
            ground_station_id = int(row[0])
            node_id = satellite_count + ground_station_id
            result[node_id] = {
                "node_id": node_id,
                "ground_station_id": ground_station_id,
                "name": row[1],
                "latitude_degrees": float(row[2]),
                "longitude_degrees": float(row[3]),
            }
    return result


def validate_focus_pair(src_node_id, dst_node_id):
    src_node_id = int(src_node_id)
    dst_node_id = int(dst_node_id)
    valid_min = min(endpoint_node_ids)
    valid_max = max(endpoint_node_ids)
    if src_node_id == dst_node_id:
        raise ValueError(
            "Focus source and destination must differ "
            "(got src_node_id=%d, dst_node_id=%d)."
            % (src_node_id, dst_node_id)
        )
    invalid = [
        node_id
        for node_id in (src_node_id, dst_node_id)
        if node_id not in endpoint_node_ids
    ]
    if invalid:
        raise ValueError(
            "Focus node IDs must be OneWeb top-100 ground-station node IDs "
            "in the inclusive range %d-%d; invalid value(s): %s."
            % (
                valid_min,
                valid_max,
                ", ".join(str(node_id) for node_id in invalid),
            )
        )
    return src_node_id, dst_node_id


def validate_focus_pair_arguments(parser, args):
    try:
        validate_focus_pair(args.src_node_id, args.dst_node_id)
    except ValueError as exc:
        parser.error(str(exc))


def focus_pair_tag_for(src_node_id, dst_node_id):
    src_node_id, dst_node_id = validate_focus_pair(src_node_id, dst_node_id)
    return "src%d_dst%d" % (src_node_id, dst_node_id)


def focus_pair_metadata(src_node_id, dst_node_id):
    src_node_id, dst_node_id = validate_focus_pair(src_node_id, dst_node_id)
    ground_stations = ground_station_info_by_node_id()
    return {
        "focus_src_node_id": src_node_id,
        "focus_dst_node_id": dst_node_id,
        "focus_src_name_if_available": ground_stations.get(src_node_id, {}).get(
            "name",
            "",
        ),
        "focus_dst_name_if_available": ground_stations.get(dst_node_id, {}).get(
            "name",
            "",
        ),
        "focus_pair_tag": focus_pair_tag_for(src_node_id, dst_node_id),
        "focus_flow_direction_count": 2,
    }


def load_level_to_tag(load_level):
    return ("%.3gx" % float(load_level)).replace(".", "p")


def capacity_to_tag(capacity_mbps):
    return ("%.6g" % float(capacity_mbps)).replace(".", "p")


def capacity_identity_tag(isl_capacity_mbps, gsl_capacity_mbps):
    return "isl%smbps_gsl%smbps" % (
        capacity_to_tag(isl_capacity_mbps),
        capacity_to_tag(gsl_capacity_mbps),
    )


def normalize_backpressure_queue_source(value=None):
    source = str(value or default_backpressure_queue_source).strip().lower()
    if source not in backpressure_queue_sources:
        raise ValueError(
            "Invalid Backpressure queue source '%s'. Expected one of: %s"
            % (value, ", ".join(backpressure_queue_sources))
        )
    return source


def normalize_backpressure_fallback(value=None):
    fallback = str(value or default_backpressure_fallback).strip().lower()
    if fallback not in backpressure_fallback_policies:
        raise ValueError(
            "Invalid Backpressure fallback '%s'. Expected one of: %s"
            % (value, ", ".join(backpressure_fallback_policies))
        )
    return fallback


def normalize_backpressure_loop_guard(value=None):
    mode = str(value or default_backpressure_loop_guard).strip().lower()
    if mode not in backpressure_loop_guard_modes:
        raise ValueError(
            "Invalid Backpressure loop guard '%s'. Expected one of: %s"
            % (value, ", ".join(backpressure_loop_guard_modes))
        )
    return mode


def backpressure_queue_source_tag(value):
    aliases = {
        "auto": "qauto",
        "per_destination_bytes": "qpdbytes",
        "per_destination_packets": "qpdpkts",
        "node_total_bytes": "qnodebytes",
        "node_total_packets": "qnodepkts",
        "interface_bytes": "qifbytes",
        "interface_packets": "qifpkts",
        "interface_nonreturn_avg_bytes": "qifnavgbytes",
        "interface_nonreturn_min_bytes": "qifnminbytes",
    }
    return aliases[normalize_backpressure_queue_source(value)]


def backpressure_fallback_tag(value):
    aliases = {
        "shortest_path": "fbsp",
        "no_route": "fbnone",
    }
    return aliases[normalize_backpressure_fallback(value)]


def backpressure_loop_guard_tag(value):
    aliases = {
        "none": "lgnone",
        "immediate_reverse": "lgimrev",
        "forward_progress_hop": "lgfwphop",
        "forward_progress_distance": "lgfpdist",
    }
    return aliases[normalize_backpressure_loop_guard(value)]


def backpressure_identity_tag(queue_source, fallback, loop_guard=default_backpressure_loop_guard):
    return "bp_%s_%s_%s" % (
        backpressure_queue_source_tag(queue_source),
        backpressure_fallback_tag(fallback),
        backpressure_loop_guard_tag(loop_guard),
    )


def algorithms_include_backpressure(algorithms):
    return backpressure_algorithm in normalize_algorithms(algorithms)


def seconds_to_tag(seconds):
    return ("%.9g" % float(seconds)).replace(".", "p")


def timing_identity_tag(simulation_end_s, traffic_stop_s):
    return "sim%ss_stop%ss" % (
        seconds_to_tag(simulation_end_s),
        seconds_to_tag(traffic_stop_s),
    )


def uses_default_capacities(run):
    return (
        float(
            run.get(
                "isl_data_rate_megabit_per_s",
                default_isl_data_rate_megabit_per_s,
            )
        )
        == default_isl_data_rate_megabit_per_s
        and float(
            run.get(
                "gsl_data_rate_megabit_per_s",
                default_gsl_data_rate_megabit_per_s,
            )
        )
        == default_gsl_data_rate_megabit_per_s
    )


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


def parse_background_flow_counts(values):
    if values is None:
        return [default_background_flow_count]
    if isinstance(values, int):
        values = [values]
    elif isinstance(values, str):
        values = [values]

    result = []
    for value in values:
        if str(value).lower() == "sweep":
            result.extend(default_background_flow_count_sweep)
            continue
        count = int(value)
        if count < 0:
            raise ValueError("Background flow count must be non-negative: %s" % value)
        result.append(count)

    deduped = []
    seen = set()
    for item in result:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
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


def normalize_lohi_management_mode(value=None):
    mode = str(value or default_lohi_management_mode).strip().lower().replace("-", "_")
    aliases = {
        "control_plane": "control_plane_only",
        "strict": "strict_physical_waypoint",
        "strict_waypoint": "strict_physical_waypoint",
    }
    mode = aliases.get(mode, mode)
    if mode not in lohi_management_modes:
        raise ValueError(
            "Invalid LoHi management mode '%s'. Expected one of: %s"
            % (value, ", ".join(lohi_management_modes))
        )
    return mode


def lohi_management_mode_tag(mode):
    mode = normalize_lohi_management_mode(mode)
    if mode == "strict_physical_waypoint":
        return "lohi_mgmt_strict_waypoint"
    return "lohi_mgmt_%s" % mode


def seconds_to_ns(seconds):
    return int(round(float(seconds) * 1000 * 1000 * 1000))


def add_traffic_mode_argument(parser):
    parser.add_argument(
        "--traffic-mode",
        choices=traffic_mode_selections,
        default=None,
        help=(
            "Traffic mode to use: focus_only, core_hotspot_specific, "
            "core_isl_hotspot_specific, random_general, or all. Default: %s"
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


def add_focus_pair_arguments(parser):
    parser.add_argument(
        "--src-node-id",
        type=int,
        default=focus_src_node_id,
        help=(
            "Focus-flow source ground-station node ID. The reciprocal direction "
            "is generated automatically. Default: %d"
        ) % focus_src_node_id,
    )
    parser.add_argument(
        "--dst-node-id",
        type=int,
        default=focus_dst_node_id,
        help=(
            "Focus-flow destination ground-station node ID. The reciprocal "
            "direction is generated automatically. Default: %d"
        ) % focus_dst_node_id,
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
        "--isl-data-rate-megabit-per-s",
        type=float,
        default=None,
        help=(
            "Override ISL capacity in Mbit/s. This also defines the load-level "
            "reference scale. Default: %.1f"
        ) % default_isl_data_rate_megabit_per_s,
    )
    parser.add_argument(
        "--gsl-data-rate-megabit-per-s",
        type=float,
        default=None,
        help=(
            "Override GSL/access capacity in Mbit/s. Default: %.1f"
        ) % default_gsl_data_rate_megabit_per_s,
    )
    parser.add_argument(
        "--background-flow-count",
        nargs="+",
        default=None,
        help=(
            "One or more background-flow counts for core_hotspot_specific "
            "and core_isl_hotspot_specific. Use 'sweep' for %s. Default: %d"
        ) % (
            default_background_flow_count_sweep,
            default_background_flow_count,
        ),
    )
    parser.add_argument(
        "--per-flow-rate-reference-background-flow-count",
        type=int,
        default=None,
        help=(
            "Background-flow count used to compute the fixed per-flow UDP "
            "rate in background-flow sweeps. Default: %d"
        ) % default_per_flow_rate_reference_background_flow_count,
    )
    parser.add_argument(
        "--random-flow-count",
        type=int,
        default=None,
        help="Override number of flows for random_general.",
    )
    parser.add_argument(
        "--endpoint-load-cap-ratio",
        type=float,
        default=None,
        help=(
            "Maximum selected source/destination endpoint offered load as a "
            "fraction of GSL capacity for core_isl_hotspot_specific. "
            "Default: %.2f"
        ) % default_endpoint_load_cap_ratio,
    )
    parser.add_argument(
        "--max-background-flows-per-dst",
        type=int,
        default=None,
        help=(
            "Maximum selected background flows per destination for "
            "core_isl_hotspot_specific. Use 0 to disable. Default: %d"
        ) % default_max_background_flows_per_dst,
    )
    parser.add_argument(
        "--max-background-flows-per-src",
        type=int,
        default=None,
        help=(
            "Maximum selected background flows per source for "
            "core_isl_hotspot_specific. Use 0 to disable. Default: %d"
        ) % default_max_background_flows_per_src,
    )
    parser.add_argument(
        "--satellite-interface-load-cap-ratio",
        type=float,
        default=None,
        help=(
            "Maximum estimated source/destination satellite-interface load "
            "as a fraction of GSL capacity for core_isl_hotspot_specific. "
            "Use 0 to disable. Default: %.2f"
        ) % default_satellite_interface_load_cap_ratio,
    )
    parser.add_argument(
        "--min-middle-isl-overlap-score",
        type=int,
        default=None,
        help=(
            "Minimum effective directed/undirected middle-ISL corridor overlap "
            "score required in strict core_isl_hotspot_specific selection. "
            "Default: %d"
        ) % default_min_middle_isl_overlap_score,
    )
    parser.add_argument(
        "--min-reachable-overlap-samples",
        type=int,
        default=None,
        help=(
            "Minimum reachable samples with middle-ISL corridor overlap required "
            "in strict core_isl_hotspot_specific selection. Default: %d"
        ) % default_min_reachable_overlap_samples,
    )
    parser.add_argument(
        "--min-overlap-ratio",
        type=float,
        default=None,
        help=(
            "Minimum effective middle-corridor overlap ratio required in strict "
            "core_isl_hotspot_specific selection. Default: %.3f"
        ) % default_min_overlap_ratio,
    )
    parser.add_argument(
        "--selection-sample-horizon-s",
        type=float,
        default=None,
        help=(
            "Fixed time horizon used to sample baseline paths for "
            "core_isl_hotspot_specific flow selection. This keeps selected "
            "flows stable across different simulation durations. Default: %.1f"
        ) % default_selection_sample_horizon_s,
    )
    parser.add_argument(
        "--selection-sample-times-s",
        nargs="+",
        default=None,
        help=(
            "Explicit baseline path sample times in seconds for "
            "core_isl_hotspot_specific. Overrides --selection-sample-horizon-s."
        ),
    )


def add_backpressure_arguments(parser):
    parser.add_argument(
        "--backpressure-queue-source",
        choices=backpressure_queue_sources,
        default=default_backpressure_queue_source,
        help=(
            "Queue source for algorithm_backpressure_over_isls. The current "
            "UDP/PDR pipeline exposes link/interface queues, so auto resolves "
            "to a node-total proxy when available. Default: %s"
        ) % default_backpressure_queue_source,
    )
    parser.add_argument(
        "--backpressure-fallback",
        choices=backpressure_fallback_policies,
        default=default_backpressure_fallback,
        help=(
            "Fallback when no positive queue differential is available. "
            "Default: %s"
        ) % default_backpressure_fallback,
    )
    parser.add_argument(
        "--backpressure-loop-guard",
        choices=backpressure_loop_guard_modes,
        default=default_backpressure_loop_guard,
        help=(
            "Restricted-route / loop-suppression mode for "
            "algorithm_backpressure_over_isls. This filters legal candidates "
            "without adding hop or distance to the queue differential weight. "
            "Default: %s"
        ) % default_backpressure_loop_guard,
    )
    diagnostics_group = parser.add_mutually_exclusive_group()
    diagnostics_group.add_argument(
        "--backpressure-diagnostics",
        dest="backpressure_diagnostics",
        action="store_true",
        help="Write Backpressure decision, fallback, queue-source, path-stretch, and loop diagnostics.",
    )
    diagnostics_group.add_argument(
        "--no-backpressure-diagnostics",
        dest="backpressure_diagnostics",
        action="store_false",
        help="Skip Backpressure diagnostics.",
    )
    parser.set_defaults(backpressure_diagnostics=default_backpressure_diagnostics)
    parser.add_argument(
        "--backpressure-diagnostics-sample-limit",
        type=int,
        default=default_backpressure_diagnostics_sample_limit,
        help=(
            "Maximum selected-decision rows to append per routing snapshot. "
            "Diagnostic focus-path decisions are prioritized. Default: %d"
        ) % default_backpressure_diagnostics_sample_limit,
    )


def add_common_run_arguments(parser):
    add_traffic_mode_argument(parser)
    add_load_level_argument(parser)
    add_algorithms_argument(parser)
    add_focus_pair_arguments(parser)
    add_runtime_override_arguments(parser)
    add_backpressure_arguments(parser)
    parser.add_argument(
        "--lohi-management-mode",
        choices=lohi_management_modes,
        default=default_lohi_management_mode,
        help=(
            "LoHi management-satellite behavior. strict_physical_waypoint "
            "currently fails closed because the NS-3 arbiter has no waypoint "
            "phase. Default: %s"
        ) % default_lohi_management_mode,
    )


def add_analysis_output_arguments(parser):
    parser.add_argument(
        "--output-layout",
        choices=["standard", "flat"],
        default="standard",
        help=(
            "Packet-delivery output layout. 'standard' writes core/, "
            "diagnostics/, and legacy/. Default: standard"
        ),
    )
    diagnostics_group = parser.add_mutually_exclusive_group()
    diagnostics_group.add_argument(
        "--write-full-diagnostics",
        dest="write_full_diagnostics",
        action="store_true",
        help="Write detailed diagnostic CSVs. This is the default.",
    )
    diagnostics_group.add_argument(
        "--no-write-full-diagnostics",
        dest="write_full_diagnostics",
        action="store_false",
        help="Skip large per-flow/path diagnostic CSVs.",
    )
    parser.set_defaults(write_full_diagnostics=True)
    parser.add_argument(
        "--write-legacy-outputs",
        action="store_true",
        help="Generate deprecated v1/v2 compatibility CSVs and plots.",
    )
    parser.add_argument(
        "--write-full-queue-saturation-timeline",
        action="store_true",
        help=(
            "Write every queue-history row. Disabled by default because this "
            "file can be multiple gigabytes."
        ),
    )
    rtt_group = parser.add_mutually_exclusive_group()
    rtt_group.add_argument(
        "--enable-rtt-analysis",
        dest="enable_rtt_analysis",
        action="store_true",
        help="Generate focus-flow estimated RTT CSVs and comparison plots.",
    )
    rtt_group.add_argument(
        "--no-rtt-analysis",
        dest="enable_rtt_analysis",
        action="store_false",
        help="Skip focus-flow estimated RTT analysis.",
    )
    parser.set_defaults(enable_rtt_analysis=True)
    parser.add_argument(
        "--rtt-sample-interval-s",
        type=float,
        default=0.1,
        help=(
            "Estimated RTT sample interval in seconds. The traffic stop time "
            "is also sampled. Default: 0.1 (100 ms)"
        ),
    )
    parser.add_argument(
        "--rtt-sample-times",
        default=None,
        help=(
            "Comma-separated explicit RTT sample times in seconds. Overrides "
            "--rtt-sample-interval-s."
        ),
    )
    parser.add_argument(
        "--enable-route-visualization",
        action="store_true",
        help="Generate focus forward, reverse, and round-trip route PNGs.",
    )
    parser.add_argument(
        "--route-plot-times",
        default="0,30,58",
        help="Comma-separated route plot times in seconds. Default: 0,30,58",
    )
    parser.add_argument(
        "--route-plot-variants",
        choices=[
            "all",
            "both",
            "original",
            "world_map",
            "world_map_zoomed",
        ],
        default="all",
        help=(
            "Route figure variants to generate. `all` writes the original, "
            "full world-map, and zoomed world-map views. `both` is the legacy "
            "alias for original plus full world map. Default: all"
        ),
    )


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


def legacy_run_name_for(traffic_mode, load_level, background_flow_count=None):
    bg_tag = ""
    if background_flow_count is not None:
        bg_tag = "_bg_flow_count_%d" % int(background_flow_count)
    return "run_%s_load_%s%s_oneweb_isls_moving_udp_pdr" % (
        traffic_mode,
        load_level_to_tag(load_level),
        bg_tag,
    )


def run_name_for(
    traffic_mode,
    load_level,
    background_flow_count=None,
    src_node_id=focus_src_node_id,
    dst_node_id=focus_dst_node_id,
    lohi_management_mode=None,
    isl_data_rate_megabit_per_s=default_isl_data_rate_megabit_per_s,
    gsl_data_rate_megabit_per_s=default_gsl_data_rate_megabit_per_s,
    simulation_end_s=None,
    traffic_stop_s=None,
    extra_identity_tag=None,
):
    bg_tag = ""
    if background_flow_count is not None:
        bg_tag = "_bg_flow_count_%d" % int(background_flow_count)
    management_tag = ""
    if lohi_management_mode is not None:
        management_tag = "_%s" % lohi_management_mode_tag(lohi_management_mode)
    timing_tag = ""
    if simulation_end_s is not None and traffic_stop_s is not None:
        timing_tag = "_%s" % timing_identity_tag(
            simulation_end_s,
            traffic_stop_s,
        )
    capacity_tag = ""
    if (
        float(isl_data_rate_megabit_per_s)
        != default_isl_data_rate_megabit_per_s
        or float(gsl_data_rate_megabit_per_s)
        != default_gsl_data_rate_megabit_per_s
    ):
        capacity_tag = "_%s" % capacity_identity_tag(
            isl_data_rate_megabit_per_s,
            gsl_data_rate_megabit_per_s,
        )
    identity_tag = ""
    if extra_identity_tag:
        identity_tag = "_%s" % str(extra_identity_tag)
    return "run_%s_%s_load_%s%s%s%s%s%s_oneweb_isls_moving_udp_pdr" % (
        traffic_mode,
        focus_pair_tag_for(src_node_id, dst_node_id),
        load_level_to_tag(load_level),
        bg_tag,
        timing_tag,
        capacity_tag,
        management_tag,
        identity_tag,
    )


def _existing_run_timing_matches(run_dir, run):
    expected = (
        float(run["simulation_end_time_s"]),
        float(run["traffic_stop_time_s"]),
    )
    try:
        algorithm_names = os.listdir(run_dir)
    except OSError:
        return False
    for algorithm_name in algorithm_names:
        metadata_path = os.path.join(
            run_dir,
            algorithm_name,
            "run_metadata.json",
        )
        if not os.path.isfile(metadata_path):
            continue
        try:
            with open(metadata_path) as f_in:
                metadata = json.load(f_in)
            actual = (
                float(metadata["simulation_end_time_s"]),
                float(metadata["traffic_stop_time_s"]),
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        return all(abs(a - b) < 1e-9 for a, b in zip(actual, expected))
    return False


def resolve_existing_run(run, runs_root="runs"):
    if os.path.isdir(os.path.join(runs_root, run["name"])):
        return run
    if run.get("backpressure_run_identity_tag"):
        return run
    pre_timing_dir = os.path.join(runs_root, run["pre_timing_name"])
    if (
        os.path.isdir(pre_timing_dir)
        and _existing_run_timing_matches(pre_timing_dir, run)
    ):
        resolved = dict(run)
        resolved["requested_name"] = run["name"]
        resolved["name"] = run["pre_timing_name"]
        resolved["using_pre_timing_run_name"] = True
        return resolved
    if (
        run.get("lohi_management_mode") == "legacy"
        and uses_default_capacities(run)
        and os.path.isdir(os.path.join(runs_root, run["pre_management_name"]))
        and _existing_run_timing_matches(
            os.path.join(runs_root, run["pre_management_name"]),
            run,
        )
    ):
        resolved = dict(run)
        resolved["requested_name"] = run["name"]
        resolved["name"] = run["pre_management_name"]
        resolved["using_pre_management_run_name"] = True
        return resolved
    if (
        run.get("lohi_management_mode") == "legacy"
        and uses_default_capacities(run)
        and
        run["src_node_id"] == focus_src_node_id
        and run["dst_node_id"] == focus_dst_node_id
        and os.path.isdir(os.path.join(runs_root, run["legacy_name"]))
        and _existing_run_timing_matches(
            os.path.join(runs_root, run["legacy_name"]),
            run,
        )
    ):
        resolved = dict(run)
        resolved["requested_name"] = run["name"]
        resolved["name"] = run["legacy_name"]
        resolved["using_legacy_run_name"] = True
        return resolved
    return run


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
    endpoint_load_cap_ratio_override=None,
    max_background_flows_per_dst_override=None,
    max_background_flows_per_src_override=None,
    per_flow_rate_reference_background_flow_count_override=None,
    satellite_interface_load_cap_ratio_override=None,
    min_middle_isl_overlap_score_override=None,
    min_reachable_overlap_samples_override=None,
    min_overlap_ratio_override=None,
    selection_sample_horizon_s_override=None,
    selection_sample_times_s_override=None,
    src_node_id_override=focus_src_node_id,
    dst_node_id_override=focus_dst_node_id,
    lohi_management_mode_override=default_lohi_management_mode,
    isl_data_rate_megabit_per_s_override=None,
    gsl_data_rate_megabit_per_s_override=None,
    backpressure_queue_source_override=default_backpressure_queue_source,
    backpressure_fallback_override=default_backpressure_fallback,
    backpressure_loop_guard_override=default_backpressure_loop_guard,
    backpressure_diagnostics_override=default_backpressure_diagnostics,
    backpressure_diagnostics_sample_limit_override=(
        default_backpressure_diagnostics_sample_limit
    ),
):
    load_levels = parse_load_levels(load_levels)
    algorithms = normalize_algorithms(algorithms)
    backpressure_queue_source = normalize_backpressure_queue_source(
        backpressure_queue_source_override
    )
    backpressure_fallback = normalize_backpressure_fallback(
        backpressure_fallback_override
    )
    backpressure_loop_guard = normalize_backpressure_loop_guard(
        backpressure_loop_guard_override
    )
    backpressure_diagnostics = bool(backpressure_diagnostics_override)
    backpressure_diagnostics_sample_limit = int(
        backpressure_diagnostics_sample_limit_override
    )
    if backpressure_diagnostics_sample_limit < 0:
        raise ValueError("backpressure_diagnostics_sample_limit must be non-negative")
    bp_identity_tag = (
        backpressure_identity_tag(
            backpressure_queue_source,
            backpressure_fallback,
            backpressure_loop_guard,
        )
        if algorithms_include_backpressure(algorithms)
        else None
    )
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
    isl_data_rate_mbps = (
        default_isl_data_rate_megabit_per_s
        if isl_data_rate_megabit_per_s_override is None
        else float(isl_data_rate_megabit_per_s_override)
    )
    gsl_data_rate_mbps = (
        default_gsl_data_rate_megabit_per_s
        if gsl_data_rate_megabit_per_s_override is None
        else float(gsl_data_rate_megabit_per_s_override)
    )
    background_flow_counts = parse_background_flow_counts(background_flow_count_override)
    random_flow_count = (
        default_random_flow_count
        if random_flow_count_override is None
        else int(random_flow_count_override)
    )
    per_flow_rate_reference_background_flow_count = (
        default_per_flow_rate_reference_background_flow_count
        if per_flow_rate_reference_background_flow_count_override is None
        else int(per_flow_rate_reference_background_flow_count_override)
    )
    endpoint_load_cap_ratio = (
        default_endpoint_load_cap_ratio
        if endpoint_load_cap_ratio_override is None
        else float(endpoint_load_cap_ratio_override)
    )
    max_background_flows_per_dst = (
        default_max_background_flows_per_dst
        if max_background_flows_per_dst_override is None
        else int(max_background_flows_per_dst_override)
    )
    max_background_flows_per_src = (
        default_max_background_flows_per_src
        if max_background_flows_per_src_override is None
        else int(max_background_flows_per_src_override)
    )
    satellite_interface_load_cap_ratio = (
        default_satellite_interface_load_cap_ratio
        if satellite_interface_load_cap_ratio_override is None
        else float(satellite_interface_load_cap_ratio_override)
    )
    min_middle_isl_overlap_score = (
        default_min_middle_isl_overlap_score
        if min_middle_isl_overlap_score_override is None
        else int(min_middle_isl_overlap_score_override)
    )
    min_reachable_overlap_samples = (
        default_min_reachable_overlap_samples
        if min_reachable_overlap_samples_override is None
        else int(min_reachable_overlap_samples_override)
    )
    min_overlap_ratio = (
        default_min_overlap_ratio
        if min_overlap_ratio_override is None
        else float(min_overlap_ratio_override)
    )
    selection_sample_horizon_s = (
        default_selection_sample_horizon_s
        if selection_sample_horizon_s_override is None
        else float(selection_sample_horizon_s_override)
    )
    selection_sample_times_s = None
    if selection_sample_times_s_override is not None:
        selection_sample_times_s = [
            float(value)
            for value in selection_sample_times_s_override
        ]
    src_node_id, dst_node_id = validate_focus_pair(
        src_node_id_override,
        dst_node_id_override,
    )
    focus_metadata = focus_pair_metadata(src_node_id, dst_node_id)
    lohi_management_mode = normalize_lohi_management_mode(
        lohi_management_mode_override
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
    if isl_data_rate_mbps <= 0:
        raise ValueError("isl_data_rate_megabit_per_s must be positive")
    if gsl_data_rate_mbps <= 0:
        raise ValueError("gsl_data_rate_megabit_per_s must be positive")
    if random_flow_count <= 0:
        raise ValueError("random_flow_count must be positive")
    if per_flow_rate_reference_background_flow_count < 0:
        raise ValueError(
            "per_flow_rate_reference_background_flow_count must be non-negative"
        )
    if endpoint_load_cap_ratio <= 0:
        raise ValueError("endpoint_load_cap_ratio must be positive")
    if max_background_flows_per_dst < 0:
        raise ValueError("max_background_flows_per_dst must be non-negative")
    if max_background_flows_per_src < 0:
        raise ValueError("max_background_flows_per_src must be non-negative")
    if satellite_interface_load_cap_ratio < 0:
        raise ValueError("satellite_interface_load_cap_ratio must be non-negative")
    if min_middle_isl_overlap_score < 0:
        raise ValueError("min_middle_isl_overlap_score must be non-negative")
    if min_reachable_overlap_samples < 0:
        raise ValueError("min_reachable_overlap_samples must be non-negative")
    if min_overlap_ratio < 0:
        raise ValueError("min_overlap_ratio must be non-negative")
    if selection_sample_horizon_s <= 0:
        raise ValueError("selection_sample_horizon_s must be positive")
    if selection_sample_times_s is not None:
        if len(selection_sample_times_s) == 0:
            raise ValueError("selection_sample_times_s must not be empty")
        for value in selection_sample_times_s:
            if value < 0:
                raise ValueError("selection_sample_times_s must be non-negative")

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
        mode_background_flow_counts = (
            background_flow_counts
            if traffic_mode in background_flow_traffic_modes
            else [background_flow_counts[0]]
        )
        for background_flow_count in mode_background_flow_counts:
            name_background_flow_count = (
                background_flow_count
                if traffic_mode in background_flow_traffic_modes
                else None
            )
            for load_level in load_levels:
                for algorithm in algorithms:
                    legacy_name = legacy_run_name_for(
                        traffic_mode,
                        load_level,
                        name_background_flow_count,
                    )
                    pre_management_name = run_name_for(
                        traffic_mode,
                        load_level,
                        name_background_flow_count,
                        src_node_id,
                        dst_node_id,
                        None,
                        isl_data_rate_mbps,
                        gsl_data_rate_mbps,
                        None,
                        None,
                        bp_identity_tag,
                    )
                    pre_timing_name = run_name_for(
                        traffic_mode,
                        load_level,
                        name_background_flow_count,
                        src_node_id,
                        dst_node_id,
                        lohi_management_mode,
                        isl_data_rate_mbps,
                        gsl_data_rate_mbps,
                        None,
                        None,
                        bp_identity_tag,
                    )
                    run_list.append({
                        "name": run_name_for(
                            traffic_mode,
                            load_level,
                            name_background_flow_count,
                            src_node_id,
                            dst_node_id,
                            lohi_management_mode,
                            isl_data_rate_mbps,
                            gsl_data_rate_mbps,
                            sim_end_s,
                            traffic_stop_s,
                            bp_identity_tag,
                        ),
                        "legacy_name": legacy_name,
                        "pre_management_name": pre_management_name,
                        "pre_timing_name": pre_timing_name,
                        "lohi_management_mode": lohi_management_mode,
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
                        "data_rate_megabit_per_s": isl_data_rate_mbps,
                        "isl_data_rate_megabit_per_s": isl_data_rate_mbps,
                        "gsl_data_rate_megabit_per_s": gsl_data_rate_mbps,
                        "queue_size_pkt": queue_pkts,
                        "load_level": float(load_level),
                        "background_flow_count": background_flow_count,
                        "per_flow_rate_reference_background_flow_count": (
                            per_flow_rate_reference_background_flow_count
                        ),
                        "random_flow_count": random_flow_count,
                        "endpoint_load_cap_ratio": endpoint_load_cap_ratio,
                        "max_background_flows_per_dst": max_background_flows_per_dst,
                        "max_background_flows_per_src": max_background_flows_per_src,
                        "satellite_interface_load_cap_ratio": (
                            satellite_interface_load_cap_ratio
                        ),
                        "min_middle_isl_overlap_score": min_middle_isl_overlap_score,
                        "min_reachable_overlap_samples": (
                            min_reachable_overlap_samples
                        ),
                        "min_overlap_ratio": min_overlap_ratio,
                        "selection_sample_horizon_s": selection_sample_horizon_s,
                        "selection_sample_times_s": selection_sample_times_s,
                        "enable_isl_utilization_tracking": enable_isl_utilization_tracking,
                        "isl_utilization_tracking_interval_ns": isl_utilization_tracking_interval_ns,
                        "enable_link_queue_tracking": enable_link_queue_tracking,
                        "enable_physical_link_drop_tracking": enable_physical_link_drop_tracking,
                        "backpressure_queue_source": backpressure_queue_source,
                        "backpressure_fallback": backpressure_fallback,
                        "backpressure_loop_guard": backpressure_loop_guard,
                        "backpressure_forward_progress_metric": (
                            "hop"
                            if backpressure_loop_guard == "forward_progress_hop"
                            else (
                                "distance"
                                if backpressure_loop_guard == "forward_progress_distance"
                                else "none"
                            )
                        ),
                        "backpressure_diagnostics": backpressure_diagnostics,
                        "backpressure_diagnostics_sample_limit": (
                            backpressure_diagnostics_sample_limit
                        ),
                        "backpressure_commodity_mode": "destination_proxy",
                        "backpressure_capacity_multiplier_enabled": True,
                        "backpressure_is_full_multi_commodity": False,
                        "backpressure_is_restricted_route": (
                            backpressure_loop_guard != "none"
                        ),
                        "backpressure_run_identity_tag": bp_identity_tag or "",
                        "src_node_id": src_node_id,
                        "dst_node_id": dst_node_id,
                        **focus_metadata,
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
    add_analysis_output_arguments(parser)
    return parser
