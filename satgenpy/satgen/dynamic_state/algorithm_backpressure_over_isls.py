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
DEFAULT_DIAGNOSTIC_SAMPLE_LIMIT = 2000

QUEUE_SOURCE_ALIASES = {
    "auto": "auto",
    "per_destination_bytes": "per_destination_bytes",
    "per_destination_packets": "per_destination_packets",
    "node_total_bytes": "node_total_bytes",
    "node_total_packets": "node_total_packets",
    "interface_bytes": "interface_bytes",
    "interface_packets": "interface_packets",
}

FALLBACK_POLICIES = {"shortest_path", "no_route"}


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


def _queue_pair_for_candidate(queue_state, current, neighbor):
    if queue_state["mode"] == "interface":
        values = queue_state["link_values"]
        return (
            float(values.get((current, neighbor), 0.0)),
            float(values.get((neighbor, current), 0.0)),
        )
    totals = queue_state["node_totals"]
    return (float(totals.get(current, 0.0)), float(totals.get(neighbor, 0.0)))


def _shortest_distance_to_ground_station(dist_sat_net_without_gs, dst_gid, dst_candidates):
    possibilities = []
    for current_sat in range(dist_sat_net_without_gs.shape[0]):
        best = float("inf")
        for gsl_cost, dst_sat in dst_candidates:
            if not math.isinf(dist_sat_net_without_gs[(current_sat, dst_sat)]):
                best = min(best, float(dist_sat_net_without_gs[(current_sat, dst_sat)]) + float(gsl_cost))
        possibilities.append(best)
    return possibilities


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
    ground_station_satellites_in_range,
    sat_neighbor_to_if,
    queue_state,
    fallback_policy,
    link_capacity_bps,
):
    candidates = []
    for neighbor in sat_graph.neighbors(current):
        if neighbor == current:
            continue
        queue_current, queue_neighbor = _queue_pair_for_candidate(
            queue_state,
            current,
            neighbor,
        )
        queue_diff = max(queue_current - queue_neighbor, 0.0)
        weight = queue_diff * float(link_capacity_bps)
        candidates.append(
            {
                "neighbor": neighbor,
                "queue_current": queue_current,
                "queue_neighbor": queue_neighbor,
                "queue_diff": queue_diff,
                "weight": weight,
            }
        )

    if not candidates:
        return {
            "decision": (-1, -1, -1),
            "selected_candidate": None,
            "selected_positive_pressure": False,
            "fallback_used": fallback_policy == "shortest_path",
            "fallback_reason": "no_candidate",
        }

    positive = [item for item in candidates if item["weight"] > 0.0]
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

    fallback_reason = "missing_queue" if not queue_state["queue_file_exists"] else "no_positive_pressure"
    if fallback_policy == "no_route":
        return {
            "decision": (-1, -1, -1),
            "selected_candidate": max(
                candidates,
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
            candidates,
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
    stretches = []
    for src, dst in _diagnostic_pairs_or_focus(diagnostic_pairs):
        path, reached, loop_detected = _trace_fstate_path(src, dst, fstate)
        if loop_detected:
            loop_detected_paths += 1
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
                "two_hop_ping_pong": _bool_text(info.get("two_hop_ping_pong", False)),
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
        "two_hop_ping_pong",
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
    summary_row = {
        "time_ns": time_since_epoch_ns,
        "scenario_id": scenario_id,
        "algorithm": ALGORITHM_NAME,
        "total_decisions": total_decisions,
        "positive_pressure_decisions": positive_count,
        "fallback_decisions": fallback_count,
        "no_positive_pressure_count": reasons.get("no_positive_pressure", 0),
        "missing_queue_count": reasons.get("missing_queue", 0),
        "no_candidate_count": reasons.get("no_candidate", 0),
        "avg_selected_weight": _mean(selected_weights),
        "p95_selected_weight": _p95(selected_weights),
        "avg_queue_diff": _mean(queue_diffs),
        "p95_queue_diff": _p95(queue_diffs),
        "loop_detected_paths": loop_detected_paths,
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
        "total_decisions",
        "positive_pressure_decisions",
        "fallback_decisions",
        "no_positive_pressure_count",
        "missing_queue_count",
        "no_candidate_count",
        "avg_selected_weight",
        "p95_selected_weight",
        "avg_queue_diff",
        "p95_queue_diff",
        "loop_detected_paths",
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
        "commodity_mode": COMMODITY_MODE,
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
        "commodity_mode",
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
        "total_decisions": total_decisions,
        "fallback_decisions": fallback_count,
        "fallback_ratio": fallback_count / float(total_decisions) if total_decisions else 0.0,
        "positive_pressure_decisions": positive_count,
        "positive_pressure_ratio": positive_count / float(total_decisions) if total_decisions else 0.0,
        "no_positive_pressure_count": reasons.get("no_positive_pressure", 0),
        "missing_queue_count": reasons.get("missing_queue", 0),
        "no_candidate_count": reasons.get("no_candidate", 0),
    }
    fallback_fields = [
        "time_ns",
        "fallback_policy",
        "total_decisions",
        "fallback_decisions",
        "fallback_ratio",
        "positive_pressure_decisions",
        "positive_pressure_ratio",
        "no_positive_pressure_count",
        "missing_queue_count",
        "no_candidate_count",
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
        backpressure_diagnostics_enabled=True,
        backpressure_diagnostics_sample_limit=DEFAULT_DIAGNOSTIC_SAMPLE_LIMIT,
        diagnostic_pairs=None,
):
    if enable_verbose_logs:
        print("\nALGORITHM: SIMPLE BACKPRESSURE OVER ISLS")

    fallback_policy = normalize_backpressure_fallback(backpressure_fallback)
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
                    selected_candidate = {
                        "neighbor": dst_gs_node_id,
                        "queue_current": 0.0,
                        "queue_neighbor": 0.0,
                        "queue_diff": 0.0,
                        "weight": 0.0,
                    }
                    selected_positive = False
                    fallback_used = False
                    fallback_reason = "direct_gsl_delivery"
                else:
                    selection = _select_backpressure_next_hop(
                        curr,
                        dst_gid,
                        sat_net_graph_only_satellites_with_isls,
                        dist_sat_net_without_gs,
                        ground_station_satellites_in_range,
                        sat_neighbor_to_if,
                        queue_state,
                        fallback_policy,
                        link_capacity_bps,
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
                    selected_candidate = {
                        "neighbor": -1,
                        "queue_current": 0.0,
                        "queue_neighbor": 0.0,
                        "queue_diff": 0.0,
                        "weight": 0.0,
                    }
                decision_infos[fstate_key] = {
                    "current_node": curr,
                    "destination": dst_gs_node_id,
                    "selected_next_hop": next_hop_decision[0],
                    "queue_current": selected_candidate["queue_current"],
                    "queue_neighbor": selected_candidate["queue_neighbor"],
                    "queue_diff": selected_candidate["queue_diff"],
                    "weight": selected_candidate["weight"],
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
        "backpressure_is_full_multi_commodity": False,
        "backpressure_capacity_multiplier_enabled": True,
    }
