import csv
import math
import os
from collections import Counter, defaultdict

import networkx as nx

from .queue_delay_cost import (
    DEFAULT_ISL_LINK_CAPACITY_BPS,
    load_queue_statistics_csv,
)


ALGORITHM_NAME = "algorithm_backpressure_over_isls"
COMMODITY_MODE = "destination_proxy"
DEFAULT_QUEUE_SOURCE = "auto"
DEFAULT_FALLBACK = "shortest_path"
DEFAULT_LOOP_GUARD = "none"
DEFAULT_DIAGNOSTIC_SAMPLE_LIMIT = 2000

QUEUE_SOURCE_ALIASES = {
    "auto": "auto",
    "per_destination_bytes": "per_destination_bytes",
    "per_destination_packets": "per_destination_packets",
    "node_total_bytes": "node_total_bytes",
    "node_total_packets": "node_total_packets",
    "interface_bytes": "interface_bytes",
    "interface_packets": "interface_packets",
    "interface_nonreturn_avg_bytes": "interface_nonreturn_avg_bytes",
    "interface_nonreturn_min_bytes": "interface_nonreturn_min_bytes",
}

FALLBACK_POLICIES = {"shortest_path", "no_route"}
LOOP_GUARD_MODES = {
    "none",
    "immediate_reverse",
    "forward_progress_hop",
    "forward_progress_distance",
}


def normalize_backpressure_queue_source(value):
    source = str(value or DEFAULT_QUEUE_SOURCE).strip().lower()
    if source not in QUEUE_SOURCE_ALIASES:
        raise ValueError(
            "backpressure queue source must be one of %s, got %r"
            % (sorted(QUEUE_SOURCE_ALIASES), value)
        )
    return QUEUE_SOURCE_ALIASES[source]


def normalize_backpressure_fallback(value):
    fallback = str(value or DEFAULT_FALLBACK).strip().lower()
    if fallback not in FALLBACK_POLICIES:
        raise ValueError(
            "backpressure fallback must be one of %s, got %r"
            % (sorted(FALLBACK_POLICIES), value)
        )
    return fallback


def normalize_backpressure_loop_guard(value):
    mode = str(value or DEFAULT_LOOP_GUARD).strip().lower()
    if mode not in LOOP_GUARD_MODES:
        raise ValueError(
            "backpressure loop guard must be one of %s, got %r"
            % (sorted(LOOP_GUARD_MODES), value)
        )
    return mode


def _bool_text(value):
    return "true" if bool(value) else "false"


def _p95(values):
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return 0.0
    index = int(math.ceil(0.95 * len(clean))) - 1
    return clean[max(0, min(index, len(clean) - 1))]


def _mean(values):
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return 0.0
    return sum(clean) / float(len(clean))


def _append_csv(path, fieldnames, rows):
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_gsl_if_bandwidth(
    output_dynamic_state_dir,
    time_since_epoch_ns,
    satellites,
    ground_stations,
    num_isls_per_sat,
    list_gsl_interfaces_info,
    enable_verbose_logs,
):
    output_filename = (
        output_dynamic_state_dir + "/gsl_if_bandwidth_" + str(time_since_epoch_ns) + ".txt"
    )
    if enable_verbose_logs:
        print("  > Writing interface bandwidth state to: " + output_filename)
    with open(output_filename, "w+") as f_out:
        if time_since_epoch_ns == 0:
            for node_id in range(len(satellites)):
                f_out.write(
                    "%d,%d,%f\n"
                    % (
                        node_id,
                        num_isls_per_sat[node_id],
                        list_gsl_interfaces_info[node_id]["aggregate_max_bandwidth"],
                    )
                )
            for node_id in range(len(satellites), len(satellites) + len(ground_stations)):
                f_out.write(
                    "%d,%d,%f\n"
                    % (
                        node_id,
                        0,
                        list_gsl_interfaces_info[node_id]["aggregate_max_bandwidth"],
                    )
                )


def _load_proxy_queue_state(queue_stats_file, num_satellites, requested_source):
    queue_file_exists = bool(queue_stats_file and os.path.exists(queue_stats_file))
    stats = load_queue_statistics_csv(queue_stats_file, num_satellites)
    requested_source = normalize_backpressure_queue_source(requested_source)

    if requested_source in ("auto", "per_destination_bytes", "per_destination_packets"):
        if stats.queue_bytes:
            mode = "node_total"
            unit = "bytes"
            effective_source = "node_total_queue_bytes"
            link_values = stats.queue_bytes
        elif stats.queue_packets:
            mode = "node_total"
            unit = "packets"
            effective_source = "node_total_queue_packets"
            link_values = stats.queue_packets
        else:
            mode = "node_total"
            unit = "unknown"
            effective_source = "unknown"
            link_values = {}
    elif requested_source == "node_total_bytes":
        mode = "node_total"
        unit = "bytes"
        effective_source = "node_total_queue_bytes"
        link_values = stats.queue_bytes
    elif requested_source == "node_total_packets":
        mode = "node_total"
        unit = "packets"
        effective_source = "node_total_queue_packets"
        link_values = stats.queue_packets
    elif requested_source == "interface_bytes":
        mode = "interface"
        unit = "bytes"
        effective_source = "interface_queue_bytes"
        link_values = stats.queue_bytes
    elif requested_source == "interface_packets":
        mode = "interface"
        unit = "packets"
        effective_source = "interface_queue_packets"
        link_values = stats.queue_packets
    elif requested_source == "interface_nonreturn_avg_bytes":
        mode = "interface_nonreturn_avg"
        unit = "bytes"
        effective_source = "interface_nonreturn_avg_bytes"
        link_values = stats.queue_bytes
    elif requested_source == "interface_nonreturn_min_bytes":
        mode = "interface_nonreturn_min"
        unit = "bytes"
        effective_source = "interface_nonreturn_min_bytes"
        link_values = stats.queue_bytes
    else:
        raise ValueError("Unsupported queue source: %s" % requested_source)

    node_totals = defaultdict(float)
    for (sat_from, _), value in link_values.items():
        node_totals[sat_from] += float(value)

    return {
        "requested_source": requested_source,
        "effective_source": effective_source,
        "mode": mode,
        "unit": unit,
        "link_values": link_values,
        "node_totals": node_totals,
        "queue_file_exists": queue_file_exists,
        "per_destination_available": False,
    }


