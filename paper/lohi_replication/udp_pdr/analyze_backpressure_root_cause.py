import csv
import math
import os
from collections import Counter


ALGORITHM = "algorithm_backpressure_over_isls"

RUNS = [
    {
        "queue_source": "node_total_queue_bytes",
        "run_name": (
            "run_core_isl_hotspot_specific_src754_dst785_load_1p6x_"
            "bg_flow_count_32_sim10s_stop8s_isl10mbps_gsl100mbps_"
            "lohi_mgmt_legacy_bp_qauto_fbsp_oneweb_isls_moving_udp_pdr"
        ),
        "notes": "original auto queue source; effective source is node_total_queue_bytes",
    },
    {
        "queue_source": "interface_nonreturn_avg_bytes",
        "run_name": (
            "run_core_isl_hotspot_specific_src754_dst785_load_1p6x_"
            "bg_flow_count_32_sim10s_stop8s_isl10mbps_gsl100mbps_"
            "lohi_mgmt_legacy_bp_qifnavgbytes_fbsp_oneweb_isls_moving_udp_pdr"
        ),
        "notes": "interface-aware non-return average queue proxy smoke",
    },
    {
        "queue_source": "interface_nonreturn_min_bytes",
        "run_name": (
            "run_core_isl_hotspot_specific_src754_dst785_load_1p6x_"
            "bg_flow_count_32_sim10s_stop8s_isl10mbps_gsl100mbps_"
            "lohi_mgmt_legacy_bp_qifnminbytes_fbsp_oneweb_isls_moving_udp_pdr"
        ),
        "notes": "interface-aware non-return minimum queue proxy smoke",
    },
]

REPORT_DIR = os.path.join(
    os.path.dirname(__file__),
    "analysis_reports",
    "backpressure_low_pdr_root_cause",
)


def _read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f_in:
        return list(csv.DictReader(f_in))


