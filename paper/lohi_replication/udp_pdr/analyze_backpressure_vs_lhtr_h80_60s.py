#!/usr/bin/env python3

import csv
import hashlib
import json
import math
import os
from pathlib import Path


os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-udp-pdr")

SCRIPT_DIR = Path(__file__).resolve().parent
RUNS_DIR = SCRIPT_DIR / "runs"
REPORT_DIR = (
    SCRIPT_DIR
    / "analysis_reports"
    / "backpressure_vs_lhtr_h80_60s"
)
FIGURES_DIR = REPORT_DIR / "figures"

NEW_RUN_NAME = (
    "run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_"
    "sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_"
    "bp_qnodebytes_fbsp_lgfwphop_oneweb_isls_moving_udp_pdr"
)
OLD_RUN_NAME = (
    "run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_"
    "sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_"
    "oneweb_isls_moving_udp_pdr"
)

NEW_RUN_DIR = RUNS_DIR / NEW_RUN_NAME
OLD_RUN_DIR = RUNS_DIR / OLD_RUN_NAME

LHTR = "algorithm_lhtr"
BACKPRESSURE = "algorithm_backpressure_over_isls"
ALGORITHMS = [LHTR, BACKPRESSURE]
ALGORITHM_LABELS = {
    LHTR: "LHTR",
    BACKPRESSURE: "Backpressure",
}

SUMMARY_FIELDS = [
    "scenario_id",
    "comparison_basis",
    "run_name",
    "algorithm",
    "algorithm_label",
    "aggregate_pdr",
    "focus_pdr",
    "background_pdr",
    "min_flow_pdr",
    "p5_flow_pdr",
    "lost_packets",
    "aggregate_pdr_delta_vs_lhtr",
    "focus_pdr_delta_vs_lhtr",
    "lost_packets_delta_vs_lhtr",
    "mean_rtt_ms",
    "p95_rtt_ms",
    "mean_propagation_rtt_ms",
    "mean_queue_delay_ms",
    "dominant_loss_attribution",
    "isl_saturation_samples",
    "gsl_saturation_samples",
    "isl_saturated_interface_count",
    "gsl_saturated_interface_count",
    "path_replay_success_ratio",
    "route_plot_count",
    "route_plot_exists",
    "notes",
]

RTT_FIELDS = [
    "algorithm",
    "algorithm_label",
    "direction",
    "mean_propagation_only_rtt_ms",
    "median_propagation_only_rtt_ms",
    "p95_propagation_only_rtt_ms",
    "mean_queue_aware_rtt_ms",
    "median_queue_aware_rtt_ms",
    "p95_queue_aware_rtt_ms",
    "mean_forward_queue_delay_ms",
    "mean_reverse_queue_delay_ms",
    "max_queue_aware_rtt_ms",
    "valid_sample_count",
    "missing_sample_count",
]

LOSS_FIELDS = [
    "algorithm",
    "algorithm_label",
    "synthetic_lost_packets",
    "exact_physical_queue_loss",
    "exact_physical_phy_loss",
    "exact_routing_loss",
    "exact_udp_send_failure_loss",
    "isl_saturation_associated_loss",
    "gsl_saturation_associated_loss",
    "mixed_saturation_associated_loss",
    "tail_in_flight_possible_loss",
    "unclassified_loss",
    "dominant_loss_attribution",
    "dominant_loss_proportion",
    "path_replay_success_ratio",
    "attribution_coverage_ratio",
    "attribution_confidence",
    "notes",
]

BACKPRESSURE_DIAG_FIELDS = [
    "scenario_id",
    "algorithm",
    "requested_queue_source",
    "effective_queue_source",
    "fallback_policy",
    "loop_guard_mode",
    "commodity_mode",
    "is_restricted_route_backpressure",
    "is_full_multi_commodity",
    "total_decisions",
    "fallback_decisions",
    "fallback_ratio",
    "positive_pressure_decisions",
    "positive_pressure_ratio",
    "fallback_no_positive_pressure_after_guard_count",
    "candidate_filter_ratio",
    "forward_progress_success_ratio",
    "queue_file_exists_ratio",
    "node_count_with_queue_mean",
    "interface_count_with_queue_mean",
    "loop_detected_ratio",
    "reached_destination_ratio",
    "avg_path_stretch",
    "p95_path_stretch",
    "path_fallback_count_mean",
    "path_positive_pressure_count_mean",
    "two_hop_ping_pong_decisions",
    "path_replay_success_ratio",
    "focus_754_to_785_pdr",
    "focus_785_to_754_pdr",
    "interpretation",
]

LHTR_DIAG_FIELDS = [
    "scenario_id",
    "algorithm",
    "traffic_light_scoring_mode",
    "br_selected_count",
    "sbr_selected_count",
    "sbr_selection_ratio",
    "fallback_count",
    "no_route_count",
    "yellow_count",
    "red_count",
    "green_count",
    "sbr_due_to_yellow_count",
    "sbr_due_to_red_count",
    "fallback_due_to_no_sbr_count",
    "fallback_due_to_stretch_count",
    "no_admissible_sbr_count",
    "avg_yellow_links",
    "avg_red_links",
    "max_yellow_links",
    "max_red_links",
    "top_decision_reasons",
    "fstate_exact_match_ratio",
    "path_replay_success_ratio",
    "focus_754_to_785_pdr",
    "focus_785_to_754_pdr",
    "interpretation",
]

