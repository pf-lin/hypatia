import csv
import hashlib
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
    background_flow_traffic_modes,
    build_arg_parser,
    describe_selection,
    endpoint_node_ids,
    get_udp_pdr_run_list,
    satellite_count,
    satellite_network_dir,
    validate_focus_pair_arguments,
)


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
SATGENPY_DIR = os.path.join(REPO_ROOT, "satgenpy")

SELECTION_DIAGNOSTIC_FILENAMES = [
    "flow_selection_diagnostics.csv",
    "corridor_overlap_summary.csv",
    "gsl_load_by_endpoint.csv",
    "isl_corridor_load_summary.csv",
    "fallback_phase_summary.csv",
    "corridor_concentration_summary.csv",
    "satellite_interface_load_summary.csv",
]


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
            "[LOHI-MANAGEMENT-MODE]": run["lohi_management_mode"],
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
            "[ENABLE-PHYSICAL-LINK-DROP-TRACKING]": (
                "true" if run["enable_physical_link_drop_tracking"] else "false"
            ),
            "[UDP-BURST-LOGGING-SET]": logging_set,
            "[FOCUS-SRC-NODE-ID]": run["src_node_id"],
            "[FOCUS-DST-NODE-ID]": run["dst_node_id"],
            "[FOCUS-SRC-NAME]": run["focus_src_name_if_available"],
            "[FOCUS-DST-NAME]": run["focus_dst_name_if_available"],
            "[FOCUS-PAIR-TAG]": run["focus_pair_tag"],
            "[FOCUS-FLOW-DIRECTION-COUNT]": run["focus_flow_direction_count"],
        },
    )


def _directed_edges(path):
    if path is None:
        return []
    return list(zip(path[:-1], path[1:]))


def _undirected_edge(edge):
    a, b = edge
    return (a, b) if a <= b else (b, a)


def _undirected_edges(edges):
    return set(_undirected_edge(edge) for edge in edges)


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


def _first_sat(path):
    if path is None or len(path) < 3:
        return None
    return path[1]


def _last_sat(path):
    if path is None or len(path) < 3:
        return None
    return path[-2]


def _satellite_interface_keys_for_path(path):
    keys = set()
    first_sat = _first_sat(path)
    last_sat = _last_sat(path)
    if first_sat is not None:
        keys.add((first_sat, "source"))
    if last_sat is not None:
        keys.add((last_sat, "destination"))
    return keys


def _primary_satellite_interface_keys(src_satellite_counts, dst_satellite_counts):
    keys = set()
    if src_satellite_counts:
        max_count = max(src_satellite_counts.values())
        satellite_id = min(
            satellite_id
            for satellite_id, count in src_satellite_counts.items()
            if count == max_count
        )
        keys.add((satellite_id, "source"))
    if dst_satellite_counts:
        max_count = max(dst_satellite_counts.values())
        satellite_id = min(
            satellite_id
            for satellite_id, count in dst_satellite_counts.items()
            if count == max_count
        )
        keys.add((satellite_id, "destination"))
    return keys


def _format_satellite_interface_keys(keys):
    return ";".join(
        "%d:%s" % (satellite_id, direction)
        for satellite_id, direction in sorted(keys)
    )


def _format_bool(value):
    return "true" if bool(value) else "false"


def _format_edges(edges):
    return ";".join("%d->%d" % (a, b) for a, b in sorted(edges))


def _format_timestamps(timestamps):
    return ";".join(str(int(value)) for value in timestamps)