def _write_csv(path, fieldnames, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f_out:
        f_out.write(text)


def _float(row, key, default=0.0):
    value = row.get(key, "")
    if value in ("", None):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(row, key, default=0):
    return int(round(_float(row, key, default)))


def _bool(row, key):
    return str(row.get(key, "")).strip().lower() in ("1", "true", "yes")


def _mean(values):
    clean = [float(value) for value in values if value is not None]
    return sum(clean) / len(clean) if clean else 0.0


def _p95(values):
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return 0.0
    index = int(math.ceil(0.95 * len(clean))) - 1
    return clean[max(0, min(index, len(clean) - 1))]


def _fmt(value, digits=4):
    try:
        return ("%%.%df" % digits) % float(value)
    except (TypeError, ValueError):
        return str(value)


def _top_items(counter, limit=5):
    return "; ".join("%s (%d)" % (key, count) for key, count in counter.most_common(limit))


def _path_nodes(path):
    if not path:
        return []
    if "->" in path:
        return [part for part in path.split("->") if part != ""]
    if ";" in path:
        return [part for part in path.split(";") if part != ""]
    return [path]


def _loop_signature(path):
    nodes = _path_nodes(path)
    seen = {}
    for index, node in enumerate(nodes):
        if node in seen:
            return "->".join(nodes[seen[node] : index + 1])
        seen[node] = index
    return "->".join(nodes[-6:])


def _path_edges(path):
    nodes = _path_nodes(path)
    return ["%s->%s" % (nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)]


def _weighted_ratio(rows, numerator_key, denominator_key):
    denominator = sum(_float(row, denominator_key) for row in rows)
    if denominator <= 0.0:
        return 0.0
    numerator = sum(_float(row, numerator_key) for row in rows)
    return numerator / denominator


def _weighted_mean(rows, value_key, weight_key):
    denominator = sum(_float(row, weight_key) for row in rows)
    if denominator <= 0.0:
        return 0.0
    return sum(_float(row, value_key) * _float(row, weight_key) for row in rows) / denominator


def _run_dirs(base_dir, run_name):
    run_dir = os.path.join(base_dir, "runs", run_name)
    algo_dir = os.path.join(run_dir, ALGORITHM)
    comp_dir = os.path.join(run_dir, "comparison_packet_delivery")
    return {
        "run": run_dir,
        "algo": algo_dir,
        "diag": os.path.join(algo_dir, "backpressure_diagnostics"),
        "core": os.path.join(comp_dir, "core"),
        "comparison_diagnostics": os.path.join(comp_dir, "diagnostics"),
    }


def _background_pdr(per_flow_rows):
    sent = sum(_int(row, "sent_packets") for row in per_flow_rows if row.get("flow_class") == "background")
    received = sum(
        _int(row, "received_packets") for row in per_flow_rows if row.get("flow_class") == "background"
    )
    return received / sent if sent else 0.0


def _rtt_metrics(rows):
    if not rows:
        return (0.0, 0.0)
    return (
        _mean([_float(row, "mean_queue_aware_rtt_ms") for row in rows]),
        max([_float(row, "p95_queue_aware_rtt_ms") for row in rows]),
    )


def _path_metrics(path_rows):
    total = len(path_rows)
    loop_rows = [row for row in path_rows if _bool(row, "loop_detected")]
    reached_rows = [row for row in path_rows if _bool(row, "reached_destination")]
    stretch_values = [_float(row, "path_stretch") for row in path_rows if row.get("path_stretch", "") != ""]
    reached_stretch_values = [
        _float(row, "path_stretch") for row in reached_rows if row.get("path_stretch", "") != ""
    ]
    loop_lengths = [_int(row, "hop_count") for row in loop_rows]

    loop_patterns = Counter(_loop_signature(row.get("path", "")) for row in loop_rows)
    loop_edges = Counter()
    for row in loop_rows:
        loop_edges.update(_path_edges(row.get("path", "")))
    time_distribution = Counter(row.get("time_ns", "") for row in loop_rows)

    positive_rows = [
        row for row in path_rows if _int(row, "positive_pressure_count_on_path") > 0
    ]
    fallback_only_rows = [
        row
        for row in path_rows
        if _int(row, "positive_pressure_count_on_path") == 0
        and _int(row, "fallback_count_on_path") > 0
    ]

    def _loop_rate(rows):
        return (
            sum(1 for row in rows if _bool(row, "loop_detected")) / float(len(rows))
            if rows
            else 0.0
        )

    def _success_rate(rows):
        return (
            sum(1 for row in rows if _bool(row, "reached_destination")) / float(len(rows))
            if rows
            else 0.0
        )

    return {
        "path_sample_count": total,
        "loop_detected_count": len(loop_rows),
        "loop_detected_ratio": len(loop_rows) / float(total) if total else 0.0,
        "reached_destination_count": len(reached_rows),
        "reached_destination_ratio": len(reached_rows) / float(total) if total else 0.0,
        "unreached_count": total - len(reached_rows),
        "avg_path_stretch": _mean(stretch_values),
        "reached_only_avg_path_stretch": _mean(reached_stretch_values),
        "avg_loop_length": _mean(loop_lengths),
        "top_loop_patterns": _top_items(loop_patterns),
        "top_loop_edges": _top_items(loop_edges),
        "loop_time_distribution": _top_items(time_distribution),
        "positive_path_count": len(positive_rows),
        "positive_path_loop_rate": _loop_rate(positive_rows),
        "positive_path_success_rate": _success_rate(positive_rows),
        "fallback_only_path_count": len(fallback_only_rows),
        "fallback_only_path_loop_rate": _loop_rate(fallback_only_rows),
        "fallback_only_path_success_rate": _success_rate(fallback_only_rows),
    }


def _decision_metrics(rows):
    selected_weights = [_float(row, "selected_weight") for row in rows]
    queue_current = [_float(row, "queue_current") for row in rows]
    queue_neighbor = [_float(row, "queue_neighbor") for row in rows]
    queue_diff = [_float(row, "queue_diff") for row in rows]
    interface_success = sum(1 for row in rows if _bool(row, "interface_queue_source_available"))
    fallback_rows = [row for row in rows if _bool(row, "fallback_used")]
    fallback_reasons = Counter(row.get("fallback_reason", "") for row in fallback_rows)
    fallback_nodes = Counter(row.get("current_node", "") for row in fallback_rows)
    fallback_destinations = Counter(row.get("destination", "") for row in fallback_rows)
    fallback_times = Counter(row.get("time_ns", "") for row in fallback_rows)
    return {
        "decision_log_rows": len(rows),
        "selected_weight_mean": _mean(selected_weights),
        "selected_weight_p95": _p95(selected_weights),
        "queue_current_mean": _mean(queue_current),
        "queue_current_p95": _p95(queue_current),
        "queue_neighbor_mean": _mean(queue_neighbor),
        "queue_neighbor_p95": _p95(queue_neighbor),
        "queue_diff_mean": _mean(queue_diff),
        "queue_diff_p95": _p95(queue_diff),
        "interface_decision_success_ratio": interface_success / float(len(rows)) if rows else 0.0,
        "fallback_reason_summary": _top_items(fallback_reasons),
        "top_fallback_nodes": _top_items(fallback_nodes),
        "top_fallback_destinations": _top_items(fallback_destinations),
        "top_fallback_times_ns": _top_items(fallback_times),
    }


def _path_replay_success(rows):
    if not rows:
        return 0.0
    return max(_float(row, "path_replay_success_ratio") for row in rows)


def _focus_path_notes(rows):
    interesting = [row for row in rows if row.get("time_ns") in ("0", "5000000000", "8000000000")]
    lines = []
    for row in interesting:
        status = row.get("path_replay_status", "")
        time_s = _float(row, "time_ns") / 1e9
        direction = row.get("direction", "")
        fwd = row.get("forward_path", "")
        rev = row.get("reverse_path", "")
        lines.append(
            "t=%s %s: %s; forward=%s; reverse=%s"
            % (_fmt(time_s, 1), direction, status, fwd, rev)
        )
    return "\n".join(lines)


def collect_metrics(base_dir):
    metrics = []
    for run in RUNS:
        dirs = _run_dirs(base_dir, run["run_name"])
        summary_rows = _read_csv(os.path.join(dirs["core"], "summary_by_algorithm.csv"))
        per_flow_rows = _read_csv(os.path.join(dirs["core"], "per_flow_delivery.csv"))
        loss_rows = _read_csv(os.path.join(dirs["core"], "loss_attribution_breakdown_v3.csv"))
        rtt_rows = _read_csv(os.path.join(dirs["core"], "udp_rtt_summary_by_algorithm.csv"))
        replay_rows = _read_csv(os.path.join(dirs["core"], "path_replay_diagnostics.csv"))
        fallback_rows = _read_csv(os.path.join(dirs["diag"], "backpressure_fallback_summary.csv"))
        summary_diag_rows = _read_csv(os.path.join(dirs["diag"], "backpressure_summary.csv"))
        queue_rows = _read_csv(os.path.join(dirs["diag"], "backpressure_queue_source_summary.csv"))
        path_rows = _read_csv(os.path.join(dirs["diag"], "backpressure_path_stretch_summary.csv"))
        decision_rows = _read_csv(os.path.join(dirs["diag"], "backpressure_decision_log.csv"))
        focus_path_rows = _read_csv(
            os.path.join(dirs["comparison_diagnostics"], "udp_focus_path_timeseries.csv")
        )

        summary = summary_rows[0] if summary_rows else {}
        loss = loss_rows[0] if loss_rows else {}
        mean_rtt, p95_rtt = _rtt_metrics(rtt_rows)
        path = _path_metrics(path_rows)
        decision = _decision_metrics(decision_rows)

        queue_file_exists_ratio = (
            sum(1 for row in queue_rows if _bool(row, "queue_file_exists")) / float(len(queue_rows))
            if queue_rows
            else 0.0
        )

        total_decisions = sum(_float(row, "total_decisions") for row in fallback_rows)
        metric = {
            "queue_source": run["queue_source"],
            "run_name": run["run_name"],
            "run_dir": dirs["run"],
            "notes": run["notes"],
            "aggregate_pdr": _float(summary, "aggregate_pdr"),
            "focus_pdr": _float(summary, "focus_flow_pdr"),
            "background_pdr": _background_pdr(per_flow_rows),
            "mean_rtt_ms": mean_rtt,
            "p95_rtt_ms": p95_rtt,
            "total_sent_packets": _int(summary, "total_sent_packets"),
            "total_received_packets": _int(summary, "total_received_packets"),
            "total_lost_packets": _int(summary, "total_lost_packets"),
            "traffic_stop_time_s": _float(summary, "traffic_stop_time_s"),
            "simulation_end_time_s": _float(summary, "simulation_end_time_s"),
            "drain_time_s": _float(summary, "drain_time_s"),
            "fallback_ratio": _weighted_ratio(fallback_rows, "fallback_decisions", "total_decisions"),
            "positive_pressure_ratio": _weighted_ratio(
                fallback_rows, "positive_pressure_decisions", "total_decisions"
            ),
            "no_positive_pressure_count": sum(_int(row, "no_positive_pressure_count") for row in fallback_rows),
            "missing_queue_count": sum(_int(row, "missing_queue_count") for row in fallback_rows),
            "no_candidate_count": sum(_int(row, "no_candidate_count") for row in fallback_rows),
            "no_forward_interface_count": sum(_int(row, "no_forward_interface_count") for row in fallback_rows),
            "total_decisions": total_decisions,
            "interface_source_success_ratio": _weighted_mean(
                summary_diag_rows, "interface_source_success_ratio", "total_decisions"
            ),
            "interface_mapping_missing_count": sum(
                _int(row, "interface_mapping_missing_count") for row in summary_diag_rows
            ),
            "queue_file_exists_ratio": queue_file_exists_ratio,
            "queue_record_count_avg": _mean([_float(row, "queue_record_count") for row in queue_rows]),
            "interface_count_with_queue_avg": _mean(
                [_float(row, "interface_count_with_queue") for row in queue_rows]
            ),
            "node_count_with_queue_avg": _mean([_float(row, "node_count_with_queue") for row in queue_rows]),
            "synthetic_lost_packets": _int(loss, "synthetic_lost_packets"),
            "exact_physical_queue_loss": _int(loss, "exact_physical_queue_loss"),
            "exact_physical_phy_loss": _int(loss, "exact_physical_phy_loss"),
            "exact_routing_loss": _int(loss, "exact_routing_loss"),
            "exact_udp_send_failure_loss": _int(loss, "exact_udp_send_failure_loss"),
            "isl_saturation_associated_loss": _int(loss, "isl_saturation_associated_loss"),
            "tail_in_flight_possible_loss": _int(loss, "tail_in_flight_possible_loss"),
            "unclassified_loss": _int(loss, "unclassified_loss"),
            "path_replay_success_ratio": _path_replay_success(replay_rows),
            "focus_path_notes": _focus_path_notes(focus_path_rows),
        }
        metric.update(path)
        metric.update(decision)
        metrics.append(metric)
    return metrics


def write_report_files(metrics):
    node = metrics[0]
    interface_metrics = [metric for metric in metrics if metric["queue_source"] != "node_total_queue_bytes"]

    smoke_rows = []
    for metric in metrics:
        smoke_rows.append(
            {
                "queue_source": metric["queue_source"],
                "aggregate_pdr": metric["aggregate_pdr"],
                "focus_pdr": metric["focus_pdr"],
                "background_pdr": metric["background_pdr"],
                "mean_rtt_ms": metric["mean_rtt_ms"],
                "p95_rtt_ms": metric["p95_rtt_ms"],
                "fallback_ratio": metric["fallback_ratio"],
                "positive_pressure_ratio": metric["positive_pressure_ratio"],
                "loop_detected_ratio": metric["loop_detected_ratio"],
                "reached_destination_ratio": metric["reached_destination_ratio"],
                "avg_path_stretch": metric["avg_path_stretch"],
                "path_replay_success_ratio": metric["path_replay_success_ratio"],
                "diagnostic_notes": metric["notes"],
            }
        )
    _write_csv(
        os.path.join(REPORT_DIR, "backpressure_smoke_comparison_node_vs_interface.csv"),
        [
            "queue_source",
            "aggregate_pdr",
            "focus_pdr",
            "background_pdr",
            "mean_rtt_ms",
            "p95_rtt_ms",
            "fallback_ratio",
            "positive_pressure_ratio",
            "loop_detected_ratio",
            "reached_destination_ratio",
            "avg_path_stretch",
            "path_replay_success_ratio",
            "diagnostic_notes",
        ],
        smoke_rows,
    )

    loop_rows = []
    for metric in metrics:
        loop_rows.append(
            {
                "queue_source": metric["queue_source"],
                "loop_detected_count": metric["loop_detected_count"],
                "loop_detected_ratio": metric["loop_detected_ratio"],
                "reached_destination_count": metric["reached_destination_count"],
                "reached_destination_ratio": metric["reached_destination_ratio"],
                "unreached_count": metric["unreached_count"],
                "avg_loop_length": metric["avg_loop_length"],
                "fallback_ratio": metric["fallback_ratio"],
                "positive_pressure_ratio": metric["positive_pressure_ratio"],
                "fallback_reason_summary": metric["fallback_reason_summary"],
                "top_fallback_nodes": metric["top_fallback_nodes"],
                "top_fallback_destinations": metric["top_fallback_destinations"],
                "top_fallback_times_ns": metric["top_fallback_times_ns"],
                "positive_pressure_vs_fallback_path_success": (
                    "positive_success=%s; fallback_only_success=%s"
                    % (
                        _fmt(metric["positive_path_success_rate"]),
                        _fmt(metric["fallback_only_path_success_rate"]),
                    )
                ),
                "positive_pressure_vs_fallback_loop_rate": (
                    "positive_loop=%s; fallback_only_loop=%s"
                    % (
                        _fmt(metric["positive_path_loop_rate"]),
                        _fmt(metric["fallback_only_path_loop_rate"]),
                    )
                ),
                "top_repeated_loop_patterns": metric["top_loop_patterns"],
                "top_loop_edges": metric["top_loop_edges"],
                "time_distribution_of_loops": metric["loop_time_distribution"],
            }
        )
    _write_csv(
        os.path.join(REPORT_DIR, "backpressure_loop_fallback_summary.csv"),
        [
            "queue_source",
            "loop_detected_count",
            "loop_detected_ratio",
            "reached_destination_count",
            "reached_destination_ratio",
            "unreached_count",
            "avg_loop_length",
            "fallback_ratio",
            "positive_pressure_ratio",
            "fallback_reason_summary",
            "top_fallback_nodes",
            "top_fallback_destinations",
            "top_fallback_times_ns",
            "positive_pressure_vs_fallback_path_success",
            "positive_pressure_vs_fallback_loop_rate",
            "top_repeated_loop_patterns",
            "top_loop_edges",
            "time_distribution_of_loops",
        ],
        loop_rows,
    )

    inflight_rows = []
    for metric in metrics:
        inflight_rows.append(
            {
                "queue_source": metric["queue_source"],
                "traffic_stop_time_s": metric["traffic_stop_time_s"],
                "simulation_end_time_s": metric["simulation_end_time_s"],
                "drain_time_s": metric["drain_time_s"],
                "total_sent_packets": metric["total_sent_packets"],
                "total_received_packets": metric["total_received_packets"],
                "total_lost_packets": metric["total_lost_packets"],
                "synthetic_lost_packets": metric["synthetic_lost_packets"],
                "tail_in_flight_possible_loss": metric["tail_in_flight_possible_loss"],
                "exact_physical_queue_loss": metric["exact_physical_queue_loss"],
                "exact_physical_phy_loss": metric["exact_physical_phy_loss"],
                "exact_routing_loss": metric["exact_routing_loss"],
                "exact_udp_send_failure_loss": metric["exact_udp_send_failure_loss"],
                "isl_saturation_associated_loss": metric["isl_saturation_associated_loss"],
                "unclassified_loss": metric["unclassified_loss"],
                "conclusion": (
                    "not primarily in-flight/drain in current attribution; "
                    "tail_in_flight_possible_loss is zero"
                ),
            }
        )
    _write_csv(
        os.path.join(REPORT_DIR, "backpressure_inflight_drain_check.csv"),
        [
            "queue_source",
            "traffic_stop_time_s",
            "simulation_end_time_s",
            "drain_time_s",
            "total_sent_packets",
            "total_received_packets",
            "total_lost_packets",
            "synthetic_lost_packets",
            "tail_in_flight_possible_loss",
            "exact_physical_queue_loss",
            "exact_physical_phy_loss",
            "exact_routing_loss",
            "exact_udp_send_failure_loss",
            "isl_saturation_associated_loss",
            "unclassified_loss",
            "conclusion",
        ],
        inflight_rows,
    )

    queue_rows = []
    for metric in metrics:
        if metric["queue_source"] == "node_total_queue_bytes":
            q_i = "node total backlog at current satellite"
            q_j = "node total backlog at candidate neighbor"
            interpretation = "coarse node pressure; not directed and not per-destination"
        elif metric["queue_source"] == "interface_nonreturn_min_bytes":
            q_i = "directed outgoing queue on current->candidate interface"
            q_j = "minimum candidate outgoing ISL queue excluding return interface"
            interpretation = "directed link-local proxy; optimistic non-commodity pressure and still loop-prone"
        else:
            q_i = "directed outgoing queue on current->candidate interface"
            q_j = "average candidate outgoing ISL queues excluding return interface"
            interpretation = "directed link-local proxy; still non-commodity and loop-prone"
        queue_rows.append(
            {
                "queue_source": metric["queue_source"],
                "q_i_definition": q_i,
                "q_j_definition": q_j,
                "queue_file_exists_ratio": metric["queue_file_exists_ratio"],
                "queue_record_count_avg": metric["queue_record_count_avg"],
                "node_count_with_queue_avg": metric["node_count_with_queue_avg"],
                "interface_count_with_queue_avg": metric["interface_count_with_queue_avg"],
                "interface_source_success_ratio": metric["interface_source_success_ratio"],
                "interface_mapping_missing_count": metric["interface_mapping_missing_count"],
                "queue_current_mean": metric["queue_current_mean"],
                "queue_current_p95": metric["queue_current_p95"],
                "queue_neighbor_mean": metric["queue_neighbor_mean"],
                "queue_neighbor_p95": metric["queue_neighbor_p95"],
                "queue_diff_mean": metric["queue_diff_mean"],
                "queue_diff_p95": metric["queue_diff_p95"],
                "selected_weight_mean": metric["selected_weight_mean"],
                "selected_weight_p95": metric["selected_weight_p95"],
                "aggregate_pdr": metric["aggregate_pdr"],
                "loop_detected_ratio": metric["loop_detected_ratio"],
                "interpretation": interpretation,
            }
        )
    _write_csv(
        os.path.join(REPORT_DIR, "backpressure_queue_source_comparison.csv"),
        [
            "queue_source",
            "q_i_definition",
            "q_j_definition",
            "queue_file_exists_ratio",
            "queue_record_count_avg",
            "node_count_with_queue_avg",
            "interface_count_with_queue_avg",
            "interface_source_success_ratio",
            "interface_mapping_missing_count",
            "queue_current_mean",
            "queue_current_p95",
            "queue_neighbor_mean",
            "queue_neighbor_p95",
            "queue_diff_mean",
            "queue_diff_p95",
            "selected_weight_mean",
            "selected_weight_p95",
            "aggregate_pdr",
            "loop_detected_ratio",
            "interpretation",
        ],
        queue_rows,
    )

    root_rows = [
        {
            "cause": "path loop / ping-pong in forwarding state",
            "evidence": (
                "node-total loop ratio %s (%d/%d), path replay success %s, "
                "t=5/t=8 focus paths loop"
                % (
                    _fmt(node["loop_detected_ratio"]),
                    node["loop_detected_count"],
                    node["path_sample_count"],
                    _fmt(node["path_replay_success_ratio"]),
                )
            ),
            "severity": "critical",
            "recommendation": "treat loops as the dominant failure mode; consider loop guard only as a separate stabilized proxy",
        },
        {
            "cause": "node_total_queue_bytes is a weak non-commodity proxy",
            "evidence": (
                "fallback ratio %s, positive-pressure ratio %s, but positive paths still loop at %s"
                % (
                    _fmt(node["fallback_ratio"]),
                    _fmt(node["positive_pressure_ratio"]),
                    _fmt(node["positive_path_loop_rate"]),
                )
            ),
            "severity": "high",
            "recommendation": "do not describe it as full multi-commodity Backpressure; keep it as a routing-level approximation",
        },
        {
            "cause": "missing per-destination commodity queues",
            "evidence": "queue source summary reports per_destination_queue_available=false",
            "severity": "high",
            "recommendation": "true commodity queues are the rigorous fix, but likely too costly for the current thesis schedule",
        },
        {
            "cause": "forwarding-state pipeline lag",
            "evidence": "routing is recomputed from previous queue snapshots every 0.1s, then installed as static forwarding state",
            "severity": "medium",
            "recommendation": "document this as a routing-level proxy, not packet-level dynamic Backpressure",
        },
        {
            "cause": "ISL saturation around looped paths",
            "evidence": (
                "node-total saturation-associated loss %d/%d; exact physical queue/phy/routing losses are zero"
                % (node["isl_saturation_associated_loss"], node["synthetic_lost_packets"])
            ),
            "severity": "medium",
            "recommendation": "interpret saturation as associated evidence, not exact root attribution",
        },
        {
            "cause": "in-flight/drain time",
            "evidence": (
                "traffic stops at %ss, simulation ends at %ss, tail_in_flight_possible_loss=%d"
                % (
                    _fmt(node["traffic_stop_time_s"], 1),
                    _fmt(node["simulation_end_time_s"], 1),
                    node["tail_in_flight_possible_loss"],
                )
            ),
            "severity": "low",
            "recommendation": "add late_arrivals_after_traffic_stop / estimated_inflight_at_end diagnostics if extending this analysis",
        },
    ]
    for iface in interface_metrics:
        root_rows.append(
            {
                "cause": "%s is feasible but not sufficient" % iface["queue_source"],
                "evidence": (
                    "PDR %s vs node-total %s; focus PDR %s vs %s; loop ratio %s"
                    % (
                        _fmt(iface["aggregate_pdr"]),
                        _fmt(node["aggregate_pdr"]),
                        _fmt(iface["focus_pdr"]),
                        _fmt(node["focus_pdr"]),
                        _fmt(iface["loop_detected_ratio"]),
                    )
                ),
                "severity": "high",
                "recommendation": "do not promote this interface proxy to formal baseline without explicit stabilization or commodity queues",
            }
        )
    _write_csv(
        os.path.join(REPORT_DIR, "backpressure_root_cause_summary.csv"),
        ["cause", "evidence", "severity", "recommendation"],
        root_rows,
    )

    _write_text(
        os.path.join(REPORT_DIR, "backpressure_interface_variant_feasibility.md"),
        _interface_feasibility_md(metrics),
    )
    _write_text(os.path.join(REPORT_DIR, "analysis_report_zh.md"), _analysis_md(metrics, root_rows))


def _interface_feasibility_md(metrics):
    node = metrics[0]
    iface_block = """
## 10s smoke result

{metric_table}

結果：`interface_nonreturn_avg_bytes` 和 `interface_nonreturn_min_bytes` 都可行且 diagnostics 有成功寫出，
但兩者都沒有改善 PDR。avg/min 的 focus PDR 都接近 0，loop ratio 也高於 node-total。
因此 interface-aware proxy 有助於說明 queue source 設計差異，但不足以直接升為 formal main baseline。
""".format(metric_table=_metric_table(metrics))
    return """# Backpressure Interface-aware Queue Variant Feasibility

## Feasibility

目前 `queue_stats/queue_stats_*.csv` 提供 directed ISL edge queue，欄位是 `from,to,packet_max,byte_max`。
這足以把 `A->B` 當作 A 的 outgoing interface queue，也足以把 `B->A` 視為 B 的 return interface。
在 route-calculation 時，satellite graph 已知道 B 的其他 ISL neighbors，因此可取 `B->C` directed queue，
並排除 `C == A` 的 return interface。

現有資料沒有暴露 ns-3 interface id 本身，也沒有 per-destination commodity queue。
因此這個 variant 是 directed-link queue proxy，而不是 full multi-commodity Backpressure。

## Method comparison

| Method | Q_i | Q_j | Meaning | Expected risk |
| --- | --- | --- | --- | --- |
| node_total_queue_bytes | current node total backlog | neighbor node total backlog | coarse node pressure | mixes unrelated outgoing directions and commodities |
| interface_nonreturn_avg_bytes | current->neighbor directed queue | avg neighbor outgoing ISL queues excluding return | link-local forwarding pressure | can still choose wrong destination direction |
| interface_nonreturn_min_bytes | current->neighbor directed queue | min neighbor outgoing ISL queues excluding return | most optimistic forward interface | may chase an empty but irrelevant interface |

## Recommendation

`interface_nonreturn_avg_bytes` is more local and less identical to `node_total_queue_bytes`, but it remains a proxy.
It should be evaluated as a candidate baseline, not presented as true Backpressure.
""" + iface_block


def _metric_table(metrics):
    lines = [
        "| queue_source | PDR | focus PDR | bg PDR | fallback | positive | loop | reached | replay success |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for metric in metrics:
        lines.append(
            "| {queue_source} | {pdr} | {focus} | {bg} | {fb} | {pos} | {loop} | {reach} | {replay} |".format(
                queue_source=metric["queue_source"],
                pdr=_fmt(metric["aggregate_pdr"]),
                focus=_fmt(metric["focus_pdr"]),
                bg=_fmt(metric["background_pdr"]),
                fb=_fmt(metric["fallback_ratio"]),
                pos=_fmt(metric["positive_pressure_ratio"]),
                loop=_fmt(metric["loop_detected_ratio"]),
                reach=_fmt(metric["reached_destination_ratio"]),
                replay=_fmt(metric["path_replay_success_ratio"]),
            )
        )
    return "\n".join(lines)


def _root_cause_table(root_rows):
    lines = [
        "| cause | evidence | severity | recommendation |",
        "| --- | --- | --- | --- |",
    ]
    for row in root_rows:
        lines.append(
            "| {cause} | {evidence} | {severity} | {recommendation} |".format(
                cause=row["cause"],
                evidence=row["evidence"],
                severity=row["severity"],
                recommendation=row["recommendation"],
            )
        )
    return "\n".join(lines)


def _analysis_md(metrics, root_rows):
    node = metrics[0]
    by_source = {metric["queue_source"]: metric for metric in metrics}
    avg_iface = by_source.get("interface_nonreturn_avg_bytes")
    min_iface = by_source.get("interface_nonreturn_min_bytes")
    iface_sentence = ""
    if avg_iface is not None and min_iface is not None:
        iface_sentence = (
            "我已實作並跑完 `interface_nonreturn_avg_bytes` 與 `interface_nonreturn_min_bytes` 10s smoke。"
            "avg/min aggregate PDR 分別是 {avg_pdr}/{min_pdr}，都低於 node-total 的 {node_pdr}；"
            "focus PDR 則都只有 {avg_focus}/{min_focus}，遠低於 node-total 的 {node_focus}。"
            "所以 interface-aware queue source 可行，但 avg/min variants 尚未讓 baseline 變得足夠可比較。"
        ).format(
            avg_pdr=_fmt(avg_iface["aggregate_pdr"]),
            min_pdr=_fmt(min_iface["aggregate_pdr"]),
            node_pdr=_fmt(node["aggregate_pdr"]),
            node_focus=_fmt(node["focus_pdr"]),
            avg_focus=_fmt(avg_iface["focus_pdr"]),
            min_focus=_fmt(min_iface["focus_pdr"]),
        )

    return """# Backpressure Low PDR Root-cause Analysis

## 1. 總結

PDR 低的主要原因不是 drain time，而是 routing-level Backpressure proxy 產生大量 forwarding-state loop。
node-total 10s smoke 的 diagnostic path loop ratio 是 {node_loop} ({node_loop_count}/{node_path_count})，
path replay success ratio 只有 {node_replay}，t=5 與 t=8 的 focus route replay 都是 loop。

in-flight / drain 目前不是主要證據：traffic 在 8s 停止、simulation 到 10s，`tail_in_flight_possible_loss=0`。
loss attribution 顯示 exact physical queue/phy/routing/send failure loss 目前都是 0，
但有 {node_sat_loss} 個 lost packets 和 ISL saturation overlap，另外 {node_unclassified} 個仍是 unclassified。

queue proxy 是關鍵問題之一。`node_total_queue_bytes` 把一個 satellite 的所有 outgoing queue 混成節點壓力，
不分 destination commodity，也不分 candidate outgoing direction，因此可能選到總 queue 比較低但轉送方向錯的 neighbor。

{iface_sentence}

## 2. 使用資料

- node-total run: `{node_run}`
- interface avg run: `{avg_run}`
- interface min run: `{min_run}`
- Backpressure diagnostics: `backpressure_decision_log.csv`, `backpressure_summary.csv`, `backpressure_queue_source_summary.csv`, `backpressure_fallback_summary.csv`, `backpressure_path_stretch_summary.csv`, `backpressure_loop_check.csv`
- delivery diagnostics: `summary_by_algorithm.csv`, `per_flow_delivery.csv`, `loss_attribution_breakdown_v3.csv`, `path_replay_diagnostics.csv`, `udp_focus_rtt_timeseries.csv`, `udp_focus_path_timeseries.csv`

## 3. Root-cause analysis

{root_table}

## 4. Node-total queue source 分析

`node_total_queue_bytes` 的 `Q_i` 和 `Q_j` 都是 satellite-level total backlog。
這會把所有 outgoing interface、所有 flow、所有 destination 的 queue 混在一起。
對 routing decision 來說，它只能回答「哪個節點總體比較塞」，不能回答「A 經由 B 往 destination 轉送是否比較合理」。

node-total smoke 的 weighted fallback ratio 是 {node_fb}，positive pressure ratio 是 {node_pos}。
這不是單純 positive pressure 太少；diagnostic path 裡只要路徑包含 positive-pressure decision，
loop rate 是 {node_pos_loop}。也就是 positive pressure proxy 本身常常把 forwarding state 推進 loop。

selected queue/weight distribution 摘要：

- queue_current mean/p95: {node_qcur_mean} / {node_qcur_p95}
- queue_neighbor mean/p95: {node_qnei_mean} / {node_qnei_p95}
- queue_diff mean/p95: {node_qdiff_mean} / {node_qdiff_p95}
- selected_weight mean/p95: {node_w_mean} / {node_w_p95}

## 5. Interface-aware queue source 評估

interface-aware proxy 可行，因為 `queue_stats` 已經有 directed edge queue (`from,to,packet_max,byte_max`)。
目前沒有直接使用 ns-3 interface id，但 directed edge `A->B` 已能代表 A 對 B 的 outgoing ISL queue；
`B->A` 可視為 return interface，B 的其他 graph neighbors 則可形成 non-return outgoing interfaces。

它與 node-total 不本質相同：node-total 是 coarse node pressure；interface-aware 是 directed link-local pressure。
但它仍然不是 full Backpressure，因為它仍缺 per-destination commodity queue，也沒有 per-packet 動態控制。
這次 avg/min variant smoke 顯示只改 queue source 不足以移除 loop 或提升 PDR。

## 6. 如果有實作 interface-aware variant

已實作：

- `interface_nonreturn_avg_bytes`
- `interface_nonreturn_min_bytes`

定義：

- `Q_i = queue(current->candidate_neighbor)`
- `Q_j = avg/min queue(candidate_neighbor->nonreturn_outgoing_ISL)`
- 若 candidate neighbor 沒有 non-return outgoing interface，fallback reason 記為 `no_forward_interface`

新增 diagnostics 欄位：

- decision log: `current_out_interface`, `neighbor_return_interface`, `neighbor_forward_interfaces`, `queue_current_out_interface`, `queue_neighbor_forward_avg`, `queue_neighbor_forward_min`, `interface_queue_source_available`, `nonreturn_interface_count`
- summary: `interface_source_success_ratio`, `no_forward_interface_count`, `interface_mapping_missing_count`

修改檔案：

- `satgenpy/satgen/dynamic_state/algorithm_backpressure_over_isls.py`
- `paper/lohi_replication/udp_pdr/dynamic_run_list.py`
- `paper/lohi_replication/udp_pdr/analyze_backpressure_root_cause.py`

## 7. Smoke comparison

{metric_table}

node-total focus paths:

```text
{node_focus_paths}
```

interface avg focus paths:

```text
{avg_focus_paths}
```

interface min focus paths:

```text
{min_focus_paths}
```

## 8. 如何讓 Backpressure 變得可比較

最務實建議：不要直接把目前 node-total、interface-avg 或 interface-min 放進 formal main table 當主 baseline。
短期可做三步：

1. 先不要跑 H80 60s formal；avg/min 都仍 loop，直接 formal 只會把不穩定 proxy 放大。
2. 新增一個明確標註的 loop-suppressed proxy，例如 `--backpressure-loop-guard immediate_reverse`，並把它稱作 practical stabilized proxy。
3. 若論文時間允許，才考慮 true per-destination commodity queue instrumentation；這是最嚴謹但成本最高的方案。

若畢業時程吃緊，我會把 Backpressure 放在「queue-driven routing-level proxy baseline / diagnostic baseline」位置，
主表可只放穩定、可解釋的 baseline；Backpressure 的 low-PDR 結果可在 appendix 或 ablation 解釋。

## 9. Thesis wording suggestion

本研究額外實作了一個 routing-level Backpressure proxy 作為 queue-driven baseline。
由於 Hypatia/ns-3 實驗流程目前沒有 per-destination commodity queue，
此 baseline 使用 node-total 或 directed-interface queue 作為壓力近似，並以週期性 forwarding-state update 取代 packet-level dynamic Backpressure。
10 秒 hotspot smoke 顯示，低 PDR 主要來自 forwarding-state loop 與 proxy pressure mismatch，
而非單純 drain time 不足。interface-aware queue source 能更局部地描述 outgoing link pressure，
但 10 秒結果顯示它仍無法替代真正 commodity queue，因此本文將其定位為可解釋的 proxy baseline，
而非 full multi-commodity Backpressure。

## 10. 下一步命令

暫時不建議直接跑 H80 60s formal。min variant 已跑完，下一步若要繼續 Backpressure baseline，建議做 loop-suppressed smoke 或 no-route diagnostic，而不是直接 formal。

```bash
cd paper/lohi_replication/udp_pdr
python analyze_backpressure_root_cause.py
```

## 11. Commit 建議

```text
analysis(backpressure): diagnose low PDR and add interface queue proxy
```
""".format(
        node_loop=_fmt(node["loop_detected_ratio"]),
        node_loop_count=node["loop_detected_count"],
        node_path_count=node["path_sample_count"],
        node_replay=_fmt(node["path_replay_success_ratio"]),
        node_sat_loss=node["isl_saturation_associated_loss"],
        node_unclassified=node["unclassified_loss"],
        iface_sentence=iface_sentence,
        node_run=node["run_dir"],
        avg_run=avg_iface["run_dir"] if avg_iface else "",
        min_run=min_iface["run_dir"] if min_iface else "",
        root_table=_root_cause_table(root_rows),
        node_fb=_fmt(node["fallback_ratio"]),
        node_pos=_fmt(node["positive_pressure_ratio"]),
        node_pos_loop=_fmt(node["positive_path_loop_rate"]),
        node_qcur_mean=_fmt(node["queue_current_mean"]),
        node_qcur_p95=_fmt(node["queue_current_p95"]),
        node_qnei_mean=_fmt(node["queue_neighbor_mean"]),
        node_qnei_p95=_fmt(node["queue_neighbor_p95"]),
        node_qdiff_mean=_fmt(node["queue_diff_mean"]),
        node_qdiff_p95=_fmt(node["queue_diff_p95"]),
        node_w_mean=_fmt(node["selected_weight_mean"]),
        node_w_p95=_fmt(node["selected_weight_p95"]),
        metric_table=_metric_table(metrics),
        node_focus_paths=node["focus_path_notes"],
        avg_focus_paths=avg_iface["focus_path_notes"] if avg_iface else "",
        min_focus_paths=min_iface["focus_path_notes"] if min_iface else "",
    )


def main():
    base_dir = os.path.dirname(__file__)
    metrics = collect_metrics(base_dir)
    write_report_files(metrics)
    print("Wrote Backpressure root-cause reports to %s" % REPORT_DIR)


if __name__ == "__main__":
    main()