def _empty_candidate_metrics(current, neighbor):
    current_out_interface = "%d->%d" % (current, neighbor) if neighbor != -1 else ""
    neighbor_return_interface = "%d->%d" % (neighbor, current) if neighbor != -1 else ""
    return {
        "neighbor": neighbor,
        "queue_current": 0.0,
        "queue_neighbor": 0.0,
        "queue_diff": 0.0,
        "weight": 0.0,
        "current_out_interface": current_out_interface,
        "neighbor_return_interface": neighbor_return_interface,
        "neighbor_forward_interfaces": "",
        "queue_current_out_interface": 0.0,
        "queue_neighbor_forward_avg": 0.0,
        "queue_neighbor_forward_min": 0.0,
        "interface_queue_source_available": False,
        "nonreturn_interface_count": 0,
        "no_forward_interface": False,
        "interface_mapping_missing": False,
        "loop_guard_mode": DEFAULT_LOOP_GUARD,
        "forward_progress_metric": "none",
        "current_distance_to_destination": "",
        "candidate_distance_to_destination": "",
        "current_hop_distance_to_destination": "",
        "candidate_hop_distance_to_destination": "",
        "candidate_is_forward_progress": True,
        "candidate_filtered_by_loop_guard": False,
        "legal_candidate_count": 0,
        "illegal_candidate_count": 0,
        "total_candidates_before_guard": 0,
        "total_candidates_after_guard": 0,
        "selected_after_loop_guard": True,
        "forward_progress_distance_missing": False,
    }


def _queue_pair_for_candidate(queue_state, current, neighbor, sat_graph=None):
    metrics = _empty_candidate_metrics(current, neighbor)
    if queue_state["mode"] == "interface":
        values = queue_state["link_values"]
        queue_current = float(values.get((current, neighbor), 0.0))
        queue_neighbor = float(values.get((neighbor, current), 0.0))
        metrics.update(
            {
                "queue_current": queue_current,
                "queue_neighbor": queue_neighbor,
                "queue_current_out_interface": queue_current,
                "queue_neighbor_forward_avg": queue_neighbor,
                "queue_neighbor_forward_min": queue_neighbor,
                "interface_queue_source_available": queue_state["queue_file_exists"],
                "nonreturn_interface_count": 1,
            }
        )
        return metrics

    if queue_state["mode"] in ("interface_nonreturn_avg", "interface_nonreturn_min"):
        values = queue_state["link_values"]
        queue_current = float(values.get((current, neighbor), 0.0))
        forward_neighbors = []
        if sat_graph is not None and neighbor in sat_graph:
            forward_neighbors = [
                int(candidate)
                for candidate in sat_graph.neighbors(neighbor)
                if int(candidate) != int(current)
            ]
        forward_values = [
            float(values.get((neighbor, candidate), 0.0))
            for candidate in forward_neighbors
        ]
        no_forward_interface = len(forward_neighbors) == 0
        forward_avg = _mean(forward_values)
        forward_min = min(forward_values) if forward_values else 0.0
        queue_neighbor = (
            forward_avg
            if queue_state["mode"] == "interface_nonreturn_avg"
            else forward_min
        )
        metrics.update(
            {
                "queue_current": queue_current,
                "queue_neighbor": queue_neighbor,
                "queue_current_out_interface": queue_current,
                "queue_neighbor_forward_avg": forward_avg,
                "queue_neighbor_forward_min": forward_min,
                "neighbor_forward_interfaces": ";".join(
                    "%d->%d" % (neighbor, candidate)
                    for candidate in sorted(forward_neighbors)
                ),
                "interface_queue_source_available": (
                    queue_state["queue_file_exists"] and not no_forward_interface
                ),
                "nonreturn_interface_count": len(forward_neighbors),
                "no_forward_interface": no_forward_interface,
            }
        )
        return metrics

    totals = queue_state["node_totals"]
    queue_current = float(totals.get(current, 0.0))
    queue_neighbor = float(totals.get(neighbor, 0.0))
    metrics.update(
        {
            "queue_current": queue_current,
            "queue_neighbor": queue_neighbor,
        }
    )
    return metrics


def _shortest_distance_to_ground_station(dist_sat_net_without_gs, dst_gid, dst_candidates):
    possibilities = []
    for current_sat in range(dist_sat_net_without_gs.shape[0]):
        best = float("inf")
        for gsl_cost, dst_sat in dst_candidates:
            if not math.isinf(dist_sat_net_without_gs[(current_sat, dst_sat)]):
                best = min(best, float(dist_sat_net_without_gs[(current_sat, dst_sat)]) + float(gsl_cost))
        possibilities.append(best)
    return possibilities


def _distance_to_ground_station(metric_matrix, current_sat, dst_candidates):
    best = float("inf")
    for _, dst_sat in dst_candidates:
        try:
            distance = float(metric_matrix[(current_sat, dst_sat)])
        except (IndexError, KeyError, TypeError):
            continue
        if not math.isinf(distance):
            best = min(best, distance)
    return best


def _format_distance(value):
    if value is None or math.isinf(float(value)):
        return ""
    return float(value)


def _forward_progress_metric(loop_guard_mode):
    if loop_guard_mode == "forward_progress_hop":
        return "hop"
    if loop_guard_mode == "forward_progress_distance":
        return "distance"
    return "none"


def _shortest_path_fallback_decision(
    current,
    dst_gid,
    sat_graph,
    dist_sat_net_without_gs,
    ground_station_satellites_in_range,
    sat_neighbor_to_if,
):
    candidates = []
    dst_candidates = ground_station_satellites_in_range[dst_gid]
    for neighbor in sat_graph.neighbors(current):
        if neighbor == current:
            continue
        for gsl_cost, dst_sat in dst_candidates:
            if math.isinf(dist_sat_net_without_gs[(neighbor, dst_sat)]):
                continue
            total_cost = (
                float(sat_graph.edges[(current, neighbor)]["weight"])
                + float(dist_sat_net_without_gs[(neighbor, dst_sat)])
                + float(gsl_cost)
            )
            candidates.append((total_cost, neighbor))
    if not candidates:
        return (-1, -1, -1)
    _, neighbor = min(candidates, key=lambda item: (item[0], item[1]))
    return (
        neighbor,
        sat_neighbor_to_if[(current, neighbor)],
        sat_neighbor_to_if[(neighbor, current)],
    )


