import json
import os
import random
import shutil
import sys
import tempfile
from collections import defaultdict

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-udp-pdr")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

sys.path.append(os.path.join(os.path.dirname(__file__)))
from dynamic_run_list import (
    add_force_and_dry_run_arguments,
    build_arg_parser,
    describe_selection,
    endpoint_node_ids,
    focus_dst_node_id,
    focus_src_node_id,
    get_udp_pdr_run_list,
    satellite_count,
    satellite_network_dir,
)


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
SATGENPY_DIR = os.path.join(REPO_ROOT, "satgenpy")


def _replace_many(text, mapping):
    for key, value in mapping.items():
        text = text.replace(key, str(value))
    return text


def _write_text(path, text):
    with open(path, "w") as f_out:
        f_out.write(text)


def _load_template():
    template_path = os.path.join(
        os.path.dirname(__file__),
        "templates",
        "template_config_ns3.properties",
    )
    with open(template_path) as f_in:
        return f_in.read()


def _render_config(run, udp_logging_ids):
    if udp_logging_ids:
        logging_set = "set(%s)" % ",".join(str(i) for i in udp_logging_ids)
    else:
        logging_set = "set()"

    interval_line = ""
    if run["enable_isl_utilization_tracking"]:
        interval_line = (
            "isl_utilization_tracking_interval_ns=%d"
            % run["isl_utilization_tracking_interval_ns"]
        )

    return _replace_many(
        _load_template(),
        {
            "[SIMULATION-END-TIME-NS]": run["simulation_end_time_ns"],
            "[TRAFFIC-STOP-TIME-NS]": run["traffic_stop_time_ns"],
            "[DRAIN-TIME-NS]": run["drain_time_ns"],
            "[SATELLITE-NETWORK]": run["satellite_network"],
            "[DYNAMIC-STATE]": run["dynamic_state"],
            "[DYNAMIC-STATE-ALGORITHM]": run["dynamic_state_algorithm"],
            "[DYNAMIC-STATE-UPDATE-INTERVAL-NS]": run[
                "dynamic_state_update_interval_ns"
            ],
            "[ISL-DATA-RATE-MEGABIT-PER-S]": run["data_rate_megabit_per_s"],
            "[GSL-DATA-RATE-MEGABIT-PER-S]": run["data_rate_megabit_per_s"],
            "[ISL-MAX-QUEUE-SIZE-PKTS]": run["queue_size_pkt"],
            "[GSL-MAX-QUEUE-SIZE-PKTS]": run["queue_size_pkt"],
            "[ENABLE-ISL-UTILIZATION-TRACKING]": (
                "true" if run["enable_isl_utilization_tracking"] else "false"
            ),
            "[ISL-UTILIZATION-TRACKING-INTERVAL-NS-COMPLETE]": interval_line,
            "[ENABLE-LINK-QUEUE-TRACKING]": (
                "true" if run["enable_link_queue_tracking"] else "false"
            ),
            "[UDP-BURST-LOGGING-SET]": logging_set,
        },
    )


def _directed_edges(path):
    if path is None:
        return []
    return list(zip(path[:-1], path[1:]))


def _satellite_middle_edges(path):
    if path is None or len(path) < 4:
        return set()
    first_last_sats = {path[1], path[-2]}
    middle = set()
    for a, b in _directed_edges(path):
        if a < satellite_count and b < satellite_count:
            if a not in first_last_sats and b not in first_last_sats:
                middle.add((a, b))
    return middle


def _first_last_sats(path):
    if path is None or len(path) < 3:
        return set()
    return {path[1], path[-2]}


def _read_fstate_delta(path, accumulated):
    if not os.path.exists(path):
        return accumulated
    with open(path) as f_in:
        for line in f_in:
            parts = line.strip().split(",")
            if len(parts) < 3:
                continue
            accumulated[(int(parts[0]), int(parts[1]))] = int(parts[2])
    return accumulated


