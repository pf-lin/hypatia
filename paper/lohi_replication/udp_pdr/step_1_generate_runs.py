import csv
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

SELECTION_DIAGNOSTIC_FILENAMES = [
    "flow_selection_diagnostics.csv",
    "corridor_overlap_summary.csv",
    "gsl_load_by_endpoint.csv",
    "isl_corridor_load_summary.csv",
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


def _first_sat(path):
    if path is None or len(path) < 3:
        return None
    return path[1]


def _last_sat(path):
    if path is None or len(path) < 3:
        return None
    return path[-2]


def _format_bool(value):
    return "true" if bool(value) else "false"


def _format_edges(edges):
    return ";".join("%d->%d" % (a, b) for a, b in sorted(edges))


def _format_timestamps(timestamps):
    return ";".join(str(int(value)) for value in timestamps)


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


def _evaluate_core_isl_hotspot_candidates(run, sample_count):
    sys.path.append(SATGENPY_DIR)
    from satgen.post_analysis.graph_tools import get_path

    print("  > Selecting core-ISL hotspot background flows from baseline paths...")
    snapshots = _compute_baseline_snapshots(run, sample_count)
    sampled_timestamps = [time_ns for time_ns, _ in snapshots]

    focus_edges_by_time = {}
    focus_conflict_sats_by_time = {}
    focus_middle_edges_by_pair = {
        (run["src_node_id"], run["dst_node_id"]): set(),
        (run["dst_node_id"], run["src_node_id"]): set(),
    }
    focus_middle_edges_union = set()
    for time_ns, fstate in snapshots:
        path_a = get_path(run["src_node_id"], run["dst_node_id"], fstate)
        path_b = get_path(run["dst_node_id"], run["src_node_id"], fstate)
        path_a_middle = _satellite_middle_edges(path_a)
        path_b_middle = _satellite_middle_edges(path_b)
        focus_edges = path_a_middle | path_b_middle
        focus_edges_by_time[time_ns] = focus_edges
        focus_conflict_sats_by_time[time_ns] = (
            _first_last_sats(path_a) | _first_last_sats(path_b)
        )
        focus_middle_edges_by_pair[(run["src_node_id"], run["dst_node_id"])].update(
            path_a_middle
        )
        focus_middle_edges_by_pair[(run["dst_node_id"], run["src_node_id"])].update(
            path_b_middle
        )
        focus_middle_edges_union.update(focus_edges)

    candidates = []
    focus_endpoint_set = {run["src_node_id"], run["dst_node_id"]}
    for src in endpoint_node_ids:
        for dst in endpoint_node_ids:
            if src == dst or src in focus_endpoint_set or dst in focus_endpoint_set:
                continue

            reachable_samples = 0
            samples_with_overlap = 0
            middle_isl_overlap_score = 0
            first_hop_conflict = False
            last_hop_conflict = False
            shared_edges = set()
            candidate_middle_edges = set()
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
                overlap_edges = middle_edges & focus_edges_by_time[time_ns]
                if overlap_edges:
                    samples_with_overlap += 1
                middle_isl_overlap_score += len(overlap_edges)
                shared_edges.update(overlap_edges)
                candidate_middle_edges.update(middle_edges)

            path_stability_score = reachable_samples + samples_with_overlap
            candidates.append({
                "src": src,
                "dst": dst,
                "reachable_samples": reachable_samples,
                "samples_with_overlap": samples_with_overlap,
                "sampled_timestamps": list(sampled_timestamps),
                "reachable_timestamps": reachable_timestamps,
                "middle_isl_overlap_score": middle_isl_overlap_score,
                "path_stability_score": path_stability_score,
                "first_hop_conflict": first_hop_conflict,
                "last_hop_conflict": last_hop_conflict,
                "edge_conflict": first_hop_conflict or last_hop_conflict,
                "shared_edges": shared_edges,
                "candidate_middle_edges": candidate_middle_edges,
                "focus_middle_edges_count": len(focus_middle_edges_union),
                "candidate_middle_edges_count": len(candidate_middle_edges),
                "selected": False,
                "selection_rank": "",
                "selection_phase": "",
                "selection_score": "",
                "corridor_concentration_score": 0,
            })

    return {
        "sampled_timestamps": sampled_timestamps,
        "focus_middle_edges_union": focus_middle_edges_union,
        "focus_middle_edges_by_pair": focus_middle_edges_by_pair,
        "candidates": candidates,
    }


def _candidate_corridor_concentration_score(candidate, selected_edge_counts):
    return sum(selected_edge_counts[edge] for edge in candidate["shared_edges"])


def _candidate_selection_score(candidate, selected_edge_counts):
    corridor_score = _candidate_corridor_concentration_score(
        candidate,
        selected_edge_counts,
    )
    return (
        float(candidate["middle_isl_overlap_score"])
        + float(corridor_score)
        + 0.1 * float(candidate["path_stability_score"])
    )


def _max_endpoint_count_allows(current_count, max_count):
    return max_count == 0 or current_count < max_count


def _candidate_feasible_for_phase(
    candidate,
    phase,
    per_flow_rate,
    src_load_mbps,
    dst_load_mbps,
    background_src_counts,
    background_dst_counts,
    max_background_flows_per_src,
    max_background_flows_per_dst,
):
    if phase["avoid_edge_conflict"] and candidate["edge_conflict"]:
        return False
    if phase["require_reachable"] and candidate["reachable_samples"] <= 0:
        return False
    if phase["require_overlap"] and candidate["middle_isl_overlap_score"] <= 0:
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

    return True


def _select_core_isl_hotspot_candidates(run, context):
    target_count = run["background_flow_count"]
    if target_count <= 0:
        return [], []

    expected_pair_count = len(_generate_focus_only_pairs(run)) + target_count
    per_flow_rate = compute_per_flow_rate_mbps(run, expected_pair_count)
    gsl_capacity_mbps = run["data_rate_megabit_per_s"]
    endpoint_cap_mbps = run["endpoint_load_cap_ratio"] * gsl_capacity_mbps
    max_per_src = run["max_background_flows_per_src"]
    max_per_dst = run["max_background_flows_per_dst"]

    src_load_mbps = defaultdict(float)
    dst_load_mbps = defaultdict(float)
    for pair in _generate_focus_only_pairs(run):
        src_load_mbps[pair["src"]] += per_flow_rate
        dst_load_mbps[pair["dst"]] += per_flow_rate

    phases = [
        {
            "name": "strict",
            "require_reachable": True,
            "require_overlap": True,
            "avoid_edge_conflict": True,
            "enforce_endpoint_flow_limits": True,
            "endpoint_cap_mbps": endpoint_cap_mbps,
        },
        {
            "name": "fallback_relax_endpoint_flow_limits",
            "require_reachable": True,
            "require_overlap": True,
            "avoid_edge_conflict": True,
            "enforce_endpoint_flow_limits": False,
            "endpoint_cap_mbps": endpoint_cap_mbps,
        },
        {
            "name": "fallback_allow_zero_overlap",
            "require_reachable": True,
            "require_overlap": False,
            "avoid_edge_conflict": True,
            "enforce_endpoint_flow_limits": False,
            "endpoint_cap_mbps": endpoint_cap_mbps,
        },
    ]
    if endpoint_cap_mbps < gsl_capacity_mbps:
        phases.append({
            "name": "fallback_endpoint_cap_to_gsl_capacity",
            "require_reachable": True,
            "require_overlap": False,
            "avoid_edge_conflict": True,
            "enforce_endpoint_flow_limits": False,
            "endpoint_cap_mbps": gsl_capacity_mbps,
        })
    phases.append({
        "name": "fallback_endpoint_cap_exceeded",
        "require_reachable": True,
        "require_overlap": False,
        "avoid_edge_conflict": True,
        "enforce_endpoint_flow_limits": False,
        "endpoint_cap_mbps": None,
    })

    selected = []
    selected_pairs = set()
    selected_edge_counts = defaultdict(int)
    background_src_counts = defaultdict(int)
    background_dst_counts = defaultdict(int)
    warnings = []

    for phase in phases:
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
                    background_src_counts,
                    background_dst_counts,
                    max_per_src,
                    max_per_dst,
                ):
                    continue
                corridor_score = _candidate_corridor_concentration_score(
                    candidate,
                    selected_edge_counts,
                )
                score = _candidate_selection_score(candidate, selected_edge_counts)
                feasible.append((
                    -score,
                    -candidate["middle_isl_overlap_score"],
                    -corridor_score,
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
            chosen = feasible[0][7]
            score = feasible[0][8]
            corridor_score = feasible[0][9]
            chosen["selected"] = True
            chosen["selection_rank"] = len(selected) + 1
            chosen["selection_phase"] = phase["name"]
            chosen["selection_score"] = score
            chosen["corridor_concentration_score"] = corridor_score

            selected.append(chosen)
            selected_pairs.add((chosen["src"], chosen["dst"]))
            background_src_counts[chosen["src"]] += 1
            background_dst_counts[chosen["dst"]] += 1
            src_load_mbps[chosen["src"]] += per_flow_rate
            dst_load_mbps[chosen["dst"]] += per_flow_rate
            for edge in chosen["shared_edges"]:
                selected_edge_counts[edge] += 1

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

    return selected, warnings


def _core_isl_candidate_reject_reason(candidate, run, final_src_load, final_dst_load):
    if candidate["selected"]:
        if candidate["selection_phase"] == "strict":
            return "selected"
        return "selected_%s" % candidate["selection_phase"]
    if candidate["edge_conflict"]:
        return "edge_conflict"
    if candidate["reachable_samples"] <= 0:
        return "unreachable"
    if candidate["middle_isl_overlap_score"] <= 0:
        return "zero_middle_isl_overlap"

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
    return "not_selected_lower_score"


def _build_core_isl_diagnostics(run, context, selected, warnings, pairs):
    per_flow_rate = compute_per_flow_rate_mbps(run, len(pairs))
    gsl_capacity_mbps = run["data_rate_megabit_per_s"]
    endpoint_cap_mbps = run["endpoint_load_cap_ratio"] * gsl_capacity_mbps

    flow_ids = {
        (pair["src"], pair["dst"]): idx
        for idx, pair in enumerate(pairs)
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
    for idx, pair in enumerate(pairs):
        final_src_load[pair["src"]] += per_flow_rate
        final_dst_load[pair["dst"]] += per_flow_rate
        final_src_flow_ids[pair["src"]].append(idx)
        final_dst_flow_ids[pair["dst"]].append(idx)

    reject_src_load = defaultdict(float, final_src_load)
    reject_dst_load = defaultdict(float, final_dst_load)
    reject_src_load["_per_flow_rate"] = per_flow_rate
    reject_dst_load["_per_flow_rate"] = per_flow_rate
    reject_src_load["_selected_background_srcs"] = selected_background_srcs
    reject_dst_load["_selected_background_dsts"] = selected_background_dsts

    selection_rows = []
    for pair in pairs[:2]:
        src = pair["src"]
        dst = pair["dst"]
        selection_rows.append({
            "flow_id": flow_ids[(src, dst)],
            "src": src,
            "dst": dst,
            "flow_class": "focus",
            "selected": "true",
            "selection_rank": 0,
            "selection_phase": "focus",
            "middle_isl_overlap_score": "",
            "reachable_samples": len(context["sampled_timestamps"]),
            "sampled_timestamps": _format_timestamps(context["sampled_timestamps"]),
            "first_hop_conflict": "false",
            "last_hop_conflict": "false",
            "src_endpoint_load_mbps_after_selection": final_src_load[src],
            "dst_endpoint_load_mbps_after_selection": final_dst_load[dst],
            "src_endpoint_load_ratio": final_src_load[src] / gsl_capacity_mbps,
            "dst_endpoint_load_ratio": final_dst_load[dst] / gsl_capacity_mbps,
            "candidate_reject_reason": "selected_focus",
            "corridor_concentration_score": "",
            "path_stability_score": "",
            "selection_score": "",
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
            "flow_id": flow_ids.get((src, dst), ""),
            "src": src,
            "dst": dst,
            "flow_class": "background",
            "selected": _format_bool(selected_flag),
            "selection_rank": candidate["selection_rank"],
            "selection_phase": candidate["selection_phase"],
            "middle_isl_overlap_score": candidate["middle_isl_overlap_score"],
            "reachable_samples": candidate["reachable_samples"],
            "sampled_timestamps": _format_timestamps(candidate["sampled_timestamps"]),
            "first_hop_conflict": _format_bool(candidate["first_hop_conflict"]),
            "last_hop_conflict": _format_bool(candidate["last_hop_conflict"]),
            "src_endpoint_load_mbps_after_selection": projected_src_load,
            "dst_endpoint_load_mbps_after_selection": projected_dst_load,
            "src_endpoint_load_ratio": projected_src_load / gsl_capacity_mbps,
            "dst_endpoint_load_ratio": projected_dst_load / gsl_capacity_mbps,
            "candidate_reject_reason": _core_isl_candidate_reject_reason(
                candidate,
                run,
                reject_src_load,
                reject_dst_load,
            ),
            "corridor_concentration_score": candidate[
                "corridor_concentration_score"
            ],
            "path_stability_score": candidate["path_stability_score"],
            "selection_score": candidate["selection_score"],
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
            "src": candidate["src"],
            "dst": candidate["dst"],
            "selected": _format_bool(candidate["selected"]),
            "selection_rank": candidate["selection_rank"],
            "overlap_edges_count": len(candidate["shared_edges"]),
            "overlap_score": candidate["middle_isl_overlap_score"],
            "sampled_timestamp_count": candidate["reachable_samples"],
            "focus_middle_edges_count": candidate["focus_middle_edges_count"],
            "candidate_middle_edges_count": candidate["candidate_middle_edges_count"],
            "shared_edges": _format_edges(candidate["shared_edges"]),
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

    selected_candidates_by_pair = {
        (candidate["src"], candidate["dst"]): candidate
        for candidate in selected
    }
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
        corridor_rows.append({
            "edge_from": edge[0],
            "edge_to": edge[1],
            "selected_flow_count": len(flow_ids_for_edge),
            "estimated_offered_rate_mbps": estimated_load,
            "isl_capacity_mbps": gsl_capacity_mbps,
            "load_ratio": estimated_load / gsl_capacity_mbps,
            "on_focus_middle_corridor": _format_bool(
                edge in context["focus_middle_edges_union"]
            ),
            "selected_flow_ids": ";".join(str(value) for value in flow_ids_for_edge),
        })
    corridor_rows.sort(
        key=lambda row: (
            row["on_focus_middle_corridor"] != "true",
            -row["estimated_offered_rate_mbps"],
            row["edge_from"],
            row["edge_to"],
        )
    )

    return {
        "flow_selection_diagnostics.csv": selection_rows,
        "corridor_overlap_summary.csv": overlap_rows,
        "gsl_load_by_endpoint.csv": gsl_rows,
        "isl_corridor_load_summary.csv": corridor_rows,
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
            "core_isl_hotspot_specific adds endpoint load caps and per-endpoint spread constraints before selecting middle-ISL-overlapping background flows.",
            "UDP packets are generated only until traffic_stop_time_s; NS-3 continues until simulation_end_time_s to drain in-flight packets.",
        ],
    }
    _write_text(
        os.path.join(run_dir, "run_metadata.json"),
        json.dumps(metadata, indent=2, sort_keys=True),
    )


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_selection_diagnostics(run_parent_dir, diagnostics):
    if diagnostics is None:
        return []
    os.makedirs(run_parent_dir, exist_ok=True)
    written = []
    schemas = {
        "flow_selection_diagnostics.csv": [
            "flow_id",
            "src",
            "dst",
            "flow_class",
            "selected",
            "selection_rank",
            "selection_phase",
            "middle_isl_overlap_score",
            "reachable_samples",
            "sampled_timestamps",
            "first_hop_conflict",
            "last_hop_conflict",
            "src_endpoint_load_mbps_after_selection",
            "dst_endpoint_load_mbps_after_selection",
            "src_endpoint_load_ratio",
            "dst_endpoint_load_ratio",
            "candidate_reject_reason",
            "corridor_concentration_score",
            "path_stability_score",
            "selection_score",
        ],
        "corridor_overlap_summary.csv": [
            "src",
            "dst",
            "selected",
            "selection_rank",
            "overlap_edges_count",
            "overlap_score",
            "sampled_timestamp_count",
            "focus_middle_edges_count",
            "candidate_middle_edges_count",
            "shared_edges",
        ],
        "gsl_load_by_endpoint.csv": [
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
        "isl_corridor_load_summary.csv": [
            "edge_from",
            "edge_to",
            "selected_flow_count",
            "estimated_offered_rate_mbps",
            "isl_capacity_mbps",
            "load_ratio",
            "on_focus_middle_corridor",
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
        args.endpoint_load_cap_ratio,
        args.max_background_flows_per_dst,
        args.max_background_flows_per_src,
    )

    generated_pairs_by_run_name = {}
    diagnostics_written_run_names = set()
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
            run["simulation_end_time_ns"],
            run["traffic_stop_time_ns"],
            run["background_flow_count"],
            run["random_flow_count"],
            run["endpoint_load_cap_ratio"],
            run["max_background_flows_per_dst"],
            run["max_background_flows_per_src"],
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
                "  dry-run selection: %d flows, %.6f Mbps/flow"
                % (len(pairs), per_flow_rate)
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
                print(
                    "  dry-run diagnostics would write: %s"
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
        print(
            "Generated run: %s (%d flows, %.6f Mbps/flow, schedule=%s)"
            % (run_dir, len(pairs), per_flow_rate, schedule_path)
        )

    print("\nSuccess")


if __name__ == "__main__":
    main()