def _direct_gsl_delivery_decision(
    current,
    dst_gid,
    ground_station_satellites_in_range,
    num_satellites,
    num_isls_per_sat,
    gid_to_sat_gsl_if_idx,
):
    for _, dst_sat in ground_station_satellites_in_range[dst_gid]:
        if dst_sat == current:
            dst_gs_node_id = num_satellites + dst_gid
            return (
                dst_gs_node_id,
                num_isls_per_sat[current] + gid_to_sat_gsl_if_idx[dst_gid],
                0,
            )
    return None


def _select_backpressure_next_hop(
    current,
    dst_gid,
    sat_graph,
    dist_sat_net_without_gs,
    forward_progress_matrix,
    ground_station_satellites_in_range,
    sat_neighbor_to_if,
    queue_state,
    fallback_policy,
    link_capacity_bps,
    loop_guard_mode=DEFAULT_LOOP_GUARD,
):
    candidates = []
    legal_candidates = []
    dst_candidates = ground_station_satellites_in_range[dst_gid]
    progress_metric = _forward_progress_metric(loop_guard_mode)
    current_progress_distance = None
    if loop_guard_mode in ("forward_progress_hop", "forward_progress_distance"):
        current_progress_distance = _distance_to_ground_station(
            forward_progress_matrix,
            current,
            dst_candidates,
        )
    for neighbor in sat_graph.neighbors(current):
        if neighbor == current:
            continue
        candidate = _queue_pair_for_candidate(
            queue_state,
            current,
            neighbor,
            sat_graph,
        )
        queue_current = candidate["queue_current"]
        queue_neighbor = candidate["queue_neighbor"]
        queue_diff = max(queue_current - queue_neighbor, 0.0)
        weight = queue_diff * float(link_capacity_bps)
        if candidate["no_forward_interface"]:
            weight = 0.0
        candidate["queue_diff"] = queue_diff
        candidate["weight"] = weight
        candidate["loop_guard_mode"] = loop_guard_mode
        candidate["forward_progress_metric"] = progress_metric
        candidate["current_distance_to_destination"] = ""
        candidate["candidate_distance_to_destination"] = ""
        candidate["current_hop_distance_to_destination"] = ""
        candidate["candidate_hop_distance_to_destination"] = ""
        candidate["candidate_is_forward_progress"] = True
        candidate["candidate_filtered_by_loop_guard"] = False
        candidate["forward_progress_distance_missing"] = False
        legal = True
        if loop_guard_mode in ("forward_progress_hop", "forward_progress_distance"):
            candidate_progress_distance = _distance_to_ground_station(
                forward_progress_matrix,
                neighbor,
                dst_candidates,
            )
            missing_distance = (
                math.isinf(current_progress_distance)
                or math.isinf(candidate_progress_distance)
            )
            is_forward_progress = (
                not missing_distance
                and candidate_progress_distance < current_progress_distance
            )
            legal = is_forward_progress
            candidate["candidate_is_forward_progress"] = is_forward_progress
            candidate["candidate_filtered_by_loop_guard"] = not legal
            candidate["forward_progress_distance_missing"] = missing_distance
            candidate["current_distance_to_destination"] = _format_distance(
                current_progress_distance
            )
            candidate["candidate_distance_to_destination"] = _format_distance(
                candidate_progress_distance
            )
            if loop_guard_mode == "forward_progress_hop":
                candidate["current_hop_distance_to_destination"] = _format_distance(
                    current_progress_distance
                )
                candidate["candidate_hop_distance_to_destination"] = _format_distance(
                    candidate_progress_distance
                )
        elif loop_guard_mode == "immediate_reverse":
            # The installed fstate is keyed by current node and destination only;
            # it cannot express previous-hop-dependent forwarding. Keep this mode
            # observable in diagnostics, but do not filter candidates here.
            legal = True
        if not legal:
            candidate["weight"] = 0.0
        candidates.append(candidate)
        if legal:
            legal_candidates.append(candidate)

    if not candidates:
        return {
            "decision": (-1, -1, -1),
            "selected_candidate": None,
            "selected_positive_pressure": False,
            "fallback_used": fallback_policy == "shortest_path",
            "fallback_reason": "no_candidate",
        }

    for item in candidates:
        item["legal_candidate_count"] = len(legal_candidates)
        item["illegal_candidate_count"] = len(candidates) - len(legal_candidates)
        item["total_candidates_before_guard"] = len(candidates)
        item["total_candidates_after_guard"] = len(legal_candidates)
        item["selected_after_loop_guard"] = item in legal_candidates

    if not legal_candidates:
        if any(item["forward_progress_distance_missing"] for item in candidates):
            fallback_reason = "missing_forward_progress_distance"
        else:
            fallback_reason = "no_legal_forward_progress_candidate"
        if fallback_policy == "no_route":
            return {
                "decision": (-1, -1, -1),
                "selected_candidate": max(
                    candidates,
                    key=lambda item: (item["queue_diff"], -item["neighbor"]),
                ),
                "selected_positive_pressure": False,
                "fallback_used": False,
                "fallback_reason": fallback_reason,
            }
        decision = _shortest_path_fallback_decision(
            current,
            dst_gid,
            sat_graph,
            dist_sat_net_without_gs,
            ground_station_satellites_in_range,
            sat_neighbor_to_if,
        )
        selected_neighbor = decision[0]
        selected_candidate = None
        for item in candidates:
            if item["neighbor"] == selected_neighbor:
                selected_candidate = item
                break
        if selected_candidate is None:
            selected_candidate = max(
                candidates,
                key=lambda item: (item["queue_diff"], -item["neighbor"]),
            )
        return {
            "decision": decision,
            "selected_candidate": selected_candidate,
            "selected_positive_pressure": False,
            "fallback_used": True,
            "fallback_reason": fallback_reason if selected_neighbor != -1 else "no_candidate",
        }

    positive = [item for item in legal_candidates if item["weight"] > 0.0]
    if positive:
        selected = min(
            positive,
            key=lambda item: (-item["weight"], item["neighbor"]),
        )
        neighbor = selected["neighbor"]
        return {
            "decision": (
                neighbor,
                sat_neighbor_to_if[(current, neighbor)],
                sat_neighbor_to_if[(neighbor, current)],
            ),
            "selected_candidate": selected,
            "selected_positive_pressure": True,
            "fallback_used": False,
            "fallback_reason": "",
        }

    if loop_guard_mode in ("forward_progress_hop", "forward_progress_distance"):
        fallback_reason = "no_positive_pressure_after_forward_progress_filter"
    elif any(item["no_forward_interface"] for item in candidates):
        fallback_reason = "no_forward_interface"
    else:
        fallback_reason = "missing_queue" if not queue_state["queue_file_exists"] else "no_positive_pressure"
    if fallback_policy == "no_route":
        return {
            "decision": (-1, -1, -1),
            "selected_candidate": max(
                legal_candidates,
                key=lambda item: (item["weight"], -item["neighbor"]),
            ),
            "selected_positive_pressure": False,
            "fallback_used": False,
            "fallback_reason": fallback_reason,
        }

    decision = _shortest_path_fallback_decision(
        current,
        dst_gid,
        sat_graph,
        dist_sat_net_without_gs,
        ground_station_satellites_in_range,
        sat_neighbor_to_if,
    )
    selected_neighbor = decision[0]
    selected_candidate = None
    for item in candidates:
        if item["neighbor"] == selected_neighbor:
            selected_candidate = item
            break
    if selected_candidate is None:
        selected_candidate = max(
            legal_candidates,
            key=lambda item: (item["weight"], -item["neighbor"]),
        )
    return {
        "decision": decision,
        "selected_candidate": selected_candidate,
        "selected_positive_pressure": False,
        "fallback_used": True,
        "fallback_reason": fallback_reason if selected_neighbor != -1 else "no_candidate",
    }