def _compute_baseline_snapshots(run, sample_count):
    if sample_count <= 0:
        sample_count = 1
    sys.path.append(SATGENPY_DIR)
    from satgen.dynamic_state.generate_dynamic_state import generate_dynamic_state_at
    from satgen.ground_stations import read_ground_stations_extended
    from satgen.interfaces import read_gsl_interfaces_info
    from satgen.isls import read_isls
    from satgen.tles import read_tles

    sat_net_dir = satellite_network_dir()
    ground_stations = read_ground_stations_extended(
        os.path.join(sat_net_dir, "ground_stations.txt")
    )
    tles = read_tles(os.path.join(sat_net_dir, "tles.txt"))
    satellites = tles["satellites"]
    epoch = tles["epoch"]
    list_isls = read_isls(os.path.join(sat_net_dir, "isls.txt"), len(satellites))
    list_gsl_interfaces_info = read_gsl_interfaces_info(
        os.path.join(sat_net_dir, "gsl_interfaces_info.txt"),
        len(satellites),
        len(ground_stations),
    )
    with open(os.path.join(sat_net_dir, "description.txt")) as f_in:
        lines = f_in.readlines()
    max_gsl_length_m = float(lines[0].split("=")[1].strip())
    max_isl_length_m = float(lines[1].split("=")[1].strip())

    sim_end = run["simulation_end_time_ns"]
    if sample_count == 1:
        sample_times = [0]
    else:
        span = max(sim_end - run["dynamic_state_update_interval_ns"], 0)
        sample_times = sorted(
            set(int(round(span * i / float(sample_count - 1))) for i in range(sample_count))
        )
        update_interval = run["dynamic_state_update_interval_ns"]
        sample_times = [
            int((t // update_interval) * update_interval) for t in sample_times
        ]

    snapshots = []
    accumulated = {}
    prev_output = None
    with tempfile.TemporaryDirectory() as tmp_dir:
        for time_ns in sample_times:
            prev_output = generate_dynamic_state_at(
                tmp_dir,
                epoch,
                time_ns,
                satellites,
                ground_stations,
                list_isls,
                list_gsl_interfaces_info,
                max_gsl_length_m,
                max_isl_length_m,
                "algorithm_free_one_only_over_isls",
                prev_output,
                False,
                None,
                None,
                None,
                0.7,
                0.3,
                run["dynamic_state_update_interval_ns"],
            )
            _read_fstate_delta(os.path.join(tmp_dir, "fstate_%d.txt" % time_ns), accumulated)
            snapshots.append((time_ns, dict(accumulated)))
    return snapshots


def _generate_focus_only_pairs(run):
    return [
        {
            "src": run["src_node_id"],
            "dst": run["dst_node_id"],
            "class": "focus",
            "score": "",
        },
        {
            "src": run["dst_node_id"],
            "dst": run["src_node_id"],
            "class": "focus",
            "score": "",
        },
    ]


def _generate_random_general_pairs(run):
    random.seed(123456789)
    candidates = [
        (src, dst)
        for src in endpoint_node_ids
        for dst in endpoint_node_ids
        if src != dst
    ]
    random.shuffle(candidates)
    selected = candidates[: run["random_flow_count"]]
    pairs = []
    for src, dst in selected:
        flow_class = (
            "focus"
            if (src, dst)
            in {
                (focus_src_node_id, focus_dst_node_id),
                (focus_dst_node_id, focus_src_node_id),
            }
            else "background"
        )
        pairs.append({"src": src, "dst": dst, "class": flow_class, "score": ""})
    if not any(p["class"] == "focus" for p in pairs):
        pairs = _generate_focus_only_pairs(run) + pairs
    return pairs


def _generate_core_hotspot_pairs(run, sample_count):
    sys.path.append(SATGENPY_DIR)
    from satgen.post_analysis.graph_tools import get_path

    print("  > Selecting core-hotspot background flows from baseline paths...")
    snapshots = _compute_baseline_snapshots(run, sample_count)

    focus_edges_by_time = {}
    focus_conflict_sats_by_time = {}
    for time_ns, fstate in snapshots:
        path_a = get_path(run["src_node_id"], run["dst_node_id"], fstate)
        path_b = get_path(run["dst_node_id"], run["src_node_id"], fstate)
        focus_edges_by_time[time_ns] = (
            _satellite_middle_edges(path_a) | _satellite_middle_edges(path_b)
        )
        focus_conflict_sats_by_time[time_ns] = (
            _first_last_sats(path_a) | _first_last_sats(path_b)
        )

    candidate_scores = []
    focus_endpoint_set = {run["src_node_id"], run["dst_node_id"]}
    for src in endpoint_node_ids:
        for dst in endpoint_node_ids:
            if src == dst or src in focus_endpoint_set or dst in focus_endpoint_set:
                continue

            score = 0
            conflict = False
            reachable_samples = 0
            for time_ns, fstate in snapshots:
                path = get_path(src, dst, fstate)
                if path is None or len(path) < 4:
                    continue
                reachable_samples += 1
                if _first_last_sats(path) & focus_conflict_sats_by_time[time_ns]:
                    conflict = True
                    break
                score += len(set(_directed_edges(path)) & focus_edges_by_time[time_ns])

            if not conflict and reachable_samples > 0:
                candidate_scores.append((score, reachable_samples, src, dst))

    candidate_scores.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    selected = []
    used_pairs = set()
    for score, _, src, dst in candidate_scores:
        if len(selected) >= run["background_flow_count"]:
            break
        if (src, dst) in used_pairs:
            continue
        selected.append({"src": src, "dst": dst, "class": "background", "score": score})
        used_pairs.add((src, dst))

    if len(selected) < run["background_flow_count"]:
        print(
            "  > Warning: only %d hotspot candidates found; filling with random non-focus pairs"
            % len(selected)
        )
        random.seed(987654321)
        fallback = [
            (src, dst)
            for src in endpoint_node_ids
            for dst in endpoint_node_ids
            if src != dst
            and src not in focus_endpoint_set
            and dst not in focus_endpoint_set
            and (src, dst) not in used_pairs
        ]
        random.shuffle(fallback)
        for src, dst in fallback:
            if len(selected) >= run["background_flow_count"]:
                break
            selected.append({"src": src, "dst": dst, "class": "background", "score": 0})
            used_pairs.add((src, dst))

    return _generate_focus_only_pairs(run) + selected


def generate_pairs(run, hotspot_sample_count):
    if run["traffic_mode"] == "focus_only":
        return _generate_focus_only_pairs(run)
    if run["traffic_mode"] == "core_hotspot_specific":
        return _generate_core_hotspot_pairs(run, hotspot_sample_count)
    if run["traffic_mode"] == "random_general":
        return _generate_random_general_pairs(run)
    raise ValueError("Unknown traffic mode: %s" % run["traffic_mode"])


def compute_per_flow_rate_mbps(run, pair_count):
    if pair_count <= 0:
        raise ValueError("Cannot compute rate for zero flows")
    aggregate_rate = run["load_level"] * run["data_rate_megabit_per_s"]
    return aggregate_rate / float(pair_count)


def write_udp_schedule(run_dir, run, pairs):
    per_flow_rate = compute_per_flow_rate_mbps(run, len(pairs))
    start_time_ns = 0
    duration_ns = run["traffic_stop_time_ns"] - start_time_ns
    if duration_ns < 0:
        raise ValueError(
            "UDP traffic duration must be non-negative (traffic_stop_time_ns=%d, start_time_ns=%d)"
            % (run["traffic_stop_time_ns"], start_time_ns)
        )
    schedule_path = os.path.join(run_dir, "udp_burst_schedule.csv")
    with open(schedule_path, "w") as f_out:
        for idx, pair in enumerate(pairs):
            metadata_items = [
                "class=%s" % pair["class"],
                "traffic_mode=%s" % run["traffic_mode"],
                "load_level=%.3f" % run["load_level"],
                "traffic_stop_time_ns=%d" % run["traffic_stop_time_ns"],
                "drain_time_ns=%d" % run["drain_time_ns"],
            ]
            if pair.get("score") != "":
                metadata_items.append("hotspot_score=%s" % pair["score"])
            metadata = "|".join(metadata_items)
            f_out.write(
                "%d,%d,%d,%.10f,%d,%d,,%s\n"
                % (
                    idx,
                    pair["src"],
                    pair["dst"],
                    per_flow_rate,
                    start_time_ns,
                    duration_ns,
                    metadata,
                )
            )
    return schedule_path, per_flow_rate


def write_run_metadata(run_dir, run, pairs, per_flow_rate):
    by_class = defaultdict(int)
    for pair in pairs:
        by_class[pair["class"]] += 1
    metadata = {
        "run": run,
        "flow_count": len(pairs),
        "flow_count_by_class": dict(by_class),
        "per_flow_rate_mbps": per_flow_rate,
        "aggregate_offered_rate_mbps": per_flow_rate * len(pairs),
        "simulation_end_time_s": run["simulation_end_time_s"],
        "traffic_stop_time_s": run["traffic_stop_time_s"],
        "drain_time_s": run["drain_time_s"],
        "simulation_end_time_ns": run["simulation_end_time_ns"],
        "traffic_stop_time_ns": run["traffic_stop_time_ns"],
        "drain_time_ns": run["drain_time_ns"],
        "drain_time_enabled": run["drain_time_enabled"],
        "pairs": pairs,
        "notes": [
            "UDP/PDR experiment generated outside paper/lohi_replication/traffic_matrix.",
            "core_hotspot_specific uses baseline shortest-path middle-ISL overlap heuristic.",
            "UDP packets are generated only until traffic_stop_time_s; NS-3 continues until simulation_end_time_s to drain in-flight packets.",
        ],
    }
    _write_text(
        os.path.join(run_dir, "run_metadata.json"),
        json.dumps(metadata, indent=2, sort_keys=True),
    )


def prepare_run_dir(run_dir, force):
    if os.path.exists(run_dir):
        if not force:
            raise RuntimeError(
                "Run directory already exists: %s. Use --force to regenerate only this udp_pdr run."
                % run_dir
            )
        shutil.rmtree(run_dir)
    os.makedirs(run_dir)
    for subdir in ["logs_ns3", "dynamic_state", "queue_stats", "prev_output_cache"]:
        os.makedirs(os.path.join(run_dir, subdir))
    _write_text(
        os.path.join(run_dir, ".gitignore"),
        "logs_ns3\ndynamic_state\nqueue_stats\nprev_output_cache\n",
    )


def main():
    parser = build_arg_parser("Generate UDP/PDR dynamic-routing run directories.")
    add_force_and_dry_run_arguments(parser)
    parser.add_argument(
        "--hotspot-sample-count",
        type=int,
        default=3,
        help="Number of baseline time samples used for core-hotspot selection.",
    )
    args = parser.parse_args()

    selected_mode, modes, load_levels, algorithms = describe_selection(args)
    print("Traffic mode selection: %s (%s)" % (selected_mode, ", ".join(modes)))
    print("Load levels: %s" % ", ".join("%.3f" % x for x in load_levels))
    print("Algorithms: %s" % ", ".join(algorithms))

    runs = get_udp_pdr_run_list(
        selected_mode,
        load_levels,
        algorithms,
        args.simulation_end_time_s,
        args.traffic_stop_time_s,
        args.dynamic_state_update_interval_ms,
        args.queue_size_pkt,
        args.background_flow_count,
        args.random_flow_count,
    )

    generated_pairs_by_run_name = {}
    for run in runs:
        run_dir = os.path.join("runs", run["name"], run["dynamic_state_algorithm"])
        print("\nPlanned run: %s" % run_dir)
        print(
            "  simulation_end=%.6fs, traffic_stop=%.6fs, drain=%.6fs"
            % (
                run["simulation_end_time_s"],
                run["traffic_stop_time_s"],
                run["drain_time_s"],
            )
        )
        if args.dry_run:
            continue

        pair_key = (
            run["name"],
            run["traffic_mode"],
            run["load_level"],
            run["simulation_end_time_ns"],
            run["traffic_stop_time_ns"],
            run["background_flow_count"],
            run["random_flow_count"],
        )
        if pair_key not in generated_pairs_by_run_name:
            generated_pairs_by_run_name[pair_key] = generate_pairs(
                run,
                args.hotspot_sample_count,
            )
        pairs = generated_pairs_by_run_name[pair_key]

        prepare_run_dir(run_dir, args.force)
        udp_logging_ids = list(range(min(run["packet_trace_flow_count"], len(pairs))))
        _write_text(
            os.path.join(run_dir, "config_ns3.properties"),
            _render_config(run, udp_logging_ids),
        )
        schedule_path, per_flow_rate = write_udp_schedule(run_dir, run, pairs)
        write_run_metadata(run_dir, run, pairs, per_flow_rate)
        print(
            "Generated run: %s (%d flows, %.6f Mbps/flow, schedule=%s)"
            % (run_dir, len(pairs), per_flow_rate, schedule_path)
        )

    print("\nSuccess")


if __name__ == "__main__":
    main()