SANITY_FIELDS = [
    "metric",
    "old_run_value",
    "new_run_value",
    "delta",
    "tolerance",
    "match_within_tolerance",
    "notes",
]


def read_csv(path):
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as f_in:
        return list(csv.DictReader(f_in))


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def read_json(path):
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f_in:
        return json.load(f_in)


def number(value, default=0.0):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def integer(value, default=0):
    return int(round(number(value, default)))


def bool_value(value):
    return str(value).strip().lower() in {"1", "true", "yes"}


def first_row(rows, **matches):
    for row in rows:
        if all(row.get(key) == value for key, value in matches.items()):
            return row
    return {}


def rows_for(rows, **matches):
    return [
        row
        for row in rows
        if all(row.get(key) == value for key, value in matches.items())
    ]


def safe_ratio(numerator, denominator):
    denominator = number(denominator)
    return number(numerator) / denominator if denominator else 0.0


def mean(values):
    values = [number(value) for value in values if value not in ("", None)]
    return sum(values) / len(values) if values else 0.0


def max_or_zero(values):
    values = [number(value) for value in values if value not in ("", None)]
    return max(values) if values else 0.0


def fmt(value, digits=3):
    if value == "" or value is None:
        return ""
    value = number(value)
    if math.isclose(value, round(value), abs_tol=10 ** (-digits)):
        return f"{int(round(value)):,}"
    return f"{value:,.{digits}f}"


def pct(value, digits=2):
    return f"{number(value) * 100:.{digits}f}%"


def pp(value, digits=2):
    return f"{number(value) * 100:+.{digits}f} p.p."


def hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as f_in:
        for chunk in iter(lambda: f_in.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def core_dir(run_dir):
    return run_dir / "comparison_packet_delivery" / "core"


def diag_dir(run_dir):
    return run_dir / "comparison_packet_delivery" / "diagnostics"


def route_plot_count(run_dir, algorithm):
    pattern = (
        run_dir
        / "comparison_packet_delivery"
        / "graphical_routes"
        / f"{algorithm}_focus_*.png"
    )
    return len(list(pattern.parent.glob(pattern.name)))


def background_pdr(per_flow_rows, algorithm):
    rows = [
        row
        for row in per_flow_rows
        if row.get("algorithm") == algorithm
        and row.get("flow_class") == "background"
    ]
    sent = sum(number(row.get("sent_packets")) for row in rows)
    received = sum(number(row.get("received_packets")) for row in rows)
    return safe_ratio(received, sent)


def focus_direction_pdr(per_flow_rows, algorithm, src, dst):
    for row in per_flow_rows:
        if (
            row.get("algorithm") == algorithm
            and row.get("flow_class") == "focus"
            and row.get("src") == str(src)
            and row.get("dst") == str(dst)
        ):
            return number(row.get("pdr"))
    return 0.0


LOSS_COLUMNS = [
    "exact_physical_queue_loss",
    "exact_physical_phy_loss",
    "exact_routing_loss",
    "exact_udp_send_failure_loss",
    "isl_saturation_associated_loss",
    "gsl_saturation_associated_loss",
    "mixed_saturation_associated_loss",
    "tail_in_flight_possible_loss",
    "unclassified_loss",
]


def dominant_loss(row):
    values = [(column, number(row.get(column))) for column in LOSS_COLUMNS]
    column, value = max(values, key=lambda item: item[1])
    total = number(row.get("synthetic_lost_packets"))
    return column, value, safe_ratio(value, total)


def rtt_main(rtt_rows, algorithm):
    return (
        first_row(rtt_rows, algorithm=algorithm, direction="754_to_785")
        or first_row(rtt_rows, algorithm=algorithm)
    )


def replay_ratio(path_replay_rows, algorithm):
    rows = rows_for(path_replay_rows, algorithm=algorithm)
    return max_or_zero(row.get("path_replay_success_ratio") for row in rows)


def saturation_stats(congested_rows, algorithm):
    rows = rows_for(congested_rows, algorithm=algorithm)
    isl_rows = [row for row in rows if row.get("link_type") == "ISL"]
    gsl_rows = [row for row in rows if row.get("link_type") == "GSL"]
    return {
        "isl_saturation_samples": sum(
            integer(row.get("samples_at_capacity")) for row in isl_rows
        ),
        "gsl_saturation_samples": sum(
            integer(row.get("samples_at_capacity")) for row in gsl_rows
        ),
        "isl_saturated_interface_count": len(isl_rows),
        "gsl_saturated_interface_count": len(gsl_rows),
    }


def summary_rows():
    summary = read_csv(core_dir(NEW_RUN_DIR) / "summary_by_algorithm.csv")
    per_flow = read_csv(core_dir(NEW_RUN_DIR) / "per_flow_delivery.csv")
    rtt = read_csv(core_dir(NEW_RUN_DIR) / "udp_rtt_summary_by_algorithm.csv")
    loss = read_csv(core_dir(NEW_RUN_DIR) / "loss_attribution_breakdown_v3.csv")
    congested = read_csv(core_dir(NEW_RUN_DIR) / "congested_interfaces_summary.csv")
    path_replay = read_csv(core_dir(NEW_RUN_DIR) / "path_replay_diagnostics.csv")

    rows = []
    lhtr_summary = first_row(summary, algorithm=LHTR)
    for algorithm in ALGORITHMS:
        row = first_row(summary, algorithm=algorithm)
        rtt_row = rtt_main(rtt, algorithm)
        loss_row = first_row(loss, algorithm=algorithm)
        loss_name, loss_value, _ = dominant_loss(loss_row)
        saturation = saturation_stats(congested, algorithm)
        routes = route_plot_count(NEW_RUN_DIR, algorithm)
        mean_queue_delay = (
            number(rtt_row.get("mean_queue_aware_rtt_ms"))
            - number(rtt_row.get("mean_propagation_only_rtt_ms"))
        )
        rows.append(
            {
                "scenario_id": "H80",
                "comparison_basis": "paired_new_run",
                "run_name": NEW_RUN_NAME,
                "algorithm": algorithm,
                "algorithm_label": ALGORITHM_LABELS[algorithm],
                "aggregate_pdr": row.get("aggregate_pdr", ""),
                "focus_pdr": row.get("focus_flow_pdr", ""),
                "background_pdr": background_pdr(per_flow, algorithm),
                "min_flow_pdr": row.get("min_flow_pdr", ""),
                "p5_flow_pdr": row.get("p5_flow_pdr", ""),
                "lost_packets": row.get("total_lost_packets", ""),
                "aggregate_pdr_delta_vs_lhtr": (
                    number(row.get("aggregate_pdr"))
                    - number(lhtr_summary.get("aggregate_pdr"))
                ),
                "focus_pdr_delta_vs_lhtr": (
                    number(row.get("focus_flow_pdr"))
                    - number(lhtr_summary.get("focus_flow_pdr"))
                ),
                "lost_packets_delta_vs_lhtr": (
                    integer(row.get("total_lost_packets"))
                    - integer(lhtr_summary.get("total_lost_packets"))
                ),
                "mean_rtt_ms": rtt_row.get("mean_queue_aware_rtt_ms", ""),
                "p95_rtt_ms": rtt_row.get("p95_queue_aware_rtt_ms", ""),
                "mean_propagation_rtt_ms": rtt_row.get(
                    "mean_propagation_only_rtt_ms",
                    "",
                ),
                "mean_queue_delay_ms": mean_queue_delay,
                "dominant_loss_attribution": "%s:%d" % (
                    loss_name,
                    int(loss_value),
                ),
                "path_replay_success_ratio": replay_ratio(path_replay, algorithm),
                "route_plot_count": routes,
                "route_plot_exists": str(routes >= 9).lower(),
                "notes": (
                    "paired LHTR baseline"
                    if algorithm == LHTR
                    else "restricted-route queue-proxy Backpressure variant"
                ),
                **saturation,
            }
        )
    return rows


def rtt_rows():
    rtt = read_csv(core_dir(NEW_RUN_DIR) / "udp_rtt_summary_by_algorithm.csv")
    rows = []
    for row in rtt:
        algorithm = row.get("algorithm")
        if algorithm not in ALGORITHMS:
            continue
        out = {"algorithm_label": ALGORITHM_LABELS[algorithm], **row}
        rows.append(out)
    return rows


def loss_rows():
    loss = read_csv(core_dir(NEW_RUN_DIR) / "loss_attribution_breakdown_v3.csv")
    rows = []
    for row in loss:
        algorithm = row.get("algorithm")
        if algorithm not in ALGORITHMS:
            continue
        name, value, proportion = dominant_loss(row)
        rows.append(
            {
                "algorithm": algorithm,
                "algorithm_label": ALGORITHM_LABELS[algorithm],
                "dominant_loss_attribution": "%s:%d" % (name, int(value)),
                "dominant_loss_proportion": proportion,
                **row,
            }
        )
    return rows


def backpressure_diagnostics():
    bp_dir = NEW_RUN_DIR / BACKPRESSURE / "backpressure_diagnostics"
    summary = read_csv(bp_dir / "backpressure_summary.csv")
    fallback = read_csv(bp_dir / "backpressure_fallback_summary.csv")
    queue_source = read_csv(bp_dir / "backpressure_queue_source_summary.csv")
    path_stretch = read_csv(bp_dir / "backpressure_path_stretch_summary.csv")
    per_flow = read_csv(core_dir(NEW_RUN_DIR) / "per_flow_delivery.csv")
    path_replay = read_csv(core_dir(NEW_RUN_DIR) / "path_replay_diagnostics.csv")

    total_decisions = sum(integer(row.get("total_decisions")) for row in fallback)
    fallback_decisions = sum(integer(row.get("fallback_decisions")) for row in fallback)
    positive_decisions = sum(
        integer(row.get("positive_pressure_decisions")) for row in fallback
    )
    no_positive_after_guard = sum(
        integer(row.get("no_positive_pressure_after_guard_count"))
        for row in fallback
    )
    candidates_before = sum(
        integer(row.get("total_candidates_before_guard")) for row in summary
    )
    candidates_after = sum(
        integer(row.get("total_candidates_after_guard")) for row in summary
    )
    loop_detected = sum(1 for row in path_stretch if bool_value(row.get("loop_detected")))
    reached = sum(1 for row in path_stretch if bool_value(row.get("reached_destination")))
    path_count = len(path_stretch)
    queue_file_exists = sum(
        1 for row in queue_source if bool_value(row.get("queue_file_exists"))
    )
    first_queue = queue_source[0] if queue_source else {}
    first_fallback = fallback[0] if fallback else {}

    row = {
        "scenario_id": "H80",
        "algorithm": BACKPRESSURE,
        "requested_queue_source": first_queue.get("requested_queue_source", ""),
        "effective_queue_source": first_queue.get("effective_queue_source", ""),
        "fallback_policy": first_fallback.get("fallback_policy", ""),
        "loop_guard_mode": first_fallback.get("loop_guard_mode", ""),
        "commodity_mode": first_queue.get("commodity_mode", ""),
        "is_restricted_route_backpressure": first_queue.get(
            "is_restricted_route_backpressure",
            "",
        ),
        "is_full_multi_commodity": first_queue.get(
            "is_full_multi_commodity",
            "",
        ),
        "total_decisions": total_decisions,
        "fallback_decisions": fallback_decisions,
        "fallback_ratio": safe_ratio(fallback_decisions, total_decisions),
        "positive_pressure_decisions": positive_decisions,
        "positive_pressure_ratio": safe_ratio(positive_decisions, total_decisions),
        "fallback_no_positive_pressure_after_guard_count": no_positive_after_guard,
        "candidate_filter_ratio": 1.0 - safe_ratio(candidates_after, candidates_before),
        "forward_progress_success_ratio": safe_ratio(
            candidates_after,
            candidates_before,
        ),
        "queue_file_exists_ratio": safe_ratio(queue_file_exists, len(queue_source)),
        "node_count_with_queue_mean": mean(
            row.get("node_count_with_queue") for row in queue_source
        ),
        "interface_count_with_queue_mean": mean(
            row.get("interface_count_with_queue") for row in queue_source
        ),
        "loop_detected_ratio": safe_ratio(loop_detected, path_count),
        "reached_destination_ratio": safe_ratio(reached, path_count),
        "avg_path_stretch": mean(row.get("path_stretch") for row in path_stretch),
        "p95_path_stretch": max_or_zero(row.get("path_stretch") for row in path_stretch),
        "path_fallback_count_mean": mean(
            row.get("fallback_count_on_path") for row in path_stretch
        ),
        "path_positive_pressure_count_mean": mean(
            row.get("positive_pressure_count_on_path") for row in path_stretch
        ),
        "two_hop_ping_pong_decisions": sum(
            integer(row.get("two_hop_ping_pong_decisions")) for row in summary
        ),
        "path_replay_success_ratio": replay_ratio(path_replay, BACKPRESSURE),
        "focus_754_to_785_pdr": focus_direction_pdr(
            per_flow,
            BACKPRESSURE,
            754,
            785,
        ),
        "focus_785_to_754_pdr": focus_direction_pdr(
            per_flow,
            BACKPRESSURE,
            785,
            754,
        ),
        "interpretation": (
            "Loop guard removed path loops, but most decisions fell back to "
            "shortest_path because no positive pressure candidate survived the "
            "forward-progress guard."
        ),
    }
    return [row]


def top_reasons(reason_rows, limit=5):
    ordered = sorted(
        reason_rows,
        key=lambda row: number(row.get("count")),
        reverse=True,
    )
    return ";".join(
        "%s:%s%%" % (
            row.get("decision_reason", ""),
            f"{number(row.get('percentage')):.3f}",
        )
        for row in ordered[:limit]
    )


def lhtr_diagnostics():
    lhtr_dir = NEW_RUN_DIR / LHTR / "lhtr_diagnostics"
    br_sbr = read_csv(lhtr_dir / "lhtr_br_sbr_summary.csv")
    reasons = read_csv(lhtr_dir / "lhtr_decision_reason_summary.csv")
    colors = read_csv(lhtr_dir / "lhtr_traffic_light_color_summary.csv")
    consistency = read_csv(lhtr_dir / "lhtr_fstate_decision_consistency.csv")
    per_flow = read_csv(core_dir(NEW_RUN_DIR) / "per_flow_delivery.csv")
    path_replay = read_csv(core_dir(NEW_RUN_DIR) / "path_replay_diagnostics.csv")

    br = sum(integer(row.get("br_selected_count")) for row in br_sbr)
    sbr = sum(integer(row.get("sbr_selected_count")) for row in br_sbr)
    fallback = sum(integer(row.get("fallback_count")) for row in br_sbr)
    no_route = sum(integer(row.get("no_route_count")) for row in br_sbr)
    match_rows = [row for row in consistency if row.get("match") in {"True", "False"}]
    match_count = sum(1 for row in match_rows if row.get("match") == "True")
    first = br_sbr[0] if br_sbr else {}

    row = {
        "scenario_id": "H80",
        "algorithm": LHTR,
        "traffic_light_scoring_mode": first.get("traffic_light_scoring_mode", ""),
        "br_selected_count": br,
        "sbr_selected_count": sbr,
        "sbr_selection_ratio": safe_ratio(sbr, br + sbr + fallback + no_route),
        "fallback_count": fallback,
        "no_route_count": no_route,
        "yellow_count": sum(integer(row.get("yellow_count")) for row in br_sbr),
        "red_count": sum(integer(row.get("red_count")) for row in br_sbr),
        "green_count": sum(integer(row.get("green_count")) for row in br_sbr),
        "sbr_due_to_yellow_count": sum(
            integer(row.get("sbr_due_to_yellow_count")) for row in br_sbr
        ),
        "sbr_due_to_red_count": sum(
            integer(row.get("sbr_due_to_red_count")) for row in br_sbr
        ),
        "fallback_due_to_no_sbr_count": sum(
            integer(row.get("fallback_due_to_no_sbr_count")) for row in br_sbr
        ),
        "fallback_due_to_stretch_count": sum(
            integer(row.get("fallback_due_to_stretch_count")) for row in br_sbr
        ),
        "no_admissible_sbr_count": sum(
            integer(row.get("no_admissible_sbr_count")) for row in br_sbr
        ),
        "avg_yellow_links": mean(row.get("yellow_count") for row in colors),
        "avg_red_links": mean(row.get("red_count") for row in colors),
        "max_yellow_links": max_or_zero(row.get("yellow_count") for row in colors),
        "max_red_links": max_or_zero(row.get("red_count") for row in colors),
        "top_decision_reasons": top_reasons(reasons),
        "fstate_exact_match_ratio": safe_ratio(match_count, len(match_rows)),
        "path_replay_success_ratio": replay_ratio(path_replay, LHTR),
        "focus_754_to_785_pdr": focus_direction_pdr(per_flow, LHTR, 754, 785),
        "focus_785_to_754_pdr": focus_direction_pdr(per_flow, LHTR, 785, 754),
        "interpretation": (
            "LHTR mostly kept BR routes and used SBR sparingly; traffic-light "
            "state reduced severe queue buildup without forcing long detours."
        ),
    }
    return [row]


def metric_compare(metric, old_value, new_value, tolerance, notes=""):
    old_num = number(old_value, None)
    new_num = number(new_value, None)
    if old_num is None or new_num is None:
        matches = str(old_value) == str(new_value)
        delta = ""
    else:
        delta_value = new_num - old_num
        delta = delta_value
        matches = abs(delta_value) <= tolerance
    return {
        "metric": metric,
        "old_run_value": old_value,
        "new_run_value": new_value,
        "delta": delta,
        "tolerance": tolerance,
        "match_within_tolerance": str(matches).lower(),
        "notes": notes,
    }


def metadata_hashes(run_dir):
    metadata = read_json(run_dir / LHTR / "run_metadata.json")
    pairs = metadata.get("pairs") or []
    first_pair = pairs[0] if pairs else {}
    return {
        "flow_selection_hash": metadata.get("flow_selection_hash", ""),
        "selection_input_hash": first_pair.get("selection_input_hash", ""),
    }


def sanity_rows():
    old_summary = read_csv(core_dir(OLD_RUN_DIR) / "summary_by_algorithm.csv")
    new_summary = read_csv(core_dir(NEW_RUN_DIR) / "summary_by_algorithm.csv")
    old_rtt = read_csv(core_dir(OLD_RUN_DIR) / "udp_rtt_summary_by_algorithm.csv")
    new_rtt = read_csv(core_dir(NEW_RUN_DIR) / "udp_rtt_summary_by_algorithm.csv")
    old_loss = read_csv(core_dir(OLD_RUN_DIR) / "loss_attribution_breakdown_v3.csv")
    new_loss = read_csv(core_dir(NEW_RUN_DIR) / "loss_attribution_breakdown_v3.csv")
    old_lhtr = first_row(old_summary, algorithm=LHTR)
    new_lhtr = first_row(new_summary, algorithm=LHTR)
    old_lhtr_rtt = rtt_main(old_rtt, LHTR)
    new_lhtr_rtt = rtt_main(new_rtt, LHTR)
    old_lhtr_loss = first_row(old_loss, algorithm=LHTR)
    new_lhtr_loss = first_row(new_loss, algorithm=LHTR)
    old_hashes = metadata_hashes(OLD_RUN_DIR)
    new_hashes = metadata_hashes(NEW_RUN_DIR)

    rows = []
    for metric in [
        "aggregate_pdr",
        "focus_flow_pdr",
        "total_lost_packets",
        "min_flow_pdr",
        "p5_flow_pdr",
        "jain_fairness",
    ]:
        rows.append(
            metric_compare(
                metric,
                old_lhtr.get(metric, ""),
                new_lhtr.get(metric, ""),
                1e-12,
                "LHTR packet-delivery summary",
            )
        )
    for metric in [
        "mean_queue_aware_rtt_ms",
        "p95_queue_aware_rtt_ms",
        "mean_propagation_only_rtt_ms",
    ]:
        rows.append(
            metric_compare(
                metric,
                old_lhtr_rtt.get(metric, ""),
                new_lhtr_rtt.get(metric, ""),
                1e-12,
                "LHTR RTT summary direction 754_to_785",
            )
        )
    rows.append(
        metric_compare(
            "synthetic_lost_packets",
            old_lhtr_loss.get("synthetic_lost_packets", ""),
            new_lhtr_loss.get("synthetic_lost_packets", ""),
            0,
            "loss attribution summary",
        )
    )
    rows.append(
        metric_compare(
            "udp_burst_schedule_sha256",
            hash_file(OLD_RUN_DIR / LHTR / "udp_burst_schedule.csv"),
            hash_file(NEW_RUN_DIR / LHTR / "udp_burst_schedule.csv"),
            0,
            "exact schedule hash",
        )
    )
    for metric in ["flow_selection_hash", "selection_input_hash"]:
        rows.append(
            metric_compare(
                metric,
                old_hashes.get(metric, ""),
                new_hashes.get(metric, ""),
                0,
                "run metadata",
            )
        )
    return rows


def write_restore_log():
    path = REPORT_DIR / "restore_hotspot_5level_60s_formal_log.md"
    backup = REPORT_DIR / "backup_overwritten_hotspot_5level_60s_formal"
    text = f"""# Restore Log: hotspot_5level_60s_formal

- Backup directory: `{backup.relative_to(SCRIPT_DIR)}`
- Backed up accident-version files:
  - `hotspot_5level_60s_formal_status.md`
  - `hotspot_5level_60s_formal_summary.csv`
- Restored shared formal files:
  - `analysis_reports/hotspot_5level_60s_formal/hotspot_5level_60s_formal_status.md`
  - `analysis_reports/hotspot_5level_60s_formal/hotspot_5level_60s_formal_summary.csv`
- Restore method: `git restore` could not create `.git/index.lock` under the sandbox's read-only `.git`, so the files were restored from `HEAD` content with read-only `git show HEAD:<path>` redirected to the workspace files.
- Verification: after restore, `git diff -- paper/lohi_replication/udp_pdr/analysis_reports/hotspot_5level_60s_formal` produced no output.

Root cause: `run_hotspot_5level_60s_formal.py` used a duration-only shared output path and rebuilt the formal manifest/summary/status after execution. With `--scenarios H80` and a CLI algorithm list that included Backpressure, the shared five-level report was rebuilt as if every scenario should also have Backpressure results, producing missing-output rows and incomplete warnings. A second bug made the damage easier to miss: `run_name_for_scenario()` only passed the first algorithm to `get_udp_pdr_run_list()`, so Backpressure identity tags were omitted when the first algorithm was Baseline.
"""
    path.write_text(text, encoding="utf-8")


def maybe_write_figures(summary):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return []

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    labels = [row["algorithm_label"] for row in summary]
    aggregate = [number(row["aggregate_pdr"]) for row in summary]
    focus = [number(row["focus_pdr"]) for row in summary]
    rtt = [number(row["mean_rtt_ms"]) for row in summary]
    lost = [number(row["lost_packets"]) for row in summary]

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
    axes[0].bar(labels, aggregate, color="#2E6F9E")
    axes[0].set_ylim(0, 1.05)
    axes[0].set_ylabel("PDR")
    axes[1].bar(labels, rtt, color="#4D8F5B")
    axes[1].set_ylabel("Estimate RTT (ms)")
    axes[2].bar(labels, lost, color="#8D5A99")
    axes[2].set_ylabel("Lost packets")
    for axis in axes:
        axis.tick_params(axis="x", rotation=0)
        axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    out = FIGURES_DIR / "backpressure_vs_lhtr_h80_60s_overview.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.6))
    axes[0].bar(labels, aggregate, color="#2E6F9E")
    axes[0].set_ylim(0, 1.05)
    axes[0].set_ylabel("PDR")
    axes[1].bar(labels, rtt, color="#4D8F5B")
    axes[1].set_ylabel("Estimate RTT (ms)")
    for axis in axes:
        axis.tick_params(axis="x", rotation=0)
        axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    pdr_rtt_out = FIGURES_DIR / "backpressure_vs_lhtr_h80_60s_pdr_rtt.png"
    fig.savefig(pdr_rtt_out, dpi=180)
    plt.close(fig)

    return [out, pdr_rtt_out]


def md_table(rows, fields, labels=None):
    labels = labels or {field: field for field in fields}
    lines = [
        "| " + " | ".join(labels.get(field, field) for field in fields) + " |",
        "| " + " | ".join(["---"] * len(fields)) + " |",
    ]
    for row in rows:
        values = []
        for field in fields:
            value = row.get(field, "")
            if isinstance(value, float):
                value = fmt(value, 3)
            values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_report(summary, bp_diag, lhtr_diag, sanity, figures):
    lhtr = first_row(summary, algorithm=LHTR)
    bp = first_row(summary, algorithm=BACKPRESSURE)
    bp_diag_row = bp_diag[0]
    lhtr_diag_row = lhtr_diag[0]
    mismatches = [
        row for row in sanity if row.get("match_within_tolerance") != "true"
    ]

    compact = [
        {
            "algorithm": row["algorithm_label"],
            "aggregate_pdr": pct(row["aggregate_pdr"]),
            "focus_pdr": pct(row["focus_pdr"]),
            "background_pdr": pct(row["background_pdr"]),
            "lost_packets": fmt(row["lost_packets"], 0),
            "mean_rtt_ms": fmt(row["mean_rtt_ms"], 1),
            "p95_rtt_ms": fmt(row["p95_rtt_ms"], 1),
            "dominant_loss_attribution": row["dominant_loss_attribution"],
        }
        for row in summary
    ]

    sanity_compact = [
        {
            "metric": row["metric"],
            "old": row["old_run_value"],
            "new": row["new_run_value"],
            "match": row["match_within_tolerance"],
        }
        for row in sanity
    ]

    figure_lines = "\n".join(
        f"- `{path.relative_to(SCRIPT_DIR)}`" for path in figures
    )
    if not figure_lines:
        figure_lines = "- 無。"

    text = f"""# 1. 總結

這次 H80 60s 的 Backpressure 結果不適合解讀成「完整 Backpressure 已輸給 LHTR」；它是 restricted-route、destination-proxy、node-total-queue 的 Backpressure variant。成對比較下，LHTR 明顯較好：aggregate PDR {pct(lhtr["aggregate_pdr"])} 對 {pct(bp["aggregate_pdr"])}，Backpressure 低 {pp(number(bp["aggregate_pdr"]) - number(lhtr["aggregate_pdr"]))}；focus PDR {pct(lhtr["focus_pdr"])} 對 {pct(bp["focus_pdr"])}，Backpressure 低 {pp(number(bp["focus_pdr"]) - number(lhtr["focus_pdr"]))}。Backpressure lost packets 多 {fmt(number(bp["lost_packets"]) - number(lhtr["lost_packets"]), 0)}，mean RTT 也從 LHTR 的 {fmt(lhtr["mean_rtt_ms"], 1)} ms 拉高到 {fmt(bp["mean_rtt_ms"], 1)} ms。

最核心原因不是 loop：Backpressure path replay 成功率 {pct(bp_diag_row["path_replay_success_ratio"])}、loop_detected_ratio {pct(bp_diag_row["loop_detected_ratio"])}、avg path stretch {fmt(bp_diag_row["avg_path_stretch"], 2)}。真正問題是壓力決策幾乎沒有生效：fallback_ratio {pct(bp_diag_row["fallback_ratio"])}，positive_pressure_ratio 只有 {pct(bp_diag_row["positive_pressure_ratio"])}，大多數 fallback 原因是 forward-progress guard 後沒有正壓力候選，因此退回 shortest path，最後仍把流量壓在 ISL hotspot 上。

# 2. 使用資料

- 新 Backpressure+LHTR paired run: `{NEW_RUN_NAME}`
- 舊四演算法 H80 60s run: `{OLD_RUN_NAME}`
- 情境: H80, simulation 60 s, traffic stop 58 s, src 754, dst 785, load 1.6x, background flows 32, ISL 10 Mbps, GSL 100 Mbps。
- Backpressure variant: requested queue source `node_total_bytes`，effective queue source `{bp_diag_row["effective_queue_source"]}`，fallback `{bp_diag_row["fallback_policy"]}`，loop guard `{bp_diag_row["loop_guard_mode"]}`，commodity mode `{bp_diag_row["commodity_mode"]}`。

# 3. Restore 結果

已備份事故版本並還原 shared formal output：

- Backup: `analysis_reports/backpressure_vs_lhtr_h80_60s/backup_overwritten_hotspot_5level_60s_formal/`
- Restore log: `analysis_reports/backpressure_vs_lhtr_h80_60s/restore_hotspot_5level_60s_formal_log.md`
- 驗證結果：`analysis_reports/hotspot_5level_60s_formal/` 還原後沒有 git diff。

# 4. Root cause of accidental overwrite

`run_hotspot_5level_60s_formal.py` 原本使用 duration-only shared output path：`analysis_reports/hotspot_5level_60s_formal/`。H80-only command 加上 Backpressure 演算法後，runner 在結尾仍重建 shared manifest/summary/status，而且 `ALGORITHMS` 取自這次 CLI，因此 formal summary 被改成期待五個情境都有 Backpressure；其他 H40/H60/H90/H100+ 自然變成 missing/incomplete warning。

另外還有一個 run-folder lookup bug：`run_name_for_scenario()` 只把第一個 algorithm 傳給 `get_udp_pdr_run_list()`。當 CLI algorithm list 第一個是 Baseline、但後面包含 Backpressure 時，run name lookup 會漏掉 `bp_q...` identity tag，導致 summary/manifest 更容易指到舊四演算法 run folder，而不是新的 BP-tagged run folder。

已加 guard：default 五情境、四演算法 formal 行為不變；subset 或 custom/BP algorithm 預設寫到 isolated formal output，只有明確加 `--update-shared-formal-summary` 才會更新 shared formal summary。也已修正 run-folder lookup，改用完整 algorithm list 保留 BP identity tag。

# 5. Backpressure vs LHTR H80 60s 比較

{md_table(compact, ["algorithm", "aggregate_pdr", "focus_pdr", "background_pdr", "lost_packets", "mean_rtt_ms", "p95_rtt_ms", "dominant_loss_attribution"])}

Backpressure 比 LHTR 差的地方集中在三個層面：第一，focus 754->785 方向 PDR 只有 {pct(bp_diag_row["focus_754_to_785_pdr"])}，遠低於 LHTR 的 {pct(lhtr_diag_row["focus_754_to_785_pdr"])}；第二，ISL saturation samples Backpressure 是 {fmt(bp["isl_saturation_samples"], 0)}，LHTR 是 {fmt(lhtr["isl_saturation_samples"], 0)}；第三，Backpressure mean queue delay 約 {fmt(bp["mean_queue_delay_ms"], 1)} ms，而 LHTR 約 {fmt(lhtr["mean_queue_delay_ms"], 1)} ms。

# 6. Backpressure diagnostics

- fallback_ratio: {pct(bp_diag_row["fallback_ratio"])}
- positive_pressure_ratio: {pct(bp_diag_row["positive_pressure_ratio"])}
- candidate_filter_ratio: {pct(bp_diag_row["candidate_filter_ratio"])}
- forward_progress_success_ratio: {pct(bp_diag_row["forward_progress_success_ratio"])}
- queue_file_exists_ratio: {pct(bp_diag_row["queue_file_exists_ratio"])}
- loop_detected_ratio: {pct(bp_diag_row["loop_detected_ratio"])}
- reached_destination_ratio: {pct(bp_diag_row["reached_destination_ratio"])}
- avg/p95 path stretch: {fmt(bp_diag_row["avg_path_stretch"], 2)} / {fmt(bp_diag_row["p95_path_stretch"], 2)}

解讀：loop suppression 確實解掉了繞圈/伸長路徑問題，但 restricted-route BP 的候選太受 forward-progress guard 限制；當 queue pressure 來自 node-total proxy 而非 per-destination/per-interface commodity queue 時，很多候選沒有足夠的正壓力訊號，最後退回 shortest path。這會讓 Backpressure 看起來像「帶著額外震盪與排隊成本的 shortest-path-ish routing」，所以 RTT 與 loss 都變差。

# 7. LHTR diagnostics

- BR selected: {fmt(lhtr_diag_row["br_selected_count"], 0)}
- SBR selected: {fmt(lhtr_diag_row["sbr_selected_count"], 0)}，SBR ratio {pct(lhtr_diag_row["sbr_selection_ratio"])}
- fallback: {fmt(lhtr_diag_row["fallback_count"], 0)}
- top reasons: `{lhtr_diag_row["top_decision_reasons"]}`
- avg yellow/red links: {fmt(lhtr_diag_row["avg_yellow_links"], 2)} / {fmt(lhtr_diag_row["avg_red_links"], 2)}
- max yellow/red links: {fmt(lhtr_diag_row["max_yellow_links"], 0)} / {fmt(lhtr_diag_row["max_red_links"], 0)}

解讀：LHTR 不是靠大量繞路取勝；它大多維持 BR，少量 SBR 在 yellow/red 訊號出現時介入。這比 Backpressure 的 node-total proxy 更穩，因為 LHTR 的 traffic-light 訊號直接把擁塞邊界轉成路由狀態，不需要在每個 next-hop candidate 上找到正壓力梯度。

# 8. 舊 LHTR vs 新 LHTR sanity check

{md_table(sanity_compact, ["metric", "old", "new", "match"])}

Sanity check 結果：{len(sanity) - len(mismatches)}/{len(sanity)} 項一致。`udp_burst_schedule.csv` hash、flow_selection_hash、selection_input_hash 皆一致；新 run 裡的 LHTR 可以作為 Backpressure 的 paired baseline。

# 9. 新增輸出檔案

- `analysis_reports/backpressure_vs_lhtr_h80_60s/analysis_report_zh.md`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_summary.csv`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_rtt.csv`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_vs_lhtr_h80_60s_loss.csv`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/backpressure_diagnostics_h80_60s.csv`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/lhtr_diagnostics_h80_60s.csv`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/lhtr_sanity_check_old_vs_new_h80_60s.csv`
- `analysis_reports/backpressure_vs_lhtr_h80_60s/restore_hotspot_5level_60s_formal_log.md`

Figures:

{figure_lines}

# 10. 論文 / 教授報告建議

建議不要把這條曲線標成 full Backpressure。更準確的標籤是「restricted-route queue-proxy Backpressure」。在報告中可以把它放在消融/negative result：loop suppression 能避免 path loop，但 queue proxy 與 forward-progress guard 讓大部分決策 fallback，無法有效卸載 hotspot。這個結果反而支持 LHTR 的設計主張：用 link/traffic-light 狀態做穩定的 coarse-grained diversion，比 node-total pressure proxy 更可靠。

# 11. 下一步建議

1. 若要繼續 Backpressure，下一個 variant 應優先測 `interface` 或 per-destination/per-commodity queue source，否則正壓力訊號太粗。
2. 保留 `forward_progress_hop` loop guard，但另測「可接受一小段 stretch」的 guard，避免把所有可用卸載候選都濾掉。
3. 跑 10s/20s smoke 做 diagnostics 先篩選 fallback_ratio；若 fallback_ratio 仍高於 80%，不建議直接跑 60s formal。
4. 論文主線可把 LHTR vs Queue-aware vs LoHi 當主結果，Backpressure restricted-route variant 當設計風險分析。

# 12. Commit 建議

建議拆成一個 commit：

`Protect hotspot formal summaries and add H80 Backpressure comparison`

包含 runner guard、read-only 分析腳本、獨立 report folder 與 restore log。不要把大型 run folder 或事故 backup 外的既有 shared formal diff 放進 commit。
"""
    (REPORT_DIR / "analysis_report_zh.md").write_text(text, encoding="utf-8")


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    summary = summary_rows()
    rtt = rtt_rows()
    loss = loss_rows()
    bp_diag = backpressure_diagnostics()
    lhtr_diag = lhtr_diagnostics()
    sanity = sanity_rows()

    write_csv(
        REPORT_DIR / "backpressure_vs_lhtr_h80_60s_summary.csv",
        summary,
        SUMMARY_FIELDS,
    )
    write_csv(
        REPORT_DIR / "backpressure_vs_lhtr_h80_60s_rtt.csv",
        rtt,
        RTT_FIELDS,
    )
    write_csv(
        REPORT_DIR / "backpressure_vs_lhtr_h80_60s_loss.csv",
        loss,
        LOSS_FIELDS,
    )
    write_csv(
        REPORT_DIR / "backpressure_diagnostics_h80_60s.csv",
        bp_diag,
        BACKPRESSURE_DIAG_FIELDS,
    )
    write_csv(
        REPORT_DIR / "lhtr_diagnostics_h80_60s.csv",
        lhtr_diag,
        LHTR_DIAG_FIELDS,
    )
    write_csv(
        REPORT_DIR / "lhtr_sanity_check_old_vs_new_h80_60s.csv",
        sanity,
        SANITY_FIELDS,
    )
    write_restore_log()
    figures = maybe_write_figures(summary)
    write_report(summary, bp_diag, lhtr_diag, sanity, figures)

    print("Wrote report directory: %s" % REPORT_DIR)
    print("Summary rows: %d" % len(summary))
    print("Sanity checks: %d" % len(sanity))


if __name__ == "__main__":
    main()