def _build_full_graph(num_satellites, num_ground_stations, sat_graph, ground_station_satellites_in_range):
    full_graph = sat_graph.copy()
    for node_id in range(num_satellites, num_satellites + num_ground_stations):
        full_graph.add_node(node_id)
    for gid, candidates in enumerate(ground_station_satellites_in_range):
        gs_node = num_satellites + gid
        for _, sat_id in candidates:
            full_graph.add_edge(gs_node, sat_id, weight=1)
    return full_graph


def _trace_fstate_path(src, dst, fstate, max_hops=1000):
    if (src, dst) not in fstate:
        return [src], False, False
    current = src
    path = [src]
    visited = {src}
    while current != dst:
        if len(path) > max_hops:
            return path, False, True
        decision = fstate.get((current, dst))
        if decision is None:
            return path, False, False
        next_hop = decision[0] if isinstance(decision, tuple) else decision
        if next_hop == -1:
            return path, False, False
        path.append(next_hop)
        if next_hop in visited:
            return path, False, True
        visited.add(next_hop)
        current = next_hop
    return path, True, False


def _format_path(path):
    return "->".join(str(item) for item in path)


def _diagnostic_pairs_or_focus(diagnostic_pairs):
    pairs = []
    for pair in diagnostic_pairs or []:
        if pair and len(pair) == 2:
            pairs.append((int(pair[0]), int(pair[1])))
    return sorted(set(pairs))