def _json_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


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

    explicit_sample_times_s = run.get("selection_sample_times_s")
    update_interval = run["dynamic_state_update_interval_ns"]
    if explicit_sample_times_s is not None:
        sample_times = [
            int(round(float(value) * 1000 * 1000 * 1000))
            for value in explicit_sample_times_s
        ]
        sample_times = [
            int((time_ns // update_interval) * update_interval)
            for time_ns in sample_times
        ]
        sample_times = sorted(set(sample_times))
    elif sample_count == 1:
        sample_times = [0]
    else:
        selection_horizon_ns = int(
            round(float(run.get("selection_sample_horizon_s", 60.0)) * 1000 * 1000 * 1000)
        )
        span = max(selection_horizon_ns - update_interval, 0)
        sample_times = sorted(
            set(int(round(span * i / float(sample_count - 1))) for i in range(sample_count))
        )
        sample_times = [
            int((t // update_interval) * update_interval) for t in sample_times
        ]
    if not sample_times:
        sample_times = [0]

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
                (run["src_node_id"], run["dst_node_id"]),
                (run["dst_node_id"], run["src_node_id"]),
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


def _evaluate_core_isl_hotspot_candidates(run, sample_count):
    sys.path.append(SATGENPY_DIR)
    from satgen.post_analysis.graph_tools import get_path

    print("  > Selecting core-ISL hotspot background flows from baseline paths...")
    snapshots = _compute_baseline_snapshots(run, sample_count)
    sampled_timestamps = [time_ns for time_ns, _ in snapshots]

    focus_edges_by_time = {}
    focus_undirected_edges_by_time = {}
    focus_conflict_sats_by_time = {}
    focus_middle_edges_by_pair = {
        (run["src_node_id"], run["dst_node_id"]): set(),
        (run["dst_node_id"], run["src_node_id"]): set(),
    }
    focus_satellite_interfaces_by_pair = {
        (run["src_node_id"], run["dst_node_id"]): set(),
        (run["dst_node_id"], run["src_node_id"]): set(),
    }
    focus_satellite_interface_counts_by_pair = {
        (run["src_node_id"], run["dst_node_id"]): {
            "source": defaultdict(int),
            "destination": defaultdict(int),
        },
        (run["dst_node_id"], run["src_node_id"]): {
            "source": defaultdict(int),
            "destination": defaultdict(int),
        },
    }
    focus_middle_edges_union = set()
    focus_middle_undirected_edges_union = set()
    for time_ns, fstate in snapshots:
        path_a = get_path(run["src_node_id"], run["dst_node_id"], fstate)
        path_b = get_path(run["dst_node_id"], run["src_node_id"], fstate)
        path_a_middle = _satellite_middle_edges(path_a)
        path_b_middle = _satellite_middle_edges(path_b)
        focus_edges = path_a_middle | path_b_middle
        focus_undirected_edges = _undirected_edges(focus_edges)
        focus_edges_by_time[time_ns] = focus_edges
        focus_undirected_edges_by_time[time_ns] = focus_undirected_edges
        focus_conflict_sats_by_time[time_ns] = (
            _first_last_sats(path_a) | _first_last_sats(path_b)
        )
        focus_middle_edges_by_pair[(run["src_node_id"], run["dst_node_id"])].update(
            path_a_middle
        )
        focus_middle_edges_by_pair[(run["dst_node_id"], run["src_node_id"])].update(
            path_b_middle
        )
        for pair_key, path in [
            ((run["src_node_id"], run["dst_node_id"]), path_a),
            ((run["dst_node_id"], run["src_node_id"]), path_b),
        ]:
            first_sat = _first_sat(path)
            last_sat = _last_sat(path)
            if first_sat is not None:
                focus_satellite_interface_counts_by_pair[pair_key]["source"][
                    first_sat
                ] += 1
            if last_sat is not None:
                focus_satellite_interface_counts_by_pair[pair_key]["destination"][
                    last_sat
                ] += 1
        focus_middle_edges_union.update(focus_edges)
        focus_middle_undirected_edges_union.update(focus_undirected_edges)

    for pair_key, counts in focus_satellite_interface_counts_by_pair.items():
        focus_satellite_interfaces_by_pair[pair_key] = _primary_satellite_interface_keys(
            counts["source"],
            counts["destination"],
        )

    candidates = []
    focus_endpoint_set = {run["src_node_id"], run["dst_node_id"]}
    for src in endpoint_node_ids:
        for dst in endpoint_node_ids:
            if src == dst or src in focus_endpoint_set or dst in focus_endpoint_set:
                continue

            reachable_samples = 0
            samples_with_overlap = 0
            directed_overlap_score = 0
            undirected_overlap_score = 0
            candidate_middle_edge_sample_count = 0
            first_hop_conflict = False
            last_hop_conflict = False
            shared_edges = set()
            shared_undirected_edges = set()
            candidate_middle_edges = set()
            src_satellite_ids = set()
            dst_satellite_ids = set()
            satellite_interface_keys = set()
            src_satellite_counts = defaultdict(int)
            dst_satellite_counts = defaultdict(int)
            reachable_timestamps = []

            for time_ns, fstate in snapshots:
                path = get_path(src, dst, fstate)
                if path is None or len(path) < 4:
                    continue
                reachable_samples += 1
                reachable_timestamps.append(time_ns)

                focus_conflict_sats = focus_conflict_sats_by_time[time_ns]
                if _first_sat(path) in focus_conflict_sats:
                    first_hop_conflict = True
                if _last_sat(path) in focus_conflict_sats:
                    last_hop_conflict = True

                middle_edges = _satellite_middle_edges(path)
                candidate_undirected_edges = _undirected_edges(middle_edges)
                directed_overlap_edges = middle_edges & focus_edges_by_time[time_ns]
                undirected_overlap_edges = (
                    candidate_undirected_edges & focus_undirected_edges_by_time[time_ns]
                )
                target_corridor_edges = set(
                    edge
                    for edge in middle_edges
                    if edge in focus_edges_by_time[time_ns]
                    or _undirected_edge(edge) in focus_undirected_edges_by_time[time_ns]
                )
                if directed_overlap_edges or undirected_overlap_edges:
                    samples_with_overlap += 1
                directed_overlap_score += len(directed_overlap_edges)
                undirected_overlap_score += len(undirected_overlap_edges)
                candidate_middle_edge_sample_count += len(middle_edges)
                shared_edges.update(target_corridor_edges)
                shared_undirected_edges.update(undirected_overlap_edges)
                candidate_middle_edges.update(middle_edges)
                first_sat = _first_sat(path)
                last_sat = _last_sat(path)
                if first_sat is not None:
                    src_satellite_ids.add(first_sat)
                    satellite_interface_keys.add((first_sat, "source"))
                    src_satellite_counts[first_sat] += 1
                if last_sat is not None:
                    dst_satellite_ids.add(last_sat)
                    satellite_interface_keys.add((last_sat, "destination"))
                    dst_satellite_counts[last_sat] += 1

            effective_overlap_score = max(
                directed_overlap_score,
                undirected_overlap_score,
            )
            overlap_ratio = (
                effective_overlap_score / float(candidate_middle_edge_sample_count)
                if candidate_middle_edge_sample_count > 0
                else 0.0
            )
            path_stability_score = reachable_samples + samples_with_overlap
            primary_satellite_interface_keys = _primary_satellite_interface_keys(
                src_satellite_counts,
                dst_satellite_counts,
            )
            candidates.append({
                "src": src,
                "dst": dst,
                "reachable_samples": reachable_samples,
                "samples_with_overlap": samples_with_overlap,
                "sampled_timestamps": list(sampled_timestamps),
                "reachable_timestamps": reachable_timestamps,
                "middle_isl_overlap_score": effective_overlap_score,
                "directed_overlap_score": directed_overlap_score,
                "undirected_overlap_score": undirected_overlap_score,
                "effective_overlap_score": effective_overlap_score,
                "middle_isl_edge_sample_count": candidate_middle_edge_sample_count,
                "overlap_ratio": overlap_ratio,
                "path_stability_score": path_stability_score,
                "first_hop_conflict": first_hop_conflict,
                "last_hop_conflict": last_hop_conflict,
                "edge_conflict": first_hop_conflict or last_hop_conflict,
                "shared_edges": shared_edges,
                "shared_undirected_edges": shared_undirected_edges,
                "candidate_middle_edges": candidate_middle_edges,
                "non_focus_middle_edges": candidate_middle_edges - shared_edges,
                "focus_middle_edges_count": len(focus_middle_edges_union),
                "focus_middle_undirected_edges_count": (
                    len(focus_middle_undirected_edges_union)
                ),
                "candidate_middle_edges_count": len(candidate_middle_edges),
                "src_satellite_ids": src_satellite_ids,
                "dst_satellite_ids": dst_satellite_ids,
                "satellite_interface_keys": primary_satellite_interface_keys,
                "sampled_satellite_interface_keys": satellite_interface_keys,
                "selected": False,
                "selection_rank": "",
                "selection_phase": "",
                "selected_phase": "",
                "fallback_phase": "",
                "fallback_reason": "",
                "relaxed_constraints": "",
                "selection_score": "",
                "corridor_concentration_score": 0,
                "candidate_rank_before_fallback": "",
                "candidate_rank_after_fallback": "",
            })

    return {
        "sampled_timestamps": sampled_timestamps,
        "focus_middle_edges_union": focus_middle_edges_union,
        "focus_middle_undirected_edges_union": focus_middle_undirected_edges_union,
        "focus_middle_edges_by_pair": focus_middle_edges_by_pair,
        "focus_satellite_interfaces_by_pair": focus_satellite_interfaces_by_pair,
        "candidates": candidates,
    }


def _candidate_effective_overlap_score(candidate):
    return float(candidate.get("effective_overlap_score", 0))


def _candidate_corridor_concentration_score(candidate, selected_undirected_edge_counts):
    return sum(
        selected_undirected_edge_counts[edge]
        for edge in candidate["shared_undirected_edges"]
    )


def _candidate_added_target_load_mbps(candidate, per_flow_rate):
    return per_flow_rate * float(len(candidate["shared_edges"]))


def _candidate_added_non_focus_load_mbps(candidate, per_flow_rate):
    return per_flow_rate * float(len(candidate["non_focus_middle_edges"]))


def _candidate_selection_score(candidate, selected_edge_counts):
    return _candidate_selection_score_with_rate(candidate, selected_edge_counts, 0.0)


def _candidate_selection_score_with_rate(candidate, selected_edge_counts, per_flow_rate):
    corridor_score = _candidate_corridor_concentration_score(
        candidate,
        selected_edge_counts,
    )
    added_target_load = _candidate_added_target_load_mbps(candidate, per_flow_rate)
    added_non_focus_load = _candidate_added_non_focus_load_mbps(candidate, per_flow_rate)
    return (
        4.0 * _candidate_effective_overlap_score(candidate)
        + 2.0 * float(corridor_score)
        + 0.5 * added_target_load
        + 0.1 * float(candidate["path_stability_score"])
        - 0.15 * added_non_focus_load
    )


def _max_endpoint_count_allows(current_count, max_count):
    return max_count == 0 or current_count < max_count


def _candidate_meets_overlap_thresholds(candidate, phase):
    if not phase["require_overlap"]:
        return True
    if _candidate_effective_overlap_score(candidate) < phase["min_overlap_score"]:
        return False
    if candidate["samples_with_overlap"] < phase["min_overlap_samples"]:
        return False
    if candidate["overlap_ratio"] + 1e-12 < phase["min_overlap_ratio"]:
        return False
    return True


def _candidate_feasible_for_phase(
    candidate,
    phase,
    per_flow_rate,
    src_load_mbps,
    dst_load_mbps,
    satellite_interface_load_mbps,
    background_src_counts,
    background_dst_counts,
    max_background_flows_per_src,
    max_background_flows_per_dst,
):
    if phase["avoid_edge_conflict"] and candidate["edge_conflict"]:
        return False
    if phase["require_reachable"] and candidate["reachable_samples"] <= 0:
        return False
    if not _candidate_meets_overlap_thresholds(candidate, phase):
        return False

    if phase["enforce_endpoint_flow_limits"]:
        if not _max_endpoint_count_allows(
            background_src_counts[candidate["src"]],
            max_background_flows_per_src,
        ):
            return False
        if not _max_endpoint_count_allows(
            background_dst_counts[candidate["dst"]],
            max_background_flows_per_dst,
        ):
            return False

    endpoint_cap_mbps = phase["endpoint_cap_mbps"]
    if endpoint_cap_mbps is not None:
        epsilon = 1e-9
        if src_load_mbps[candidate["src"]] + per_flow_rate > endpoint_cap_mbps + epsilon:
            return False
        if dst_load_mbps[candidate["dst"]] + per_flow_rate > endpoint_cap_mbps + epsilon:
            return False

    satellite_interface_cap_mbps = phase["satellite_interface_cap_mbps"]
    if satellite_interface_cap_mbps is not None:
        epsilon = 1e-9
        for key in candidate["satellite_interface_keys"]:
            if (
                satellite_interface_load_mbps[key] + per_flow_rate
                > satellite_interface_cap_mbps + epsilon
            ):
                return False

    return True


def _phase(
    name,
    require_overlap,
    avoid_edge_conflict,
    enforce_endpoint_flow_limits,
    endpoint_cap_mbps,
    satellite_interface_cap_mbps,
    min_overlap_score,
    min_overlap_samples,
    min_overlap_ratio,
    relaxed_constraints,
    fallback_reason,
):
    return {
        "name": name,
        "require_reachable": True,
        "require_overlap": require_overlap,
        "avoid_edge_conflict": avoid_edge_conflict,
        "enforce_endpoint_flow_limits": enforce_endpoint_flow_limits,
        "endpoint_cap_mbps": endpoint_cap_mbps,
        "satellite_interface_cap_mbps": satellite_interface_cap_mbps,
        "min_overlap_score": min_overlap_score,
        "min_overlap_samples": min_overlap_samples,
        "min_overlap_ratio": min_overlap_ratio,
        "relaxed_constraints": relaxed_constraints,
        "fallback_reason": fallback_reason,
    }


def _select_core_isl_hotspot_candidates(run, context):
    target_count = run["background_flow_count"]
    if target_count <= 0:
        return [], []

    expected_pair_count = len(_generate_focus_only_pairs(run)) + target_count
    per_flow_rate = compute_per_flow_rate_mbps(run, expected_pair_count)
    gsl_capacity_mbps = run["data_rate_megabit_per_s"]
    endpoint_cap_mbps = run["endpoint_load_cap_ratio"] * gsl_capacity_mbps
    relaxed_endpoint_cap_mbps = gsl_capacity_mbps
    satellite_interface_cap_mbps = None
    if run.get("satellite_interface_load_cap_ratio", 0.0) > 0:
        satellite_interface_cap_mbps = (
            run["satellite_interface_load_cap_ratio"] * gsl_capacity_mbps
        )
    relaxed_satellite_interface_cap_mbps = gsl_capacity_mbps
    max_per_src = run["max_background_flows_per_src"]
    max_per_dst = run["max_background_flows_per_dst"]
    min_overlap_score = run["min_middle_isl_overlap_score"]
    min_overlap_samples = run["min_reachable_overlap_samples"]
    min_overlap_ratio = run["min_overlap_ratio"]

    src_load_mbps = defaultdict(float)
    dst_load_mbps = defaultdict(float)
    satellite_interface_load_mbps = defaultdict(float)
    for pair in _generate_focus_only_pairs(run):
        src_load_mbps[pair["src"]] += per_flow_rate
        dst_load_mbps[pair["dst"]] += per_flow_rate
        for key in context["focus_satellite_interfaces_by_pair"].get(
            (pair["src"], pair["dst"]),
            set(),
        ):
            satellite_interface_load_mbps[key] += per_flow_rate

    phases = [
        _phase(
            "strict",
            True,
            True,
            True,
            endpoint_cap_mbps,
            satellite_interface_cap_mbps,
            min_overlap_score,
            min_overlap_samples,
            min_overlap_ratio,
            "",
            "strict_constraints_satisfied",
        ),
        _phase(
            "relax_per_src_dst_limit",
            True,
            True,
            False,
            endpoint_cap_mbps,
            satellite_interface_cap_mbps,
            min_overlap_score,
            min_overlap_samples,
            min_overlap_ratio,
            "per_src_dst_limit",
            "strict phase lacked enough candidates under per-src/per-dst limits",
        ),
        _phase(
            "relax_endpoint_cap",
            True,
            True,
            False,
            relaxed_endpoint_cap_mbps,
            relaxed_satellite_interface_cap_mbps,
            min_overlap_score,
            min_overlap_samples,
            min_overlap_ratio,
            "per_src_dst_limit;endpoint_cap_ratio_to_1.0;satellite_interface_cap_ratio_to_1.0",
            "overlap candidates required endpoint cap relaxation to GSL capacity",
        ),
        _phase(
            "relax_corridor_threshold",
            True,
            True,
            False,
            relaxed_endpoint_cap_mbps,
            relaxed_satellite_interface_cap_mbps,
            1,
            1,
            0.0,
            "per_src_dst_limit;endpoint_cap_ratio_to_1.0;satellite_interface_cap_ratio_to_1.0;corridor_threshold",
            "overlap candidates remained but did not meet strict overlap thresholds",
        ),
        _phase(
            "relax_edge_conflict",
            True,
            False,
            False,
            relaxed_endpoint_cap_mbps,
            relaxed_satellite_interface_cap_mbps,
            1,
            1,
            0.0,
            "per_src_dst_limit;endpoint_cap_ratio_to_1.0;satellite_interface_cap_ratio_to_1.0;edge_conflict",
            "overlap candidates required allowing focus first/last-satellite conflicts under GSL/interface caps",
        ),
        _phase(
            "fallback_allow_zero_overlap",
            False,
            True,
            False,
            relaxed_endpoint_cap_mbps,
            relaxed_satellite_interface_cap_mbps,
            0,
            0,
            0.0,
            "per_src_dst_limit;endpoint_cap_ratio_to_1.0;satellite_interface_cap_ratio_to_1.0;allow_zero_overlap",
            "nonzero-overlap candidates were insufficient under GSL/interface caps",
        ),
        _phase(
            "fallback_insufficient_candidates",
            False,
            False,
            False,
            None,
            None,
            0,
            0,
            0.0,
            "edge_conflict;endpoint_cap;satellite_interface_cap;allow_zero_overlap",
            "insufficient reachable candidates remained after all constrained phases",
        ),
    ]

    selected = []
    selected_pairs = set()
    selected_undirected_edge_counts = defaultdict(int)
    for edge in context["focus_middle_edges_union"]:
        selected_undirected_edge_counts[_undirected_edge(edge)] += 1
    background_src_counts = defaultdict(int)
    background_dst_counts = defaultdict(int)
    warnings = []
    phase_stats = {
        phase["name"]: {
            "candidate_count": 0,
            "selected_count": 0,
        }
        for phase in phases
    }

    initial_ranked = sorted(
        context["candidates"],
        key=lambda candidate: (
            -_candidate_selection_score_with_rate(
                candidate,
                selected_undirected_edge_counts,
                per_flow_rate,
            ),
            -_candidate_effective_overlap_score(candidate),
            -candidate["samples_with_overlap"],
            -candidate["reachable_samples"],
            candidate["src"],
            candidate["dst"],
        ),
    )
    for rank, candidate in enumerate(initial_ranked, start=1):
        candidate["candidate_rank_before_fallback"] = rank

    for phase in phases:
        phase_candidates = [
            candidate
            for candidate in context["candidates"]
            if (candidate["src"], candidate["dst"]) not in selected_pairs
            and _candidate_feasible_for_phase(
                candidate,
                phase,
                per_flow_rate,
                src_load_mbps,
                dst_load_mbps,
                satellite_interface_load_mbps,
                background_src_counts,
                background_dst_counts,
                max_per_src,
                max_per_dst,
            )
        ]
        phase_stats[phase["name"]]["candidate_count"] = len(phase_candidates)
        while len(selected) < target_count:
            feasible = []
            for candidate in context["candidates"]:
                pair = (candidate["src"], candidate["dst"])
                if pair in selected_pairs:
                    continue
                if not _candidate_feasible_for_phase(
                    candidate,
                    phase,
                    per_flow_rate,
                    src_load_mbps,
                    dst_load_mbps,
                    satellite_interface_load_mbps,
                    background_src_counts,
                    background_dst_counts,
                    max_per_src,
                    max_per_dst,
                ):
                    continue
                corridor_score = _candidate_corridor_concentration_score(
                    candidate,
                    selected_undirected_edge_counts,
                )
                score = _candidate_selection_score_with_rate(
                    candidate,
                    selected_undirected_edge_counts,
                    per_flow_rate,
                )
                feasible.append((
                    -score,
                    -_candidate_effective_overlap_score(candidate),
                    -corridor_score,
                    _candidate_added_non_focus_load_mbps(candidate, per_flow_rate),
                    -candidate["samples_with_overlap"],
                    -candidate["reachable_samples"],
                    candidate["src"],
                    candidate["dst"],
                    candidate,
                    score,
                    corridor_score,
                ))

            if not feasible:
                break

            feasible.sort()
            chosen = feasible[0][8]
            score = feasible[0][9]
            corridor_score = feasible[0][10]
            chosen["selected"] = True
            chosen["selection_rank"] = len(selected) + 1
            chosen["selection_phase"] = phase["name"]
            chosen["selected_phase"] = phase["name"]
            chosen["fallback_phase"] = "" if phase["name"] == "strict" else phase["name"]
            chosen["fallback_reason"] = phase["fallback_reason"]
            chosen["relaxed_constraints"] = phase["relaxed_constraints"]
            chosen["selection_score"] = score
            chosen["corridor_concentration_score"] = corridor_score

            selected.append(chosen)
            phase_stats[phase["name"]]["selected_count"] += 1
            selected_pairs.add((chosen["src"], chosen["dst"]))
            background_src_counts[chosen["src"]] += 1
            background_dst_counts[chosen["dst"]] += 1
            src_load_mbps[chosen["src"]] += per_flow_rate
            dst_load_mbps[chosen["dst"]] += per_flow_rate
            for key in chosen["satellite_interface_keys"]:
                satellite_interface_load_mbps[key] += per_flow_rate
            for edge in chosen["shared_undirected_edges"]:
                selected_undirected_edge_counts[edge] += 1

        if len(selected) >= target_count:
            break

    if len(selected) < target_count:
        warnings.append(
            "Only %d/%d non-edge-conflicting background candidates could be selected."
            % (len(selected), target_count)
        )
    fallback_phases = sorted(
        set(
            candidate["selection_phase"]
            for candidate in selected
            if candidate["selection_phase"] != "strict"
        )
    )
    for phase_name in fallback_phases:
        warnings.append("Selection used fallback phase: %s" % phase_name)

    final_ranked = sorted(
        context["candidates"],
        key=lambda candidate: (
            -_candidate_selection_score_with_rate(
                candidate,
                selected_undirected_edge_counts,
                per_flow_rate,
            ),
            -_candidate_effective_overlap_score(candidate),
            -candidate["samples_with_overlap"],
            -candidate["reachable_samples"],
            candidate["src"],
            candidate["dst"],
        ),
    )
    for rank, candidate in enumerate(final_ranked, start=1):
        candidate["candidate_rank_after_fallback"] = rank

    context["selection_phases"] = phases
    context["phase_stats"] = phase_stats

    return selected, warnings


def _core_isl_candidate_reject_reason(
    candidate,
    run,
    final_src_load,
    final_dst_load,
    final_satellite_interface_load,
):
    if candidate["selected"]:
        if candidate["selection_phase"] == "strict":
            return "selected"
        return "selected_%s" % candidate["selection_phase"]
    if candidate["edge_conflict"]:
        return "edge_conflict"
    if candidate["reachable_samples"] <= 0:
        return "unreachable"
    if _candidate_effective_overlap_score(candidate) <= 0:
        return "zero_middle_isl_overlap"
    if (
        _candidate_effective_overlap_score(candidate)
        < run["min_middle_isl_overlap_score"]
    ):
        return "below_min_middle_isl_overlap_score"
    if candidate["samples_with_overlap"] < run["min_reachable_overlap_samples"]:
        return "below_min_reachable_overlap_samples"
    if candidate["overlap_ratio"] + 1e-12 < run["min_overlap_ratio"]:
        return "below_min_overlap_ratio"

    max_per_src = run["max_background_flows_per_src"]
    max_per_dst = run["max_background_flows_per_dst"]
    selected_src_count = sum(
        1
        for value in final_src_load.get("_selected_background_srcs", [])
        if value == candidate["src"]
    )
    selected_dst_count = sum(
        1
        for value in final_dst_load.get("_selected_background_dsts", [])
        if value == candidate["dst"]
    )
    if max_per_src > 0 and selected_src_count >= max_per_src:
        return "max_background_flows_per_src"
    if max_per_dst > 0 and selected_dst_count >= max_per_dst:
        return "max_background_flows_per_dst"

    per_flow_rate = final_src_load["_per_flow_rate"]
    endpoint_cap_mbps = run["endpoint_load_cap_ratio"] * run["data_rate_megabit_per_s"]
    if final_src_load[candidate["src"]] + per_flow_rate > endpoint_cap_mbps + 1e-9:
        return "src_endpoint_load_cap"
    if final_dst_load[candidate["dst"]] + per_flow_rate > endpoint_cap_mbps + 1e-9:
        return "dst_endpoint_load_cap"
    satellite_interface_cap_ratio = run.get("satellite_interface_load_cap_ratio", 0.0)
    if satellite_interface_cap_ratio > 0:
        satellite_interface_cap_mbps = (
            satellite_interface_cap_ratio * run["data_rate_megabit_per_s"]
        )
        for key in candidate["satellite_interface_keys"]:
            if (
                final_satellite_interface_load.get(key, 0.0) + per_flow_rate
                > satellite_interface_cap_mbps + 1e-9
            ):
                return "satellite_interface_load_cap"
    return "not_selected_lower_score"


def _max_projected_satellite_interface_ratio(
    candidate,
    final_satellite_interface_load,
    per_flow_rate,
    gsl_capacity_mbps,
    direction,
    selected_flag,
):
    keys = [
        key
        for key in candidate["satellite_interface_keys"]
        if key[1] == direction
    ]
    if not keys or gsl_capacity_mbps <= 0:
        return 0.0
    ratios = []
    for key in keys:
        load = final_satellite_interface_load.get(key, 0.0)
        if not selected_flag:
            load += per_flow_rate
        ratios.append(load / gsl_capacity_mbps)
    return max(ratios) if ratios else 0.0


def _selection_input_hash(run, context):
    payload = {
        "traffic_mode": run["traffic_mode"],
        "load_level": run["load_level"],
        "background_flow_count": run["background_flow_count"],
        "per_flow_rate_reference_background_flow_count": (
            run["per_flow_rate_reference_background_flow_count"]
        ),
        "focus_pair": [run["src_node_id"], run["dst_node_id"]],
        "data_rate_megabit_per_s": run["data_rate_megabit_per_s"],
        "endpoint_load_cap_ratio": run["endpoint_load_cap_ratio"],
        "satellite_interface_load_cap_ratio": (
            run.get("satellite_interface_load_cap_ratio", 0.0)
        ),
        "max_background_flows_per_src": run["max_background_flows_per_src"],
        "max_background_flows_per_dst": run["max_background_flows_per_dst"],
        "min_middle_isl_overlap_score": run["min_middle_isl_overlap_score"],
        "min_reachable_overlap_samples": run["min_reachable_overlap_samples"],
        "min_overlap_ratio": run["min_overlap_ratio"],
        "dynamic_state_update_interval_ns": run["dynamic_state_update_interval_ns"],
        "selection_sample_horizon_s": run.get("selection_sample_horizon_s"),
        "selection_sample_times_s": run.get("selection_sample_times_s"),
        "sampled_timestamps": context["sampled_timestamps"],
        "focus_middle_edges": [
            [edge[0], edge[1]]
            for edge in sorted(context["focus_middle_edges_union"])
        ],
    }
    return _json_hash(payload)


def _flow_selection_hash(run, context, pairs):
    payload = {
        "selection_input_hash": context["selection_input_hash"],
        "pairs": [
            {
                "src": pair["src"],
                "dst": pair["dst"],
                "class": pair["class"],
                "selection_phase": pair.get("selection_phase", ""),
            }
            for pair in pairs
        ],
    }
    return _json_hash(payload)


def _build_core_isl_diagnostics(run, context, selected, warnings, pairs):
    per_flow_rate = compute_per_flow_rate_mbps(run, len(pairs))
    gsl_capacity_mbps = run["data_rate_megabit_per_s"]
    endpoint_cap_mbps = run["endpoint_load_cap_ratio"] * gsl_capacity_mbps
    satellite_interface_cap_mbps = (
        run.get("satellite_interface_load_cap_ratio", 0.0) * gsl_capacity_mbps
    )
    selection_input_hash = context.get("selection_input_hash", "")
    flow_selection_hash = context.get("flow_selection_hash", "")

    flow_ids = {
        (pair["src"], pair["dst"]): idx
        for idx, pair in enumerate(pairs)
    }
    selected_candidates_by_pair = {
        (candidate["src"], candidate["dst"]): candidate
        for candidate in selected
    }
    selected_background_srcs = [
        candidate["src"]
        for candidate in selected
    ]
    selected_background_dsts = [
        candidate["dst"]
        for candidate in selected
    ]

    final_src_load = defaultdict(float)
    final_dst_load = defaultdict(float)
    final_src_flow_ids = defaultdict(list)
    final_dst_flow_ids = defaultdict(list)
    final_satellite_interface_load = defaultdict(float)
    final_satellite_interface_flow_ids = defaultdict(list)
    for idx, pair in enumerate(pairs):
        final_src_load[pair["src"]] += per_flow_rate
        final_dst_load[pair["dst"]] += per_flow_rate
        final_src_flow_ids[pair["src"]].append(idx)
        final_dst_flow_ids[pair["dst"]].append(idx)
        pair_key = (pair["src"], pair["dst"])
        if pair["class"] == "focus":
            satellite_keys = context["focus_satellite_interfaces_by_pair"].get(
                pair_key,
                set(),
            )
        else:
            satellite_keys = selected_candidates_by_pair[pair_key][
                "satellite_interface_keys"
            ]
        for key in satellite_keys:
            final_satellite_interface_load[key] += per_flow_rate
            final_satellite_interface_flow_ids[key].append(idx)

    reject_src_load = defaultdict(float, final_src_load)
    reject_dst_load = defaultdict(float, final_dst_load)
    reject_satellite_interface_load = defaultdict(
        float,
        final_satellite_interface_load,
    )
    reject_src_load["_per_flow_rate"] = per_flow_rate
    reject_dst_load["_per_flow_rate"] = per_flow_rate
    reject_src_load["_selected_background_srcs"] = selected_background_srcs
    reject_dst_load["_selected_background_dsts"] = selected_background_dsts

    selection_rows = []
    for pair in pairs[:2]:
        src = pair["src"]
        dst = pair["dst"]
        satellite_keys = context["focus_satellite_interfaces_by_pair"].get(
            (src, dst),
            set(),
        )
        src_satellite_ratio = max(
            [
                final_satellite_interface_load[key] / gsl_capacity_mbps
                for key in satellite_keys
                if key[1] == "source"
            ]
            or [0.0]
        )
        dst_satellite_ratio = max(
            [
                final_satellite_interface_load[key] / gsl_capacity_mbps
                for key in satellite_keys
                if key[1] == "destination"
            ]
            or [0.0]
        )
        selection_rows.append({
            "flow_selection_hash": flow_selection_hash,
            "selection_input_hash": selection_input_hash,
            "flow_id": flow_ids[(src, dst)],
            "src": src,
            "dst": dst,
            "flow_class": "focus",
            "selected": "true",
            "selection_rank": 0,
            "selection_phase": "focus",
            "selected_phase": "focus",
            "fallback_phase": "",
            "fallback_reason": "selected_focus",
            "relaxed_constraints": "",
            "middle_isl_overlap_score": "",
            "directed_overlap_score": "",
            "undirected_overlap_score": "",
            "overlap_ratio": "",
            "reachable_samples": len(context["sampled_timestamps"]),
            "sampled_timestamps": _format_timestamps(context["sampled_timestamps"]),
            "first_hop_conflict": "false",
            "last_hop_conflict": "false",
            "satellite_interface_keys": _format_satellite_interface_keys(
                satellite_keys
            ),
            "adds_target_corridor_load_mbps": "",
            "adds_non_focus_edge_load_mbps": "",
            "src_endpoint_load_mbps_after_selection": final_src_load[src],
            "dst_endpoint_load_mbps_after_selection": final_dst_load[dst],
            "src_endpoint_load_ratio": final_src_load[src] / gsl_capacity_mbps,
            "dst_endpoint_load_ratio": final_dst_load[dst] / gsl_capacity_mbps,
            "src_endpoint_load_ratio_after": final_src_load[src] / gsl_capacity_mbps,
            "dst_endpoint_load_ratio_after": final_dst_load[dst] / gsl_capacity_mbps,
            "src_satellite_interface_load_ratio_after": src_satellite_ratio,
            "dst_satellite_interface_load_ratio_after": dst_satellite_ratio,
            "candidate_reject_reason": "selected_focus",
            "corridor_concentration_score": "",
            "path_stability_score": "",
            "selection_score": "",
            "candidate_rank_before_fallback": "",
            "candidate_rank_after_fallback": "",
        })

    for candidate in sorted(
        context["candidates"],
        key=lambda item: (
            not item["selected"],
            item["selection_rank"] if item["selection_rank"] != "" else 10**9,
            -item["middle_isl_overlap_score"],
            item["src"],
            item["dst"],
        ),
    ):
        src = candidate["src"]
        dst = candidate["dst"]
        selected_flag = bool(candidate["selected"])
        projected_src_load = final_src_load[src]
        projected_dst_load = final_dst_load[dst]
        if not selected_flag:
            projected_src_load += per_flow_rate
            projected_dst_load += per_flow_rate
        selection_rows.append({
            "flow_selection_hash": flow_selection_hash,
            "selection_input_hash": selection_input_hash,
            "flow_id": flow_ids.get((src, dst), ""),
            "src": src,
            "dst": dst,
            "flow_class": "background",
            "selected": _format_bool(selected_flag),
            "selection_rank": candidate["selection_rank"],
            "selection_phase": candidate["selection_phase"],
            "selected_phase": candidate["selected_phase"],
            "fallback_phase": candidate["fallback_phase"],
            "fallback_reason": candidate["fallback_reason"],
            "relaxed_constraints": candidate["relaxed_constraints"],
            "middle_isl_overlap_score": candidate["middle_isl_overlap_score"],
            "directed_overlap_score": candidate["directed_overlap_score"],
            "undirected_overlap_score": candidate["undirected_overlap_score"],
            "overlap_ratio": candidate["overlap_ratio"],
            "reachable_samples": candidate["reachable_samples"],
            "sampled_timestamps": _format_timestamps(candidate["sampled_timestamps"]),
            "first_hop_conflict": _format_bool(candidate["first_hop_conflict"]),
            "last_hop_conflict": _format_bool(candidate["last_hop_conflict"]),
            "satellite_interface_keys": _format_satellite_interface_keys(
                candidate["satellite_interface_keys"]
            ),
            "adds_target_corridor_load_mbps": _candidate_added_target_load_mbps(
                candidate,
                per_flow_rate,
            ),
            "adds_non_focus_edge_load_mbps": _candidate_added_non_focus_load_mbps(
                candidate,
                per_flow_rate,
            ),
            "src_endpoint_load_mbps_after_selection": projected_src_load,
            "dst_endpoint_load_mbps_after_selection": projected_dst_load,
            "src_endpoint_load_ratio": projected_src_load / gsl_capacity_mbps,
            "dst_endpoint_load_ratio": projected_dst_load / gsl_capacity_mbps,
            "src_endpoint_load_ratio_after": projected_src_load / gsl_capacity_mbps,
            "dst_endpoint_load_ratio_after": projected_dst_load / gsl_capacity_mbps,
            "src_satellite_interface_load_ratio_after": (
                _max_projected_satellite_interface_ratio(
                    candidate,
                    final_satellite_interface_load,
                    per_flow_rate,
                    gsl_capacity_mbps,
                    "source",
                    selected_flag,
                )
            ),
            "dst_satellite_interface_load_ratio_after": (
                _max_projected_satellite_interface_ratio(
                    candidate,
                    final_satellite_interface_load,
                    per_flow_rate,
                    gsl_capacity_mbps,
                    "destination",
                    selected_flag,
                )
            ),
            "candidate_reject_reason": _core_isl_candidate_reject_reason(
                candidate,
                run,
                reject_src_load,
                reject_dst_load,
                reject_satellite_interface_load,
            ),
            "corridor_concentration_score": candidate[
                "corridor_concentration_score"
            ],
            "path_stability_score": candidate["path_stability_score"],
            "selection_score": candidate["selection_score"],
            "candidate_rank_before_fallback": candidate[
                "candidate_rank_before_fallback"
            ],
            "candidate_rank_after_fallback": candidate[
                "candidate_rank_after_fallback"
            ],
        })

    overlap_rows = []
    for candidate in sorted(
        context["candidates"],
        key=lambda item: (
            not item["selected"],
            item["selection_rank"] if item["selection_rank"] != "" else 10**9,
            -item["middle_isl_overlap_score"],
            item["src"],
            item["dst"],
        ),
    ):
        overlap_rows.append({
            "flow_selection_hash": flow_selection_hash,
            "selection_input_hash": selection_input_hash,
            "src": candidate["src"],
            "dst": candidate["dst"],
            "selected": _format_bool(candidate["selected"]),
            "selection_rank": candidate["selection_rank"],
            "overlap_edges_count": len(candidate["shared_edges"]),
            "overlap_score": candidate["middle_isl_overlap_score"],
            "directed_overlap_score": candidate["directed_overlap_score"],
            "undirected_overlap_score": candidate["undirected_overlap_score"],
            "overlap_ratio": candidate["overlap_ratio"],
            "samples_with_overlap": candidate["samples_with_overlap"],
            "sampled_timestamp_count": candidate["reachable_samples"],
            "focus_middle_edges_count": candidate["focus_middle_edges_count"],
            "focus_middle_undirected_edges_count": candidate[
                "focus_middle_undirected_edges_count"
            ],
            "candidate_middle_edges_count": candidate["candidate_middle_edges_count"],
            "shared_edges": _format_edges(candidate["shared_edges"]),
            "shared_undirected_edges": _format_edges(
                candidate["shared_undirected_edges"]
            ),
            "non_focus_middle_edges": _format_edges(candidate["non_focus_middle_edges"]),
        })

    gsl_rows = []
    endpoint_keys = sorted(set(final_src_flow_ids.keys()) | set(final_dst_flow_ids.keys()))
    for endpoint in endpoint_keys:
        for direction, load_map, flow_map in [
            ("src", final_src_load, final_src_flow_ids),
            ("dst", final_dst_load, final_dst_flow_ids),
        ]:
            flow_ids_for_endpoint = flow_map.get(endpoint, [])
            if not flow_ids_for_endpoint:
                continue
            total_load = load_map[endpoint]
            gsl_rows.append({
                "endpoint_node": endpoint,
                "direction": direction,
                "flow_count": len(flow_ids_for_endpoint),
                "total_offered_rate_mbps": total_load,
                "gsl_capacity_mbps": gsl_capacity_mbps,
                "load_ratio": total_load / gsl_capacity_mbps,
                "over_capacity": _format_bool(total_load > gsl_capacity_mbps + 1e-9),
                "endpoint_load_cap_ratio": run["endpoint_load_cap_ratio"],
                "endpoint_load_cap_mbps": endpoint_cap_mbps,
                "over_endpoint_load_cap": _format_bool(
                    total_load > endpoint_cap_mbps + 1e-9
                ),
                "selected_flow_ids": ";".join(str(value) for value in flow_ids_for_endpoint),
            })

    satellite_interface_rows = []
    for key in sorted(final_satellite_interface_load.keys()):
        satellite_id, direction = key
        total_load = final_satellite_interface_load[key]
        flow_ids_for_interface = sorted(final_satellite_interface_flow_ids[key])
        satellite_interface_rows.append({
            "satellite_id": satellite_id,
            "interface_type": (
                "first_hop_satellite_proxy"
                if direction == "source"
                else "last_hop_satellite_proxy"
            ),
            "direction": direction,
            "selected_flow_count": len(flow_ids_for_interface),
            "estimated_offered_rate_mbps": total_load,
            "gsl_capacity_mbps": gsl_capacity_mbps,
            "load_ratio": total_load / gsl_capacity_mbps,
            "over_capacity": _format_bool(total_load > gsl_capacity_mbps + 1e-9),
            "satellite_interface_load_cap_ratio": run.get(
                "satellite_interface_load_cap_ratio",
                0.0,
            ),
            "satellite_interface_load_cap_mbps": satellite_interface_cap_mbps,
            "over_satellite_interface_load_cap": _format_bool(
                satellite_interface_cap_mbps > 0
                and total_load > satellite_interface_cap_mbps + 1e-9
            ),
            "selected_flow_ids": ";".join(
                str(value) for value in flow_ids_for_interface
            ),
        })

    edge_flow_ids = defaultdict(set)
    for pair in pairs:
        pair_key = (pair["src"], pair["dst"])
        flow_id = flow_ids[pair_key]
        if pair["class"] == "focus":
            flow_edges = context["focus_middle_edges_by_pair"].get(pair_key, set())
        else:
            flow_edges = selected_candidates_by_pair[pair_key]["candidate_middle_edges"]
        for edge in flow_edges:
            edge_flow_ids[edge].add(flow_id)

    corridor_rows = []
    all_edges = set(edge_flow_ids.keys()) | set(context["focus_middle_edges_union"])
    for edge in sorted(all_edges):
        flow_ids_for_edge = sorted(edge_flow_ids.get(edge, set()))
        estimated_load = per_flow_rate * len(flow_ids_for_edge)
        on_directed_focus_corridor = edge in context["focus_middle_edges_union"]
        on_target_focus_corridor = (
            on_directed_focus_corridor
            or _undirected_edge(edge)
            in context["focus_middle_undirected_edges_union"]
        )
        corridor_rows.append({
            "edge_from": edge[0],
            "edge_to": edge[1],
            "selected_flow_count": len(flow_ids_for_edge),
            "estimated_offered_rate_mbps": estimated_load,
            "isl_capacity_mbps": gsl_capacity_mbps,
            "load_ratio": estimated_load / gsl_capacity_mbps,
            "on_focus_middle_corridor": _format_bool(
                on_directed_focus_corridor
            ),
            "on_target_focus_corridor": _format_bool(on_target_focus_corridor),
            "selected_flow_ids": ";".join(str(value) for value in flow_ids_for_edge),
            "selected_flow_ids_using_edge": ";".join(
                str(value) for value in flow_ids_for_edge
            ),
        })
    ranked_corridor_rows = sorted(
        corridor_rows,
        key=lambda row: (
            -row["estimated_offered_rate_mbps"],
            row["edge_from"],
            row["edge_to"],
        ),
    )
    for rank, row in enumerate(ranked_corridor_rows, start=1):
        row["edge_rank_by_load"] = rank
    corridor_rows.sort(
        key=lambda row: (
            row["on_target_focus_corridor"] != "true",
            -row["estimated_offered_rate_mbps"],
            row["edge_from"],
            row["edge_to"],
        )
    )

    fallback_rows = []
    selected_by_phase = defaultdict(list)
    for candidate in selected:
        selected_by_phase[candidate["selection_phase"]].append(candidate)
    for phase in context.get("selection_phases", []):
        selected_in_phase = selected_by_phase.get(phase["name"], [])
        overlaps = [
            _candidate_effective_overlap_score(candidate)
            for candidate in selected_in_phase
        ]
        candidate_count = context.get("phase_stats", {}).get(
            phase["name"],
            {},
        ).get("candidate_count", 0)
        fallback_rows.append({
            "phase": phase["name"],
            "selected_count": len(selected_in_phase),
            "candidate_count": candidate_count,
            "rejected_count": max(candidate_count - len(selected_in_phase), 0),
            "zero_overlap_selected_count": sum(
                1
                for candidate in selected_in_phase
                if _candidate_effective_overlap_score(candidate) <= 0
            ),
            "avg_overlap": (
                sum(overlaps) / float(len(overlaps)) if overlaps else 0.0
            ),
            "min_overlap": min(overlaps) if overlaps else 0,
            "max_overlap": max(overlaps) if overlaps else 0,
            "notes": (
                "relaxed_constraints=%s; fallback_reason=%s"
                % (phase["relaxed_constraints"], phase["fallback_reason"])
            ),
        })

    target_corridor_rows = [
        row for row in corridor_rows if row["on_target_focus_corridor"] == "true"
    ]
    non_focus_rows = [
        row for row in corridor_rows if row["on_target_focus_corridor"] != "true"
    ]
    top_loaded = ranked_corridor_rows[0] if ranked_corridor_rows else None
    top_non_focus = sorted(
        non_focus_rows,
        key=lambda row: (
            -row["estimated_offered_rate_mbps"],
            row["edge_from"],
            row["edge_to"],
        ),
    )
    top_non_focus = top_non_focus[0] if top_non_focus else None
    selected_overlaps = [
        _candidate_effective_overlap_score(candidate)
        for candidate in selected
    ]
    target_corridor_load = sum(
        float(row["estimated_offered_rate_mbps"])
        for row in target_corridor_rows
    )
    non_focus_load = sum(
        float(row["estimated_offered_rate_mbps"])
        for row in non_focus_rows
    )
    corridor_concentration_rows = [{
        "flow_selection_hash": flow_selection_hash,
        "selection_input_hash": selection_input_hash,
        "sampled_timestamps": _format_timestamps(context["sampled_timestamps"]),
        "target_corridor_edge_count": len(
            context["focus_middle_undirected_edges_union"]
        ),
        "selected_flow_count": len(selected),
        "avg_middle_isl_overlap": (
            sum(selected_overlaps) / float(len(selected_overlaps))
            if selected_overlaps
            else 0.0
        ),
        "zero_overlap_selected_count": sum(
            1
            for candidate in selected
            if _candidate_effective_overlap_score(candidate) <= 0
        ),
        "target_corridor_offered_load_mbps": target_corridor_load,
        "target_corridor_max_load_ratio": (
            max([float(row["load_ratio"]) for row in target_corridor_rows])
            if target_corridor_rows
            else 0.0
        ),
        "top_loaded_edge": (
            "%d->%d" % (top_loaded["edge_from"], top_loaded["edge_to"])
            if top_loaded
            else ""
        ),
        "top_loaded_edge_on_target_corridor": (
            top_loaded["on_target_focus_corridor"] if top_loaded else ""
        ),
        "top_non_focus_edge": (
            "%d->%d" % (top_non_focus["edge_from"], top_non_focus["edge_to"])
            if top_non_focus
            else ""
        ),
        "top_non_focus_edge_load_ratio": (
            top_non_focus["load_ratio"] if top_non_focus else 0.0
        ),
        "target_to_non_focus_load_ratio": (
            target_corridor_load / non_focus_load
            if non_focus_load > 0
            else "inf"
        ),
    }]

    zero_overlap_selected_count = corridor_concentration_rows[0][
        "zero_overlap_selected_count"
    ]
    if zero_overlap_selected_count:
        warnings.append(
            "Selected %d zero-overlap background flows after fallback."
            % zero_overlap_selected_count
        )
    if top_loaded and top_loaded["on_target_focus_corridor"] != "true":
        warnings.append(
            "Top estimated loaded ISL edge %d->%d is not on the target focus corridor."
            % (top_loaded["edge_from"], top_loaded["edge_to"])
        )
    endpoint_cap_exceeded_rows = [
        row for row in gsl_rows if row["over_endpoint_load_cap"] == "true"
    ]
    if endpoint_cap_exceeded_rows:
        warnings.append(
            "%d endpoint load rows exceed endpoint_load_cap_ratio=%.3f but remain below or equal to GSL capacity unless over_capacity=true."
            % (len(endpoint_cap_exceeded_rows), run["endpoint_load_cap_ratio"])
        )
    satellite_cap_exceeded_rows = [
        row
        for row in satellite_interface_rows
        if row["over_satellite_interface_load_cap"] == "true"
    ]
    if satellite_cap_exceeded_rows:
        warnings.append(
            "%d satellite-interface proxy rows exceed satellite_interface_load_cap_ratio=%.3f but remain below or equal to GSL capacity unless over_capacity=true."
            % (
                len(satellite_cap_exceeded_rows),
                run.get("satellite_interface_load_cap_ratio", 0.0),
            )
        )

    for rows in [
        selection_rows,
        overlap_rows,
        gsl_rows,
        corridor_rows,
        fallback_rows,
        corridor_concentration_rows,
        satellite_interface_rows,
    ]:
        for row in rows:
            row.update(_focus_identity_fields(run))
            row["background_flow_count"] = run["background_flow_count"]
            row["per_flow_rate_mbps"] = per_flow_rate

    return {
        "flow_selection_diagnostics.csv": selection_rows,
        "corridor_overlap_summary.csv": overlap_rows,
        "gsl_load_by_endpoint.csv": gsl_rows,
        "isl_corridor_load_summary.csv": corridor_rows,
        "fallback_phase_summary.csv": fallback_rows,
        "corridor_concentration_summary.csv": corridor_concentration_rows,
        "satellite_interface_load_summary.csv": satellite_interface_rows,
        "warnings": warnings,
    }


def _generate_core_isl_hotspot_pairs(run, sample_count):
    context = _evaluate_core_isl_hotspot_candidates(run, sample_count)
    selected, warnings = _select_core_isl_hotspot_candidates(run, context)
    pairs = _generate_focus_only_pairs(run)
    for candidate in selected:
        pairs.append({
            "src": candidate["src"],
            "dst": candidate["dst"],
            "class": "background",
            "score": candidate["middle_isl_overlap_score"],
            "selection_phase": candidate["selection_phase"],
            "corridor_concentration_score": candidate[
                "corridor_concentration_score"
            ],
            "path_stability_score": candidate["path_stability_score"],
        })
    context["selection_input_hash"] = _selection_input_hash(run, context)
    context["flow_selection_hash"] = _flow_selection_hash(run, context, pairs)
    for pair in pairs:
        pair["selection_input_hash"] = context["selection_input_hash"]
        pair["flow_selection_hash"] = context["flow_selection_hash"]
        pair["selection_sampled_timestamps"] = _format_timestamps(
            context["sampled_timestamps"]
        )
    diagnostics = _build_core_isl_diagnostics(run, context, selected, warnings, pairs)
    return pairs, diagnostics


def generate_pairs_and_diagnostics(run, hotspot_sample_count):
    if run["traffic_mode"] == "focus_only":
        return _generate_focus_only_pairs(run), None
    if run["traffic_mode"] == "core_hotspot_specific":
        return _generate_core_hotspot_pairs(run, hotspot_sample_count), None
    if run["traffic_mode"] == "core_isl_hotspot_specific":
        return _generate_core_isl_hotspot_pairs(run, hotspot_sample_count)
    if run["traffic_mode"] == "random_general":
        return _generate_random_general_pairs(run), None
    raise ValueError("Unknown traffic mode: %s" % run["traffic_mode"])


def generate_pairs(run, hotspot_sample_count):
    pairs, _ = generate_pairs_and_diagnostics(run, hotspot_sample_count)
    return pairs


def compute_per_flow_rate_mbps(run, pair_count):
    if pair_count <= 0:
        raise ValueError("Cannot compute rate for zero flows")
    aggregate_rate = run["load_level"] * run["data_rate_megabit_per_s"]
    reference_pair_count = pair_count
    if run["traffic_mode"] in background_flow_traffic_modes:
        reference_pair_count = (
            len(_generate_focus_only_pairs(run))
            + int(run["per_flow_rate_reference_background_flow_count"])
        )
    if reference_pair_count <= 0:
        raise ValueError("Cannot compute rate for zero reference flows")
    return aggregate_rate / float(reference_pair_count)


def compute_reference_pair_count_for_per_flow_rate(run, pair_count):
    if run["traffic_mode"] in background_flow_traffic_modes:
        return (
            len(_generate_focus_only_pairs(run))
            + int(run["per_flow_rate_reference_background_flow_count"])
        )
    return pair_count


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
                "background_flow_count=%d" % run["background_flow_count"],
                "per_flow_rate_mbps=%.10f" % per_flow_rate,
                "per_flow_rate_reference_background_flow_count=%d"
                % run["per_flow_rate_reference_background_flow_count"],
                "traffic_stop_time_ns=%d" % run["traffic_stop_time_ns"],
                "drain_time_ns=%d" % run["drain_time_ns"],
                "focus_src_node_id=%d" % run["src_node_id"],
                "focus_dst_node_id=%d" % run["dst_node_id"],
                "focus_pair_tag=%s" % run["focus_pair_tag"],
            ]
            if pair.get("score") != "":
                metadata_items.append("hotspot_score=%s" % pair["score"])
            if pair.get("selection_phase"):
                metadata_items.append("selected_phase=%s" % pair["selection_phase"])
            if pair.get("flow_selection_hash"):
                metadata_items.append(
                    "flow_selection_hash=%s" % pair["flow_selection_hash"]
                )
            if pair.get("selection_input_hash"):
                metadata_items.append(
                    "selection_input_hash=%s" % pair["selection_input_hash"]
                )
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
    reference_pair_count = compute_reference_pair_count_for_per_flow_rate(
        run,
        len(pairs),
    )
    scheduled_total_rate = per_flow_rate * len(pairs)
    flow_selection_hash = pairs[0].get("flow_selection_hash", "") if pairs else ""
    selection_input_hash = pairs[0].get("selection_input_hash", "") if pairs else ""
    selection_sampled_timestamps = (
        pairs[0].get("selection_sampled_timestamps", "") if pairs else ""
    )
    metadata = {
        "run": run,
        **_focus_identity_fields(run),
        "lohi_management_mode": run["lohi_management_mode"],
        "flow_count": len(pairs),
        "flow_count_by_class": dict(by_class),
        "per_flow_rate_mbps": per_flow_rate,
        "per_flow_rate_reference_background_flow_count": run[
            "per_flow_rate_reference_background_flow_count"
        ],
        "reference_flow_count_for_per_flow_rate": reference_pair_count,
        "reference_aggregate_offered_rate_mbps": (
            run["load_level"] * run["data_rate_megabit_per_s"]
        ),
        "aggregate_offered_rate_mbps": scheduled_total_rate,
        "background_offered_rate_mbps": (
            per_flow_rate * by_class.get("background", 0)
        ),
        "focus_offered_rate_mbps": per_flow_rate * by_class.get("focus", 0),
        "simulation_end_time_s": run["simulation_end_time_s"],
        "traffic_stop_time_s": run["traffic_stop_time_s"],
        "drain_time_s": run["drain_time_s"],
        "simulation_end_time_ns": run["simulation_end_time_ns"],
        "traffic_stop_time_ns": run["traffic_stop_time_ns"],
        "drain_time_ns": run["drain_time_ns"],
        "drain_time_enabled": run["drain_time_enabled"],
        "flow_selection_hash": flow_selection_hash,
        "selection_input_hash": selection_input_hash,
        "selection_sampled_timestamps": selection_sampled_timestamps,
        "flow_selection_settings": {
            "endpoint_load_cap_ratio": run.get("endpoint_load_cap_ratio"),
            "satellite_interface_load_cap_ratio": run.get(
                "satellite_interface_load_cap_ratio"
            ),
            "max_background_flows_per_src": run.get(
                "max_background_flows_per_src"
            ),
            "max_background_flows_per_dst": run.get(
                "max_background_flows_per_dst"
            ),
            "min_middle_isl_overlap_score": run.get(
                "min_middle_isl_overlap_score"
            ),
            "min_reachable_overlap_samples": run.get(
                "min_reachable_overlap_samples"
            ),
            "min_overlap_ratio": run.get("min_overlap_ratio"),
            "selection_sample_horizon_s": run.get("selection_sample_horizon_s"),
            "selection_sample_times_s": run.get("selection_sample_times_s"),
        },
        "pairs": pairs,
        "notes": [
            "UDP/PDR experiment generated outside paper/lohi_replication/traffic_matrix.",
            "core_hotspot_specific uses baseline shortest-path middle-ISL overlap heuristic.",
            "core_isl_hotspot_specific adds endpoint, satellite-interface, and per-endpoint spread constraints before selecting middle-ISL-overlapping background flows.",
            "core_isl_hotspot_specific flow selection samples a fixed baseline time horizon by default, so selected pairs can remain stable across different simulation durations.",
            "In background-flow sweeps, per-flow rate is computed from the configured reference background-flow count, not from the current background-flow count.",
            "UDP packets are generated only until traffic_stop_time_s; NS-3 continues until simulation_end_time_s to drain in-flight packets.",
        ],
    }
    _write_text(
        os.path.join(run_dir, "run_metadata.json"),
        json.dumps(metadata, indent=2, sort_keys=True),
    )


def write_schedule_summary(run_parent_dir, run, pairs, per_flow_rate):
    by_class = defaultdict(int)
    for pair in pairs:
        by_class[pair["class"]] += 1
    reference_pair_count = compute_reference_pair_count_for_per_flow_rate(
        run,
        len(pairs),
    )
    traffic_duration_s = (
        run["traffic_stop_time_ns"] / 1e9
        if run["traffic_stop_time_ns"] is not None
        else 0.0
    )
    flow_selection_hash = pairs[0].get("flow_selection_hash", "") if pairs else ""
    selection_input_hash = pairs[0].get("selection_input_hash", "") if pairs else ""
    rows = [{
        "run_name": run["name"],
        **_focus_identity_fields(run),
        "traffic_mode": run["traffic_mode"],
        "lohi_management_mode": run["lohi_management_mode"],
        "load_level": run["load_level"],
        "background_flow_count": run["background_flow_count"],
        "generated_background_flow_count": by_class.get("background", 0),
        "focus_flow_count": by_class.get("focus", 0),
        "total_flow_count": len(pairs),
        "per_flow_rate_mbps": per_flow_rate,
        "per_flow_rate_reference_background_flow_count": run[
            "per_flow_rate_reference_background_flow_count"
        ],
        "reference_flow_count_for_per_flow_rate": reference_pair_count,
        "reference_aggregate_offered_rate_mbps": (
            run["load_level"] * run["data_rate_megabit_per_s"]
        ),
        "total_offered_rate_mbps": per_flow_rate * len(pairs),
        "background_offered_rate_mbps": per_flow_rate * by_class.get("background", 0),
        "focus_offered_rate_mbps": per_flow_rate * by_class.get("focus", 0),
        "traffic_duration_s": traffic_duration_s,
        "flow_selection_hash": flow_selection_hash,
        "selection_input_hash": selection_input_hash,
    }]
    _write_csv(
        os.path.join(run_parent_dir, "schedule_summary.csv"),
        rows,
        [
            "run_name",
            "focus_src_node_id",
            "focus_dst_node_id",
            "focus_src_name_if_available",
            "focus_dst_name_if_available",
            "focus_pair_tag",
            "focus_flow_direction_count",
            "traffic_mode",
            "lohi_management_mode",
            "load_level",
            "background_flow_count",
            "generated_background_flow_count",
            "focus_flow_count",
            "total_flow_count",
            "per_flow_rate_mbps",
            "per_flow_rate_reference_background_flow_count",
            "reference_flow_count_for_per_flow_rate",
            "reference_aggregate_offered_rate_mbps",
            "total_offered_rate_mbps",
            "background_offered_rate_mbps",
            "focus_offered_rate_mbps",
            "traffic_duration_s",
            "flow_selection_hash",
            "selection_input_hash",
        ],
    )


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _focus_identity_fields(run):
    return {
        "focus_src_node_id": run["src_node_id"],
        "focus_dst_node_id": run["dst_node_id"],
        "focus_src_name_if_available": run.get(
            "focus_src_name_if_available",
            "",
        ),
        "focus_dst_name_if_available": run.get(
            "focus_dst_name_if_available",
            "",
        ),
        "focus_pair_tag": run["focus_pair_tag"],
        "focus_flow_direction_count": run["focus_flow_direction_count"],
    }


def write_selection_diagnostics(run_parent_dir, diagnostics):
    if diagnostics is None:
        return []
    os.makedirs(run_parent_dir, exist_ok=True)
    written = []
    focus_columns = [
        "focus_src_node_id",
        "focus_dst_node_id",
        "focus_src_name_if_available",
        "focus_dst_name_if_available",
        "focus_pair_tag",
        "focus_flow_direction_count",
    ]
    schemas = {
        "flow_selection_diagnostics.csv": focus_columns + [
            "background_flow_count",
            "per_flow_rate_mbps",
            "flow_selection_hash",
            "selection_input_hash",
            "flow_id",
            "src",
            "dst",
            "flow_class",
            "selected",
            "selection_rank",
            "selection_phase",
            "selected_phase",
            "fallback_phase",
            "fallback_reason",
            "relaxed_constraints",
            "middle_isl_overlap_score",
            "directed_overlap_score",
            "undirected_overlap_score",
            "overlap_ratio",
            "reachable_samples",
            "sampled_timestamps",
            "first_hop_conflict",
            "last_hop_conflict",
            "satellite_interface_keys",
            "adds_target_corridor_load_mbps",
            "adds_non_focus_edge_load_mbps",
            "src_endpoint_load_mbps_after_selection",
            "dst_endpoint_load_mbps_after_selection",
            "src_endpoint_load_ratio",
            "dst_endpoint_load_ratio",
            "src_endpoint_load_ratio_after",
            "dst_endpoint_load_ratio_after",
            "src_satellite_interface_load_ratio_after",
            "dst_satellite_interface_load_ratio_after",
            "candidate_reject_reason",
            "corridor_concentration_score",
            "path_stability_score",
            "selection_score",
            "candidate_rank_before_fallback",
            "candidate_rank_after_fallback",
        ],
        "corridor_overlap_summary.csv": focus_columns + [
            "background_flow_count",
            "per_flow_rate_mbps",
            "flow_selection_hash",
            "selection_input_hash",
            "src",
            "dst",
            "selected",
            "selection_rank",
            "overlap_edges_count",
            "overlap_score",
            "directed_overlap_score",
            "undirected_overlap_score",
            "overlap_ratio",
            "samples_with_overlap",
            "sampled_timestamp_count",
            "focus_middle_edges_count",
            "focus_middle_undirected_edges_count",
            "candidate_middle_edges_count",
            "shared_edges",
            "shared_undirected_edges",
            "non_focus_middle_edges",
        ],
        "gsl_load_by_endpoint.csv": focus_columns + [
            "background_flow_count",
            "per_flow_rate_mbps",
            "endpoint_node",
            "direction",
            "flow_count",
            "total_offered_rate_mbps",
            "gsl_capacity_mbps",
            "load_ratio",
            "over_capacity",
            "endpoint_load_cap_ratio",
            "endpoint_load_cap_mbps",
            "over_endpoint_load_cap",
            "selected_flow_ids",
        ],
        "isl_corridor_load_summary.csv": focus_columns + [
            "background_flow_count",
            "per_flow_rate_mbps",
            "edge_from",
            "edge_to",
            "selected_flow_count",
            "estimated_offered_rate_mbps",
            "isl_capacity_mbps",
            "load_ratio",
            "on_focus_middle_corridor",
            "on_target_focus_corridor",
            "selected_flow_ids",
            "selected_flow_ids_using_edge",
            "edge_rank_by_load",
        ],
        "fallback_phase_summary.csv": focus_columns + [
            "background_flow_count",
            "per_flow_rate_mbps",
            "phase",
            "selected_count",
            "candidate_count",
            "rejected_count",
            "zero_overlap_selected_count",
            "avg_overlap",
            "min_overlap",
            "max_overlap",
            "notes",
        ],
        "corridor_concentration_summary.csv": focus_columns + [
            "background_flow_count",
            "per_flow_rate_mbps",
            "flow_selection_hash",
            "selection_input_hash",
            "sampled_timestamps",
            "target_corridor_edge_count",
            "selected_flow_count",
            "avg_middle_isl_overlap",
            "zero_overlap_selected_count",
            "target_corridor_offered_load_mbps",
            "target_corridor_max_load_ratio",
            "top_loaded_edge",
            "top_loaded_edge_on_target_corridor",
            "top_non_focus_edge",
            "top_non_focus_edge_load_ratio",
            "target_to_non_focus_load_ratio",
        ],
        "satellite_interface_load_summary.csv": focus_columns + [
            "background_flow_count",
            "per_flow_rate_mbps",
            "satellite_id",
            "interface_type",
            "direction",
            "selected_flow_count",
            "estimated_offered_rate_mbps",
            "gsl_capacity_mbps",
            "load_ratio",
            "over_capacity",
            "satellite_interface_load_cap_ratio",
            "satellite_interface_load_cap_mbps",
            "over_satellite_interface_load_cap",
            "selected_flow_ids",
        ],
    }
    for filename in SELECTION_DIAGNOSTIC_FILENAMES:
        path = os.path.join(run_parent_dir, filename)
        _write_csv(path, diagnostics.get(filename, []), schemas[filename])
        written.append(path)
    warnings = diagnostics.get("warnings", [])
    if warnings:
        _write_text(
            os.path.join(run_parent_dir, "flow_selection_warnings.txt"),
            "\n".join(warnings) + "\n",
        )
    return written


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


def print_dry_run_diagnostics(run, diagnostics):
    if diagnostics is None:
        return
    fallback_rows = diagnostics.get("fallback_phase_summary.csv", [])
    concentration_rows = diagnostics.get(
        "corridor_concentration_summary.csv",
        [],
    )
    gsl_rows = diagnostics.get("gsl_load_by_endpoint.csv", [])
    satellite_rows = diagnostics.get(
        "satellite_interface_load_summary.csv",
        [],
    )
    strict_selected_count = sum(
        int(row["selected_count"])
        for row in fallback_rows
        if row["phase"] == "strict"
    )
    fallback_selected_count = sum(
        int(row["selected_count"])
        for row in fallback_rows
        if row["phase"] != "strict"
    )
    concentration = concentration_rows[0] if concentration_rows else {}
    max_endpoint_ratio = max(
        [float(row["load_ratio"]) for row in gsl_rows] or [0.0]
    )
    max_satellite_ratio = max(
        [float(row["load_ratio"]) for row in satellite_rows] or [0.0]
    )
    print("  dry-run focus pair: %d (%s) <-> %d (%s)" % (
        run["src_node_id"],
        run["focus_src_name_if_available"],
        run["dst_node_id"],
        run["focus_dst_name_if_available"],
    ))
    print("  dry-run focus pair tag: %s" % run["focus_pair_tag"])
    print(
        "  dry-run selection quality: strict=%d fallback=%d zero_overlap=%s "
        "target_to_non_focus=%s"
        % (
            strict_selected_count,
            fallback_selected_count,
            concentration.get("zero_overlap_selected_count", ""),
            concentration.get("target_to_non_focus_load_ratio", ""),
        )
    )
    print(
        "  dry-run load caps: max_endpoint_ratio=%.6f cap=%.6f "
        "max_satellite_interface_ratio=%.6f cap=%.6f"
        % (
            max_endpoint_ratio,
            run["endpoint_load_cap_ratio"],
            max_satellite_ratio,
            run["satellite_interface_load_cap_ratio"],
        )
    )
    print(
        "  dry-run hashes: selection_input=%s flow_selection=%s"
        % (
            concentration.get("selection_input_hash", ""),
            concentration.get("flow_selection_hash", ""),
        )
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
    validate_focus_pair_arguments(parser, args)

    selected_mode, modes, load_levels, algorithms = describe_selection(args)
    print("Traffic mode selection: %s (%s)" % (selected_mode, ", ".join(modes)))
    print("Load levels: %s" % ", ".join("%.3f" % x for x in load_levels))
    print("Algorithms: %s" % ", ".join(algorithms))
    print(
        "Focus pair: %d <-> %d"
        % (args.src_node_id, args.dst_node_id)
    )

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
        args.endpoint_load_cap_ratio,
        args.max_background_flows_per_dst,
        args.max_background_flows_per_src,
        args.per_flow_rate_reference_background_flow_count,
        args.satellite_interface_load_cap_ratio,
        args.min_middle_isl_overlap_score,
        args.min_reachable_overlap_samples,
        args.min_overlap_ratio,
        args.selection_sample_horizon_s,
        args.selection_sample_times_s,
        args.src_node_id,
        args.dst_node_id,
        args.lohi_management_mode,
    )

    generated_pairs_by_run_name = {}
    diagnostics_written_run_names = set()
    schedule_summary_written_run_names = set()
    for run in runs:
        run_dir = os.path.join("runs", run["name"], run["dynamic_state_algorithm"])
        run_parent_dir = os.path.join("runs", run["name"])
        print("\nPlanned run: %s" % run_dir)
        print(
            "  simulation_end=%.6fs, traffic_stop=%.6fs, drain=%.6fs"
            % (
                run["simulation_end_time_s"],
                run["traffic_stop_time_s"],
                run["drain_time_s"],
            )
        )

        pair_key = (
            run["name"],
            run["traffic_mode"],
            run["load_level"],
            run["background_flow_count"],
            run["random_flow_count"],
            run["endpoint_load_cap_ratio"],
            run["max_background_flows_per_dst"],
            run["max_background_flows_per_src"],
            run["per_flow_rate_reference_background_flow_count"],
            run.get("satellite_interface_load_cap_ratio"),
            run.get("min_middle_isl_overlap_score"),
            run.get("min_reachable_overlap_samples"),
            run.get("min_overlap_ratio"),
            run.get("selection_sample_horizon_s"),
            tuple(run.get("selection_sample_times_s") or []),
            run["src_node_id"],
            run["dst_node_id"],
        )
        if pair_key not in generated_pairs_by_run_name:
            generated_pairs_by_run_name[pair_key] = generate_pairs_and_diagnostics(
                run,
                args.hotspot_sample_count,
            )
        pairs, diagnostics = generated_pairs_by_run_name[pair_key]

        if args.dry_run:
            per_flow_rate = compute_per_flow_rate_mbps(run, len(pairs))
            print(
                "  dry-run selection: %d flows, %.6f Mbps/flow (reference bg flows=%d)"
                % (
                    len(pairs),
                    per_flow_rate,
                    run["per_flow_rate_reference_background_flow_count"],
                )
            )
            for idx, pair in enumerate(pairs):
                print(
                    "    flow %d: %s -> %s class=%s score=%s"
                    % (
                        idx,
                        pair["src"],
                        pair["dst"],
                        pair["class"],
                        pair.get("score", ""),
                    )
                )
            if diagnostics is not None:
                print_dry_run_diagnostics(run, diagnostics)
                print(
                    "  dry-run diagnostics (generation mode) would write: %s"
                    % ", ".join(SELECTION_DIAGNOSTIC_FILENAMES)
                )
            continue

        prepare_run_dir(run_dir, args.force)
        if diagnostics is not None and run["name"] not in diagnostics_written_run_names:
            written = write_selection_diagnostics(run_parent_dir, diagnostics)
            diagnostics_written_run_names.add(run["name"])
            if written:
                print(
                    "  > Wrote selection diagnostics under %s"
                    % run_parent_dir
                )
        udp_logging_ids = list(range(min(run["packet_trace_flow_count"], len(pairs))))
        _write_text(
            os.path.join(run_dir, "config_ns3.properties"),
            _render_config(run, udp_logging_ids),
        )
        schedule_path, per_flow_rate = write_udp_schedule(run_dir, run, pairs)
        write_run_metadata(run_dir, run, pairs, per_flow_rate)
        if run["name"] not in schedule_summary_written_run_names:
            write_schedule_summary(run_parent_dir, run, pairs, per_flow_rate)
            schedule_summary_written_run_names.add(run["name"])
        print(
            "Generated run: %s (%d flows, %.6f Mbps/flow, schedule=%s)"
            % (run_dir, len(pairs), per_flow_rate, schedule_path)
        )

    print("\nSuccess")


if __name__ == "__main__":
    main()