def _write_diagnostics(
    output_dynamic_state_dir,
    time_since_epoch_ns,
    num_satellites,
    num_ground_stations,
    fstate,
    decision_infos,
    queue_state,
    fallback_policy,
    loop_guard_mode,
    diagnostics_sample_limit,
    diagnostic_pairs,
    sat_graph,
    ground_station_satellites_in_range,
):
    algorithm_run_dir = os.path.dirname(os.path.abspath(output_dynamic_state_dir))
    run_dir = os.path.dirname(algorithm_run_dir)
    scenario_id = os.path.basename(run_dir)
    diagnostics_dir = os.path.join(algorithm_run_dir, "backpressure_diagnostics")
    os.makedirs(diagnostics_dir, exist_ok=True)

    full_graph = _build_full_graph(
        num_satellites,
        num_ground_stations,
        sat_graph,
        ground_station_satellites_in_range,
    )
    path_rows = []
    diagnostic_keys = set()
    loop_detected_paths = 0
    reached_paths = 0
    stretches = []
    for src, dst in _diagnostic_pairs_or_focus(diagnostic_pairs):
        path, reached, loop_detected = _trace_fstate_path(src, dst, fstate)
        if loop_detected:
            loop_detected_paths += 1
        if reached:
            reached_paths += 1
        hop_count = max(0, len(path) - 1)
        try:
            shortest_hops = nx.shortest_path_length(full_graph, src, dst)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            shortest_hops = ""
        path_stretch = ""
        if isinstance(shortest_hops, int) and shortest_hops > 0:
            path_stretch = hop_count / float(shortest_hops)
            stretches.append(path_stretch)
        fallback_count = 0
        positive_count = 0
        for node in path:
            key = (node, dst)
            if key in decision_infos:
                diagnostic_keys.add(key)
                info = decision_infos[key]
                if info["fallback_used"]:
                    fallback_count += 1
                if info["selected_positive_pressure"]:
                    positive_count += 1
        path_rows.append(
            {
                "time": time_since_epoch_ns / 1e9,
                "time_ns": time_since_epoch_ns,
                "loop_guard_mode": loop_guard_mode,
                "src": src,
                "dst": dst,
                "path": _format_path(path),
                "hop_count": hop_count,
                "shortest_path_hop_count": shortest_hops,
                "path_stretch": path_stretch,
                "loop_detected": _bool_text(loop_detected),
                "reached_destination": _bool_text(reached),
                "fallback_count_on_path": fallback_count,
                "positive_pressure_count_on_path": positive_count,
            }
        )

    path_fields = [
        "time",
        "time_ns",
        "loop_guard_mode",
        "src",
        "dst",
        "path",
        "hop_count",
        "shortest_path_hop_count",
        "path_stretch",
        "loop_detected",
        "reached_destination",
        "fallback_count_on_path",
        "positive_pressure_count_on_path",
    ]
    _append_csv(
        os.path.join(diagnostics_dir, "backpressure_path_stretch_summary.csv"),
        path_fields,
        path_rows,
    )
    _append_csv(
        os.path.join(diagnostics_dir, "backpressure_loop_check.csv"),
        path_fields,
        path_rows,
    )

    sorted_keys = sorted(decision_infos)
    keys_to_log = []
    seen = set()
    for key in sorted(diagnostic_keys):
        if key in decision_infos and key not in seen:
            keys_to_log.append(key)
            seen.add(key)
    for key in sorted_keys:
        if diagnostics_sample_limit and diagnostics_sample_limit > 0 and len(keys_to_log) >= diagnostics_sample_limit:
            break
        if key not in seen:
            keys_to_log.append(key)
            seen.add(key)

    decision_rows = []
    for key in keys_to_log:
        info = decision_infos[key]
        selected_next_hop = info["selected_next_hop"]
        candidate_link = ""
        if selected_next_hop != -1:
            candidate_link = "%d->%d" % (info["current_node"], selected_next_hop)
        decision_rows.append(
            {
                "time_ns": time_since_epoch_ns,
                "current_node": info["current_node"],
                "destination": info["destination"],
                "candidate_neighbor": selected_next_hop if selected_next_hop != -1 else "",
                "candidate_link": candidate_link,
                "queue_current": info["queue_current"],
                "queue_neighbor": info["queue_neighbor"],
                "queue_diff": info["queue_diff"],
                "link_capacity_bps": info["link_capacity_bps"],
                "weight": info["weight"],
                "selected_next_hop": selected_next_hop,
                "selected_weight": info["weight"],
                "selected_positive_pressure": _bool_text(info["selected_positive_pressure"]),
                "fallback_used": _bool_text(info["fallback_used"]),
                "fallback_reason": info["fallback_reason"],
                "loop_guard_mode": info.get("loop_guard_mode", loop_guard_mode),
                "forward_progress_metric": info.get("forward_progress_metric", "none"),
                "current_distance_to_destination": info.get("current_distance_to_destination", ""),
                "candidate_distance_to_destination": info.get("candidate_distance_to_destination", ""),
                "current_hop_distance_to_destination": info.get("current_hop_distance_to_destination", ""),
                "candidate_hop_distance_to_destination": info.get("candidate_hop_distance_to_destination", ""),
                "candidate_is_forward_progress": _bool_text(
                    info.get("candidate_is_forward_progress", True)
                ),
                "candidate_filtered_by_loop_guard": _bool_text(
                    info.get("candidate_filtered_by_loop_guard", False)
                ),
                "legal_candidate_count": info.get("legal_candidate_count", 0),
                "illegal_candidate_count": info.get("illegal_candidate_count", 0),
                "selected_after_loop_guard": _bool_text(
                    info.get("selected_after_loop_guard", True)
                ),
                "two_hop_ping_pong": _bool_text(info.get("two_hop_ping_pong", False)),
                "current_out_interface": info.get("current_out_interface", ""),
                "neighbor_return_interface": info.get("neighbor_return_interface", ""),
                "neighbor_forward_interfaces": info.get("neighbor_forward_interfaces", ""),
                "queue_current_out_interface": info.get("queue_current_out_interface", 0.0),
                "queue_neighbor_forward_avg": info.get("queue_neighbor_forward_avg", 0.0),
                "queue_neighbor_forward_min": info.get("queue_neighbor_forward_min", 0.0),
                "interface_queue_source_available": _bool_text(
                    info.get("interface_queue_source_available", False)
                ),
                "nonreturn_interface_count": info.get("nonreturn_interface_count", 0),
                "queue_source": queue_state["effective_source"],
                "commodity_mode": COMMODITY_MODE,
            }
        )

    decision_fields = [
        "time_ns",
        "current_node",
        "destination",
        "candidate_neighbor",
        "candidate_link",
        "queue_current",
        "queue_neighbor",
        "queue_diff",
        "link_capacity_bps",
        "weight",
        "selected_next_hop",
        "selected_weight",
        "selected_positive_pressure",
        "fallback_used",
        "fallback_reason",
        "loop_guard_mode",
        "forward_progress_metric",
        "current_distance_to_destination",
        "candidate_distance_to_destination",
        "current_hop_distance_to_destination",
        "candidate_hop_distance_to_destination",
        "candidate_is_forward_progress",
        "candidate_filtered_by_loop_guard",
        "legal_candidate_count",
        "illegal_candidate_count",
        "selected_after_loop_guard",
        "two_hop_ping_pong",
        "current_out_interface",
        "neighbor_return_interface",
        "neighbor_forward_interfaces",
        "queue_current_out_interface",
        "queue_neighbor_forward_avg",
        "queue_neighbor_forward_min",
        "interface_queue_source_available",
        "nonreturn_interface_count",
        "queue_source",
        "commodity_mode",
    ]
    _append_csv(
        os.path.join(diagnostics_dir, "backpressure_decision_log.csv"),
        decision_fields,
        decision_rows,
    )

    reasons = Counter(info["fallback_reason"] for info in decision_infos.values() if info["fallback_reason"])
    selected_weights = [info["weight"] for info in decision_infos.values()]
    queue_diffs = [info["queue_diff"] for info in decision_infos.values()]
    total_decisions = len(decision_infos)
    positive_count = sum(1 for info in decision_infos.values() if info["selected_positive_pressure"])
    fallback_count = sum(1 for info in decision_infos.values() if info["fallback_used"])
    ping_pong_count = sum(1 for info in decision_infos.values() if info.get("two_hop_ping_pong", False))
    interface_success_count = sum(
        1 for info in decision_infos.values()
        if info.get("interface_queue_source_available", False)
    )
    no_forward_interface_count = sum(
        1 for info in decision_infos.values()
        if info.get("no_forward_interface", False)
    )
    interface_mapping_missing_count = sum(
        1 for info in decision_infos.values()
        if info.get("interface_mapping_missing", False)
    )
    total_candidates_before_guard = sum(
        int(info.get("total_candidates_before_guard", 0))
        for info in decision_infos.values()
    )
    total_candidates_after_guard = sum(
        int(info.get("total_candidates_after_guard", 0))
        for info in decision_infos.values()
    )
    total_candidates_filtered = max(
        0,
        total_candidates_before_guard - total_candidates_after_guard,
    )
    path_count = len(path_rows)
    summary_row = {
        "time_ns": time_since_epoch_ns,
        "scenario_id": scenario_id,
        "algorithm": ALGORITHM_NAME,
        "loop_guard_mode": loop_guard_mode,
        "total_decisions": total_decisions,
        "positive_pressure_decisions": positive_count,
        "fallback_decisions": fallback_count,
        "no_positive_pressure_count": reasons.get("no_positive_pressure", 0),
        "missing_queue_count": reasons.get("missing_queue", 0),
        "no_candidate_count": reasons.get("no_candidate", 0),
        "fallback_no_legal_forward_progress_count": (
            reasons.get("no_legal_forward_progress_candidate", 0)
            + reasons.get("missing_forward_progress_distance", 0)
        ),
        "fallback_no_positive_pressure_after_guard_count": reasons.get(
            "no_positive_pressure_after_forward_progress_filter",
            0,
        ),
        "no_forward_interface_count": no_forward_interface_count,
        "interface_mapping_missing_count": interface_mapping_missing_count,
        "interface_source_success_ratio": (
            interface_success_count / float(total_decisions)
            if total_decisions
            else 0.0
        ),
        "total_candidates_before_guard": total_candidates_before_guard,
        "total_candidates_after_guard": total_candidates_after_guard,
        "candidate_filter_ratio": (
            total_candidates_filtered / float(total_candidates_before_guard)
            if total_candidates_before_guard
            else 0.0
        ),
        "forward_progress_success_ratio": (
            total_candidates_after_guard / float(total_candidates_before_guard)
            if total_candidates_before_guard
            else 0.0
        ),
        "avg_selected_weight": _mean(selected_weights),
        "p95_selected_weight": _p95(selected_weights),
        "avg_queue_diff": _mean(queue_diffs),
        "p95_queue_diff": _p95(queue_diffs),
        "loop_detected_paths": loop_detected_paths,
        "loop_detected_ratio": (
            loop_detected_paths / float(path_count) if path_count else 0.0
        ),
        "reached_destination_ratio": (
            reached_paths / float(path_count) if path_count else 0.0
        ),
        "two_hop_ping_pong_decisions": ping_pong_count,
        "avg_path_stretch": _mean(stretches),
        "p95_path_stretch": _p95(stretches),
        "queue_source": queue_state["effective_source"],
        "commodity_mode": COMMODITY_MODE,
    }
    summary_fields = [
        "time_ns",
        "scenario_id",
        "algorithm",
        "loop_guard_mode",
        "total_decisions",
        "positive_pressure_decisions",
        "fallback_decisions",
        "no_positive_pressure_count",
        "missing_queue_count",
        "no_candidate_count",
        "fallback_no_legal_forward_progress_count",
        "fallback_no_positive_pressure_after_guard_count",
        "no_forward_interface_count",
        "interface_mapping_missing_count",
        "interface_source_success_ratio",
        "total_candidates_before_guard",
        "total_candidates_after_guard",
        "candidate_filter_ratio",
        "forward_progress_success_ratio",
        "avg_selected_weight",
        "p95_selected_weight",
        "avg_queue_diff",
        "p95_queue_diff",
        "loop_detected_paths",
        "loop_detected_ratio",
        "reached_destination_ratio",
        "two_hop_ping_pong_decisions",
        "avg_path_stretch",
        "p95_path_stretch",
        "queue_source",
        "commodity_mode",
    ]
    _append_csv(
        os.path.join(diagnostics_dir, "backpressure_summary.csv"),
        summary_fields,
        [summary_row],
    )

    queue_row = {
        "time_ns": time_since_epoch_ns,
        "requested_queue_source": queue_state["requested_source"],
        "effective_queue_source": queue_state["effective_source"],
        "queue_source": queue_state["effective_source"],
        "loop_guard_mode": loop_guard_mode,
        "backpressure_forward_progress_metric": _forward_progress_metric(loop_guard_mode),
        "commodity_mode": COMMODITY_MODE,
        "is_restricted_route_backpressure": _bool_text(loop_guard_mode != "none"),
        "is_full_multi_commodity": "false",
        "per_destination_queue_available": _bool_text(queue_state["per_destination_available"]),
        "queue_file_exists": _bool_text(queue_state["queue_file_exists"]),
        "queue_record_count": len(queue_state["link_values"]),
        "node_count_with_queue": len(queue_state["node_totals"]),
        "interface_count_with_queue": len(queue_state["link_values"]),
    }
    queue_fields = [
        "time_ns",
        "requested_queue_source",
        "effective_queue_source",
        "queue_source",
        "loop_guard_mode",
        "backpressure_forward_progress_metric",
        "commodity_mode",
        "is_restricted_route_backpressure",
        "is_full_multi_commodity",
        "per_destination_queue_available",
        "queue_file_exists",
        "queue_record_count",
        "node_count_with_queue",
        "interface_count_with_queue",
    ]
    _append_csv(
        os.path.join(diagnostics_dir, "backpressure_queue_source_summary.csv"),
        queue_fields,
        [queue_row],
    )

    fallback_row = {
        "time_ns": time_since_epoch_ns,
        "fallback_policy": fallback_policy,
        "loop_guard_mode": loop_guard_mode,
        "total_decisions": total_decisions,
        "fallback_decisions": fallback_count,
        "fallback_ratio": fallback_count / float(total_decisions) if total_decisions else 0.0,
        "positive_pressure_decisions": positive_count,
        "positive_pressure_ratio": positive_count / float(total_decisions) if total_decisions else 0.0,
        "no_positive_pressure_count": reasons.get("no_positive_pressure", 0),
        "no_positive_pressure_after_guard_count": reasons.get(
            "no_positive_pressure_after_forward_progress_filter",
            0,
        ),
        "no_legal_forward_progress_count": reasons.get(
            "no_legal_forward_progress_candidate",
            0,
        ),
        "missing_forward_progress_distance_count": reasons.get(
            "missing_forward_progress_distance",
            0,
        ),
        "missing_queue_count": reasons.get("missing_queue", 0),
        "no_candidate_count": reasons.get("no_candidate", 0),
        "no_forward_interface_count": reasons.get("no_forward_interface", 0),
    }
    fallback_fields = [
        "time_ns",
        "fallback_policy",
        "loop_guard_mode",
        "total_decisions",
        "fallback_decisions",
        "fallback_ratio",
        "positive_pressure_decisions",
        "positive_pressure_ratio",
        "no_positive_pressure_count",
        "no_positive_pressure_after_guard_count",
        "no_legal_forward_progress_count",
        "missing_forward_progress_distance_count",
        "missing_queue_count",
        "no_candidate_count",
        "no_forward_interface_count",
    ]
    _append_csv(
        os.path.join(diagnostics_dir, "backpressure_fallback_summary.csv"),
        fallback_fields,
        [fallback_row],
    )


def algorithm_backpressure_over_isls(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        satellites,
        ground_stations,
        sat_net_graph_only_satellites_with_isls,
        ground_station_satellites_in_range,
        num_isls_per_sat,
        sat_neighbor_to_if,
        list_gsl_interfaces_info,
        prev_output,
        enable_verbose_logs,
        queue_stats_file=None,
        isl_link_capacity_bps=None,
        backpressure_queue_source=DEFAULT_QUEUE_SOURCE,
        backpressure_fallback=DEFAULT_FALLBACK,
        backpressure_loop_guard=DEFAULT_LOOP_GUARD,
        backpressure_diagnostics_enabled=True,
        backpressure_diagnostics_sample_limit=DEFAULT_DIAGNOSTIC_SAMPLE_LIMIT,
        diagnostic_pairs=None,
):
    if enable_verbose_logs:
        print("\nALGORITHM: SIMPLE BACKPRESSURE OVER ISLS")

    fallback_policy = normalize_backpressure_fallback(backpressure_fallback)
    loop_guard_mode = normalize_backpressure_loop_guard(backpressure_loop_guard)
    queue_state = _load_proxy_queue_state(
        queue_stats_file,
        len(satellites),
        backpressure_queue_source,
    )
    link_capacity_bps = (
        DEFAULT_ISL_LINK_CAPACITY_BPS
        if isl_link_capacity_bps is None
        else float(isl_link_capacity_bps)
    )

    if enable_verbose_logs:
        print("  > Queue source requested: %s" % queue_state["requested_source"])
        print("  > Queue source effective: %s" % queue_state["effective_source"])
        print("  > Commodity mode: %s" % COMMODITY_MODE)
        print("  > Fallback policy: %s" % fallback_policy)
        print("  > Loop guard mode: %s" % loop_guard_mode)
        print("  > Forward-progress metric: %s" % _forward_progress_metric(loop_guard_mode))

    _write_gsl_if_bandwidth(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        satellites,
        ground_stations,
        num_isls_per_sat,
        list_gsl_interfaces_info,
        enable_verbose_logs,
    )

    if enable_verbose_logs:
        print("  > Calculating shortest-path matrix for fallback and diagnostics")
    dist_sat_net_without_gs = nx.floyd_warshall_numpy(
        sat_net_graph_only_satellites_with_isls
    )
    forward_progress_matrix = dist_sat_net_without_gs
    if loop_guard_mode == "forward_progress_hop":
        forward_progress_matrix = nx.floyd_warshall_numpy(
            sat_net_graph_only_satellites_with_isls,
            weight="hop_weight",
        )

    num_satellites = len(satellites)
    num_ground_stations = len(ground_stations)
    gid_to_sat_gsl_if_idx = [0] * num_ground_stations
    prev_fstate = prev_output["fstate"] if prev_output is not None else None
    fstate = {}
    decision_infos = {}

    output_filename = output_dynamic_state_dir + "/fstate_" + str(time_since_epoch_ns) + ".txt"
    if enable_verbose_logs:
        print("  > Writing forwarding state to: " + output_filename)

    with open(output_filename, "w+") as f_out:
        for curr in range(num_satellites):
            for dst_gid in range(num_ground_stations):
                dst_gs_node_id = num_satellites + dst_gid
                direct_decision = _direct_gsl_delivery_decision(
                    curr,
                    dst_gid,
                    ground_station_satellites_in_range,
                    num_satellites,
                    num_isls_per_sat,
                    gid_to_sat_gsl_if_idx,
                )
                if direct_decision is not None:
                    next_hop_decision = direct_decision
                    selected_candidate = _empty_candidate_metrics(curr, dst_gs_node_id)
                    selected_positive = False
                    fallback_used = False
                    fallback_reason = "direct_gsl_delivery"
                else:
                    selection = _select_backpressure_next_hop(
                        curr,
                        dst_gid,
                        sat_net_graph_only_satellites_with_isls,
                        dist_sat_net_without_gs,
                        forward_progress_matrix,
                        ground_station_satellites_in_range,
                        sat_neighbor_to_if,
                        queue_state,
                        fallback_policy,
                        link_capacity_bps,
                        loop_guard_mode,
                    )
                    next_hop_decision = selection["decision"]
                    selected_candidate = selection["selected_candidate"]
                    selected_positive = selection["selected_positive_pressure"]
                    fallback_used = selection["fallback_used"]
                    fallback_reason = selection["fallback_reason"]

                fstate_key = (curr, dst_gs_node_id)
                if not prev_fstate or prev_fstate.get(fstate_key) != next_hop_decision:
                    f_out.write(
                        "%d,%d,%d,%d,%d\n"
                        % (
                            curr,
                            dst_gs_node_id,
                            next_hop_decision[0],
                            next_hop_decision[1],
                            next_hop_decision[2],
                        )
                    )
                fstate[fstate_key] = next_hop_decision
                if selected_candidate is None:
                    selected_candidate = _empty_candidate_metrics(curr, -1)
                selected_candidate["loop_guard_mode"] = loop_guard_mode
                selected_candidate["forward_progress_metric"] = _forward_progress_metric(
                    loop_guard_mode
                )
                decision_infos[fstate_key] = {
                    "current_node": curr,
                    "destination": dst_gs_node_id,
                    "selected_next_hop": next_hop_decision[0],
                    "queue_current": selected_candidate["queue_current"],
                    "queue_neighbor": selected_candidate["queue_neighbor"],
                    "queue_diff": selected_candidate["queue_diff"],
                    "weight": selected_candidate["weight"],
                    "current_out_interface": selected_candidate["current_out_interface"],
                    "neighbor_return_interface": selected_candidate["neighbor_return_interface"],
                    "neighbor_forward_interfaces": selected_candidate["neighbor_forward_interfaces"],
                    "queue_current_out_interface": selected_candidate["queue_current_out_interface"],
                    "queue_neighbor_forward_avg": selected_candidate["queue_neighbor_forward_avg"],
                    "queue_neighbor_forward_min": selected_candidate["queue_neighbor_forward_min"],
                    "interface_queue_source_available": selected_candidate["interface_queue_source_available"],
                    "nonreturn_interface_count": selected_candidate["nonreturn_interface_count"],
                    "no_forward_interface": selected_candidate["no_forward_interface"],
                    "interface_mapping_missing": selected_candidate["interface_mapping_missing"],
                    "loop_guard_mode": selected_candidate["loop_guard_mode"],
                    "forward_progress_metric": selected_candidate["forward_progress_metric"],
                    "current_distance_to_destination": selected_candidate[
                        "current_distance_to_destination"
                    ],
                    "candidate_distance_to_destination": selected_candidate[
                        "candidate_distance_to_destination"
                    ],
                    "current_hop_distance_to_destination": selected_candidate[
                        "current_hop_distance_to_destination"
                    ],
                    "candidate_hop_distance_to_destination": selected_candidate[
                        "candidate_hop_distance_to_destination"
                    ],
                    "candidate_is_forward_progress": selected_candidate[
                        "candidate_is_forward_progress"
                    ],
                    "candidate_filtered_by_loop_guard": selected_candidate[
                        "candidate_filtered_by_loop_guard"
                    ],
                    "legal_candidate_count": selected_candidate["legal_candidate_count"],
                    "illegal_candidate_count": selected_candidate["illegal_candidate_count"],
                    "total_candidates_before_guard": selected_candidate[
                        "total_candidates_before_guard"
                    ],
                    "total_candidates_after_guard": selected_candidate[
                        "total_candidates_after_guard"
                    ],
                    "selected_after_loop_guard": selected_candidate[
                        "selected_after_loop_guard"
                    ],
                    "forward_progress_distance_missing": selected_candidate[
                        "forward_progress_distance_missing"
                    ],
                    "link_capacity_bps": link_capacity_bps,
                    "selected_positive_pressure": selected_positive,
                    "fallback_used": fallback_used,
                    "fallback_reason": fallback_reason,
                }

        dist_to_ground_station = {}
        for dst_gid in range(num_ground_stations):
            distances = _shortest_distance_to_ground_station(
                dist_sat_net_without_gs,
                dst_gid,
                ground_station_satellites_in_range[dst_gid],
            )
            for sat_id, distance in enumerate(distances):
                dist_to_ground_station[(sat_id, num_satellites + dst_gid)] = distance

        for src_gid in range(num_ground_stations):
            for dst_gid in range(num_ground_stations):
                if src_gid == dst_gid:
                    continue
                src_gs_node_id = num_satellites + src_gid
                dst_gs_node_id = num_satellites + dst_gid
                possibilities = []
                for gsl_cost, src_sat in ground_station_satellites_in_range[src_gid]:
                    offered = dist_to_ground_station.get((src_sat, dst_gs_node_id), float("inf"))
                    if not math.isinf(offered):
                        possibilities.append((float(gsl_cost) + float(offered), src_sat))
                next_hop_decision = (-1, -1, -1)
                if possibilities:
                    _, src_sat_id = min(possibilities, key=lambda item: (item[0], item[1]))
                    next_hop_decision = (
                        src_sat_id,
                        0,
                        num_isls_per_sat[src_sat_id] + gid_to_sat_gsl_if_idx[src_gid],
                    )
                fstate_key = (src_gs_node_id, dst_gs_node_id)
                if not prev_fstate or prev_fstate.get(fstate_key) != next_hop_decision:
                    f_out.write(
                        "%d,%d,%d,%d,%d\n"
                        % (
                            src_gs_node_id,
                            dst_gs_node_id,
                            next_hop_decision[0],
                            next_hop_decision[1],
                            next_hop_decision[2],
                        )
                    )
                fstate[fstate_key] = next_hop_decision

    for (current, destination), info in decision_infos.items():
        next_hop = info["selected_next_hop"]
        info["two_hop_ping_pong"] = False
        if 0 <= next_hop < num_satellites:
            neighbor_decision = fstate.get((next_hop, destination))
            if neighbor_decision is not None and neighbor_decision[0] == current:
                info["two_hop_ping_pong"] = True

    if backpressure_diagnostics_enabled:
        _write_diagnostics(
            output_dynamic_state_dir,
            time_since_epoch_ns,
            num_satellites,
            num_ground_stations,
            fstate,
            decision_infos,
            queue_state,
            fallback_policy,
            loop_guard_mode,
            int(backpressure_diagnostics_sample_limit),
            diagnostic_pairs,
            sat_net_graph_only_satellites_with_isls,
            ground_station_satellites_in_range,
        )

    if enable_verbose_logs:
        print("")

    return {
        "fstate": fstate,
        "backpressure_queue_source": queue_state["effective_source"],
        "backpressure_requested_queue_source": queue_state["requested_source"],
        "backpressure_commodity_mode": COMMODITY_MODE,
        "backpressure_fallback": fallback_policy,
        "backpressure_loop_guard": loop_guard_mode,
        "backpressure_forward_progress_metric": _forward_progress_metric(loop_guard_mode),
        "backpressure_is_restricted_route": loop_guard_mode != "none",
        "backpressure_is_full_multi_commodity": False,
        "backpressure_capacity_multiplier_enabled": True,
    }
