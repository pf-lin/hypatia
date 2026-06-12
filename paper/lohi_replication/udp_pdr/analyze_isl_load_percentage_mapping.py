#!/usr/bin/env python3

import csv
import json
import math
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from dynamic_path_replay import (
    apply_fstate_delta,
    list_fstate_snapshots,
    parse_fstate_delta,
    replay_path,
)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUNS_ROOT = os.path.join(SCRIPT_DIR, "runs")
CALIBRATION_DIR = os.path.join(
    RUNS_ROOT,
    "comparison_calibration",
    "src754_dst785_isl10mbps_gsl100mbps_10s",
)
SCENARIO_SUMMARY_PATH = os.path.join(
    CALIBRATION_DIR, "isl_focused_scenario_summary.csv"
)
BOTTLENECK_CHECK_PATH = os.path.join(
    CALIBRATION_DIR, "isl_gsl_bottleneck_check.csv"
)
NETWORK_DIR = os.path.abspath(
    os.path.join(
        SCRIPT_DIR,
        "..",
        "..",
        "satellite_networks_state",
        "gen_data",
        "oneweb_1200_isls_plus_grid_ground_stations_top_100_"
        "algorithm_free_one_only_over_isls",
    )
)
BASELINE_DYNAMIC_STATE_DIR = os.path.join(
    NETWORK_DIR, "dynamic_state_1000ms_for_200s"
)
OUTPUT_DIR = os.path.join(
    SCRIPT_DIR, "analysis_reports", "isl_load_percentage_mapping"
)

QUEUE_AWARE = "algorithm_queue_aware_over_isls"
BASELINE = "algorithm_free_one_only_over_isls"
NUM_SATELLITES = 720
NUM_NODES = 820

TRAFFIC_LABELS = [
    ("Low", 0.0, 50.0),
    ("Medium", 50.0, 70.0),
    ("High", 70.0, 85.0),
    ("Severe", 85.0, 100.0),
    ("Overload", 100.0, math.inf),
]

# These are observed Queue-aware validation conditions, not traffic labels.
PRESSURE_LOCALIZED_TARGET_P95 = 0.60
PRESSURE_LOCALIZED_LINK_THRESHOLD = 0.80
PRESSURE_SUSTAINED_QUEUE_SAMPLES = 1000
PRESSURE_SUSTAINED_SPAN_S = 4.0
PRESSURE_OVERLOADED_QUEUE_SAMPLES = 25000
PRESSURE_OVERLOADED_SPAN_S = 6.0
PRESSURE_OVERLOADED_LINKS_OVER_90 = 3


def _read_csv(path, columns=None):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame(columns=columns or [])
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns or [])


def _read_json(path):
    with open(path, encoding="utf-8") as f_in:
        return json.load(f_in)


def _bool_text(value):
    return "true" if bool(value) else "false"


def _finite(value, default=math.nan):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _weighted_quantile(values, weights, quantile):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    values = values[valid]
    weights = weights[valid]
    if len(values) == 0:
        return math.nan
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    cutoff = float(quantile) * weights.sum()
    index = int(np.searchsorted(np.cumsum(weights), cutoff, side="left"))
    return float(values[min(index, len(values) - 1)])


def traffic_load_label(offered_percent):
    value = float(offered_percent)
    for label, lower, upper in TRAFFIC_LABELS:
        if lower <= value < upper:
            return label
    return "Unknown"


def observed_pressure_condition(
    target_corridor_p95,
    links_over_80pct,
    links_over_90pct,
    isl_samples_at_capacity,
    sustained_saturation_duration_s,
):
    target_p95 = _finite(target_corridor_p95, 0.0)
    links80 = int(links_over_80pct)
    links90 = int(links_over_90pct)
    samples = int(isl_samples_at_capacity)
    span_s = _finite(sustained_saturation_duration_s, 0.0)

    if samples >= PRESSURE_OVERLOADED_QUEUE_SAMPLES or (
        span_s >= PRESSURE_OVERLOADED_SPAN_S
        and links90 >= PRESSURE_OVERLOADED_LINKS_OVER_90
    ):
        return "Overloaded"
    if samples >= PRESSURE_SUSTAINED_QUEUE_SAMPLES or (
        span_s >= PRESSURE_SUSTAINED_SPAN_S and links90 > 0
    ):
        return "Sustained congestion"
    if (
        target_p95 >= PRESSURE_LOCALIZED_TARGET_P95
        or links80 > 0
        or samples > 0
    ):
        return "Localized congestion"
    return "Non-congested"


def _read_schedule(path):
    rows = []
    with open(path, newline="") as f_in:
        for raw in csv.reader(f_in):
            if not raw:
                continue
            start_ns = int(raw[4])
            duration_ns = int(raw[5])
            rows.append(
                {
                    "flow_id": int(raw[0]),
                    "src": int(raw[1]),
                    "dst": int(raw[2]),
                    "rate_mbps": float(raw[3]),
                    "start_ns": start_ns,
                    "end_ns": start_ns + duration_ns,
                    "metadata": raw[7] if len(raw) > 7 else "",
                }
            )
    return rows


def _directed_isl_count():
    isls_path = os.path.join(NETWORK_DIR, "isls.txt")
    with open(isls_path, encoding="utf-8") as f_in:
        undirected = sum(1 for line in f_in if line.strip())
    return 2 * undirected


def _build_reference_states(traffic_stop_ns):
    snapshots = [
        item
        for item in list_fstate_snapshots(BASELINE_DYNAMIC_STATE_DIR)
        if item[0] < traffic_stop_ns
    ]
    states = []
    state = {}
    for index, (snapshot_time_ns, path) in enumerate(snapshots):
        apply_fstate_delta(state, parse_fstate_delta(path))
        next_time_ns = (
            snapshots[index + 1][0]
            if index + 1 < len(snapshots)
            else traffic_stop_ns
        )
        states.append(
            (
                snapshot_time_ns,
                min(next_time_ns, traffic_stop_ns),
                dict(state),
            )
        )
    return states


def _reference_path_metrics(flows, states, traffic_stop_ns, isl_capacity_mbps):
    demand_integral = 0.0
    initial_demand = 0.0
    total_offered_integral = 0.0
    replay_attempt_duration = 0.0
    replay_success_duration = 0.0
    active_edges = set()
    peak_edge_rate_mbps = 0.0
    failure_counts = defaultdict(int)

    for state_index, (interval_start, interval_end, state) in enumerate(states):
        edge_rates = defaultdict(float)
        for flow in flows:
            overlap_start = max(interval_start, flow["start_ns"])
            overlap_end = min(interval_end, flow["end_ns"], traffic_stop_ns)
            if overlap_end <= overlap_start:
                continue
            duration_s = (overlap_end - overlap_start) / 1e9
            replay_attempt_duration += duration_s
            result = replay_path(
                state,
                flow["src"],
                flow["dst"],
                NUM_SATELLITES,
                NUM_NODES,
            )
            if not result.success:
                failure_counts[result.status] += 1
                continue
            replay_success_duration += duration_s
            hop_count = len(result.isl_interface_keys)
            demand_integral += flow["rate_mbps"] * hop_count * duration_s
            total_offered_integral += flow["rate_mbps"] * duration_s
            for key in result.isl_interface_keys:
                active_edges.add(key)
                edge_rates[key] += flow["rate_mbps"]
            if state_index == 0 and interval_start == 0:
                initial_demand += flow["rate_mbps"] * hop_count
        if edge_rates:
            peak_edge_rate_mbps = max(
                peak_edge_rate_mbps, max(edge_rates.values())
            )

    traffic_duration_s = traffic_stop_ns / 1e9
    reference_demand = demand_integral / traffic_duration_s
    time_average_offered = total_offered_integral / traffic_duration_s
    success_ratio = (
        replay_success_duration / replay_attempt_duration
        if replay_attempt_duration > 0
        else 0.0
    )
    confidence = (
        "high"
        if success_ratio >= 1.0 - 1e-12
        else "medium"
        if success_ratio >= 0.99
        else "low"
    )
    return {
        "reference_total_isl_hop_demand_mbps_hops": reference_demand,
        "initial_reference_total_isl_hop_demand_mbps_hops": initial_demand,
        "reference_average_isl_hop_count": (
            reference_demand / time_average_offered
            if time_average_offered > 0
            else math.nan
        ),
        "reference_active_directed_isl_link_count": len(active_edges),
        "peak_reference_link_offered_rate_mbps": peak_edge_rate_mbps,
        "peak_reference_link_offered_load_percent": (
            100.0 * peak_edge_rate_mbps / isl_capacity_mbps
        ),
        "reference_replay_success_ratio": success_ratio,
        "reference_confidence": confidence,
        "reference_replay_failures": ";".join(
            "%s=%d" % item for item in sorted(failure_counts.items())
        ),
    }


def _read_interval_csv(path, value_name, traffic_stop_ns):
    columns = ["from", "to", "interval_start_ns", "interval_end_ns", value_name]
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame(columns=columns + ["duration_ns"])
    frame = pd.read_csv(path, header=None, names=columns)
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna()
    frame["interval_start_ns"] = frame["interval_start_ns"].clip(lower=0)
    frame["interval_end_ns"] = frame["interval_end_ns"].clip(
        upper=traffic_stop_ns
    )
    frame["duration_ns"] = (
        frame["interval_end_ns"] - frame["interval_start_ns"]
    )
    return frame[frame["duration_ns"] > 0].copy()


def _target_corridor_edges(run_dir):
    frame = _read_csv(os.path.join(run_dir, "isl_corridor_load_summary.csv"))
    if len(frame) == 0:
        return set()
    flag = frame["on_target_focus_corridor"].astype(str).str.lower()
    frame = frame[flag.isin(["true", "1"])]
    return {
        (int(row["edge_from"]), int(row["edge_to"]))
        for _, row in frame.iterrows()
    }


def _with_zero_weight(values, weights, expected_weight):
    present_weight = float(np.asarray(weights, dtype=float).sum())
    missing_weight = max(0.0, float(expected_weight) - present_weight)
    if missing_weight <= 0:
        return np.asarray(values, dtype=float), np.asarray(weights, dtype=float)
    return (
        np.append(np.asarray(values, dtype=float), 0.0),
        np.append(np.asarray(weights, dtype=float), missing_weight),
    )


def _utilization_metrics(
    logs_dir, target_edges, traffic_stop_ns, directed_isl_count
):
    frame = _read_interval_csv(
        os.path.join(logs_dir, "isl_utilization.csv"),
        "utilization",
        traffic_stop_ns,
    )
    if len(frame) == 0:
        return {
            key: math.nan
            for key in [
                "all_isl_mean",
                "all_isl_p50",
                "all_isl_p95",
                "all_isl_p99",
                "all_isl_max",
                "active_isl_mean",
                "active_isl_p50",
                "active_isl_p95",
                "active_isl_p99",
                "active_isl_max",
                "target_corridor_mean",
                "target_corridor_p50",
                "target_corridor_p95",
                "target_corridor_p99",
                "target_corridor_max",
                "target_corridor_all_p95",
                "top1_isl_utilization",
                "top5_isl_mean_utilization",
                "top10_isl_mean_utilization",
            ]
        } | {
            "active_directed_isl_count": 0,
            "target_corridor_edge_count": len(target_edges),
            "links_over_60pct": 0,
            "links_over_70pct": 0,
            "links_over_80pct": 0,
            "links_over_90pct": 0,
            "links_over_100pct": 0,
            "utilization_source": "unknown",
        }

    traffic_duration_ns = float(traffic_stop_ns)
    all_expected_weight = directed_isl_count * traffic_duration_ns
    all_values, all_weights = _with_zero_weight(
        frame["utilization"], frame["duration_ns"], all_expected_weight
    )
    active = frame[frame["utilization"] > 0].copy()
    max_by_link = frame.groupby(["from", "to"])["utilization"].max()
    link_integrals = (
        frame.assign(
            utilization_duration=frame["utilization"] * frame["duration_ns"]
        )
        .groupby(["from", "to"])["utilization_duration"]
        .sum()
    )
    link_means = (link_integrals / traffic_duration_ns).sort_values(
        ascending=False
    )

    target_mask = pd.Series(
        [
            (int(row["from"]), int(row["to"])) in target_edges
            for _, row in frame.iterrows()
        ],
        index=frame.index,
    )
    target_all = frame[target_mask].copy()
    target_active = target_all[target_all["utilization"] > 0].copy()
    target_values, target_weights = _with_zero_weight(
        target_all["utilization"],
        target_all["duration_ns"],
        len(target_edges) * traffic_duration_ns,
    )

    def active_quantile(quantile):
        return _weighted_quantile(
            active["utilization"], active["duration_ns"], quantile
        )

    def target_quantile(quantile):
        return _weighted_quantile(
            target_active["utilization"],
            target_active["duration_ns"],
            quantile,
        )

    return {
        "all_isl_mean": float(
            np.average(all_values, weights=all_weights)
        ),
        "all_isl_p50": _weighted_quantile(all_values, all_weights, 0.50),
        "all_isl_p95": _weighted_quantile(all_values, all_weights, 0.95),
        "all_isl_p99": _weighted_quantile(all_values, all_weights, 0.99),
        "all_isl_max": float(frame["utilization"].max()),
        "active_isl_mean": (
            float(
                np.average(
                    active["utilization"], weights=active["duration_ns"]
                )
            )
            if len(active)
            else 0.0
        ),
        "active_isl_p50": active_quantile(0.50),
        "active_isl_p95": active_quantile(0.95),
        "active_isl_p99": active_quantile(0.99),
        "active_isl_max": float(active["utilization"].max()) if len(active) else 0.0,
        "active_directed_isl_count": int(
            active[["from", "to"]].drop_duplicates().shape[0]
        ),
        "target_corridor_mean": (
            float(
                np.average(
                    target_active["utilization"],
                    weights=target_active["duration_ns"],
                )
            )
            if len(target_active)
            else 0.0
        ),
        "target_corridor_p50": target_quantile(0.50),
        "target_corridor_p95": target_quantile(0.95),
        "target_corridor_p99": target_quantile(0.99),
        "target_corridor_max": (
            float(target_active["utilization"].max())
            if len(target_active)
            else 0.0
        ),
        "target_corridor_all_p95": _weighted_quantile(
            target_values, target_weights, 0.95
        ),
        "target_corridor_edge_count": len(target_edges),
        "top1_isl_utilization": (
            float(link_means.iloc[0]) if len(link_means) else 0.0
        ),
        "top5_isl_mean_utilization": (
            float(link_means.head(5).mean()) if len(link_means) else 0.0
        ),
        "top10_isl_mean_utilization": (
            float(link_means.head(10).mean()) if len(link_means) else 0.0
        ),
        "links_over_60pct": int((max_by_link >= 0.60).sum()),
        "links_over_70pct": int((max_by_link >= 0.70).sum()),
        "links_over_80pct": int((max_by_link >= 0.80).sum()),
        "links_over_90pct": int((max_by_link >= 0.90).sum()),
        "links_over_100pct": int((max_by_link >= 1.0 - 1e-9).sum()),
        "utilization_source": "measured_throughput",
    }


def _queue_saturation_metrics(run_dir, algorithm, traffic_stop_ns):
    frame = _read_csv(
        os.path.join(
            run_dir,
            "comparison_packet_delivery",
            "core",
            "congested_interfaces_summary.csv",
        )
    )
    if len(frame) == 0:
        return {
            "isl_samples_at_capacity": 0,
            "gsl_samples_at_capacity": 0,
            "sustained_saturation_duration_s": 0.0,
            "saturated_isl_interface_count": 0,
            "long_saturation_isl_interface_count": 0,
        }
    frame = frame[frame["algorithm"].astype(str) == algorithm].copy()
    frame["samples_at_capacity"] = pd.to_numeric(
        frame["samples_at_capacity"], errors="coerce"
    ).fillna(0)
    isl = frame[frame["link_type"].astype(str).str.upper() == "ISL"].copy()
    gsl = frame[frame["link_type"].astype(str).str.upper() == "GSL"].copy()
    if len(isl):
        first = pd.to_numeric(
            isl["first_saturation_time_ns"], errors="coerce"
        )
        last = pd.to_numeric(
            isl["last_saturation_time_ns"], errors="coerce"
        )
        spans = (
            np.minimum(last, traffic_stop_ns) - np.maximum(first, 0)
        ).clip(lower=0) / 1e9
    else:
        spans = pd.Series(dtype=float)
    traffic_window_summary = _read_csv(BOTTLENECK_CHECK_PATH)
    selected_summary = traffic_window_summary[
        (traffic_window_summary["run_folder"].astype(str) == os.path.basename(run_dir))
        & (traffic_window_summary["algorithm"].astype(str) == algorithm)
    ]
    summary_row = (
        selected_summary.iloc[0].to_dict() if len(selected_summary) else {}
    )
    isl_samples = int(
        float(
            summary_row.get(
                "isl_samples_at_capacity",
                isl["samples_at_capacity"].sum(),
            )
            or 0
        )
    )
    gsl_samples = int(
        float(
            summary_row.get(
                "gsl_samples_at_capacity",
                gsl["samples_at_capacity"].sum(),
            )
            or 0
        )
    )
    return {
        "isl_samples_at_capacity": isl_samples,
        "gsl_samples_at_capacity": gsl_samples,
        "sustained_saturation_duration_s": (
            float(spans.max()) if len(spans) else 0.0
        ),
        "saturated_isl_interface_count": int(
            (isl["samples_at_capacity"] > 0).sum()
        ),
        "long_saturation_isl_interface_count": int(
            (spans >= PRESSURE_SUSTAINED_SPAN_S).sum()
        ),
    }


def _loss_metrics(run_dir, algorithm):
    breakdown = _read_csv(
        os.path.join(
            run_dir,
            "comparison_packet_delivery",
            "core",
            "loss_attribution_breakdown_v3.csv",
        )
    )
    selected = breakdown[breakdown["algorithm"].astype(str) == algorithm]
    row = selected.iloc[0].to_dict() if len(selected) else {}
    names = [
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
    values = {name: int(float(row.get(name, 0) or 0)) for name in names}
    maximum = max(values.values()) if values else 0
    dominant = max(values, key=values.get) if maximum > 0 else "no_loss"
    return values | {"dominant_loss_attribution": dominant}


def _weighted_pdr(frame):
    if len(frame) == 0:
        return math.nan
    sent = float(frame["sent_packets"].sum())
    return float(frame["received_packets"].sum()) / sent if sent > 0 else math.nan


def _pdr_metrics(run_dir, algorithm):
    core_dir = os.path.join(run_dir, "comparison_packet_delivery", "core")
    summary = _read_csv(os.path.join(core_dir, "summary_by_algorithm.csv"))
    selected = summary[summary["algorithm"].astype(str) == algorithm]
    row = selected.iloc[0].to_dict() if len(selected) else {}
    per_flow = _read_csv(os.path.join(core_dir, "per_flow_delivery.csv"))
    per_flow = per_flow[per_flow["algorithm"].astype(str) == algorithm]
    background = per_flow[
        per_flow["flow_class"].astype(str) == "background"
    ]
    return {
        "aggregate_pdr": _finite(row.get("aggregate_pdr")),
        "focus_pdr": _finite(row.get("focus_flow_pdr")),
        "background_pdr": _weighted_pdr(background),
        "min_flow_pdr": _finite(row.get("min_flow_pdr")),
        "p5_flow_pdr": _finite(row.get("p5_flow_pdr")),
        "lost_packets": int(float(row.get("total_lost_packets", 0) or 0)),
        "failed_flow_count": int(float(row.get("failed_flow_count", 0) or 0)),
    }


def _algorithms_available(run_dir):
    core_summary = _read_csv(
        os.path.join(
            run_dir,
            "comparison_packet_delivery",
            "core",
            "summary_by_algorithm.csv",
        )
    )
    algorithms = []
    for algorithm in core_summary.get("algorithm", pd.Series(dtype=str)):
        finished = os.path.join(run_dir, algorithm, "logs_ns3", "finished.txt")
        if os.path.exists(finished):
            algorithms.append(str(algorithm))
    return sorted(set(algorithms))


def _files_available(run_dir, algorithms):
    checks = {
        "run_metadata": any(
            os.path.exists(os.path.join(run_dir, algorithm, "run_metadata.json"))
            for algorithm in algorithms
        ),
        "config_ns3": any(
            os.path.exists(
                os.path.join(run_dir, algorithm, "config_ns3.properties")
            )
            for algorithm in algorithms
        ),
        "udp_burst_schedule": any(
            os.path.exists(
                os.path.join(run_dir, algorithm, "udp_burst_schedule.csv")
            )
            for algorithm in algorithms
        ),
        "flow_selection_diagnostics": os.path.exists(
            os.path.join(run_dir, "flow_selection_diagnostics.csv")
        ),
        "corridor_concentration_summary": os.path.exists(
            os.path.join(run_dir, "corridor_concentration_summary.csv")
        ),
        "isl_corridor_load_summary": os.path.exists(
            os.path.join(run_dir, "isl_corridor_load_summary.csv")
        ),
        "comparison_packet_delivery": os.path.isdir(
            os.path.join(run_dir, "comparison_packet_delivery")
        ),
    }
    return ";".join("%s=%s" % (key, _bool_text(value)) for key, value in checks.items())


def _definition_rows():
    rows = []
    for label, lower, upper in TRAFFIC_LABELS:
        upper_text = "" if math.isinf(upper) else upper
        rows.append(
            {
                "definition_type": "traffic_load_label",
                "label": label,
                "metric": "offered_isl_resource_load_percent",
                "rule": "%s <= offered load < %s"
                % (lower, upper_text if upper_text != "" else "infinity"),
                "uses_pdr": "false",
                "notes": (
                    "Official routing-independent label; denominator is total "
                    "directed constellation ISL capacity."
                ),
            }
        )
    rows.extend(
        [
            {
                "definition_type": "observed_pressure_condition",
                "label": "Non-congested",
                "metric": "Queue-aware observed throughput and queue pressure",
                "rule": (
                    "target active p95 < 0.60, links over 80% = 0, and "
                    "ISL capacity samples = 0"
                ),
                "uses_pdr": "false",
                "notes": "Adaptive observed validation only.",
            },
            {
                "definition_type": "observed_pressure_condition",
                "label": "Localized congestion",
                "metric": "Queue-aware observed throughput and queue pressure",
                "rule": (
                    "target active p95 >= 0.60, or links over 80% > 0, or "
                    "0 < ISL capacity samples < 1000; sustained/overloaded "
                    "rules take precedence"
                ),
                "uses_pdr": "false",
                "notes": "Adaptive observed validation only.",
            },
            {
                "definition_type": "observed_pressure_condition",
                "label": "Sustained congestion",
                "metric": "Queue-aware observed throughput and queue pressure",
                "rule": (
                    "ISL capacity samples >= 1000, or saturation observation "
                    "span >= 4 s with at least one link over 90%; overloaded "
                    "rule takes precedence"
                ),
                "uses_pdr": "false",
                "notes": (
                    "Saturation duration is a first-to-last observation-span "
                    "proxy, not proof of continuous saturation."
                ),
            },
            {
                "definition_type": "observed_pressure_condition",
                "label": "Overloaded",
                "metric": "Queue-aware observed throughput and queue pressure",
                "rule": (
                    "ISL capacity samples >= 25000, or saturation observation "
                    "span >= 6 s and links over 90% >= 3"
                ),
                "uses_pdr": "false",
                "notes": "Adaptive observed validation only.",
            },
            {
                "definition_type": "gsl_safety_gate",
                "label": "Safe",
                "metric": "GSL capacity, queue saturation, and associated loss",
                "rule": (
                    "GSL capacity = 100 Mbps, GSL capacity samples = 0, "
                    "GSL-associated loss = 0, and mixed loss does not dominate"
                ),
                "uses_pdr": "false",
                "notes": (
                    "Associated loss is time/path correlation, not physical "
                    "drop proof."
                ),
            },
        ]
    )
    return rows


def _format_setting(load_level, background_flow_count):
    return "load=%.1f,bg=%d" % (float(load_level), int(background_flow_count))


def _candidate_rows(mapping, pressure, pdr):
    preferred = [(1.0, 16), (1.8, 24), (2.0, 32), (2.4, 40), (2.8, 56)]
    pdr_lookup = {
        (row["setting_id"], row["algorithm"]): row for _, row in pdr.iterrows()
    }
    pressure_lookup = {
        (row["setting_id"], row["algorithm"]): row
        for _, row in pressure.iterrows()
    }
    rows = []
    for index, (load_level, bg_count) in enumerate(preferred, 1):
        selected = mapping[
            np.isclose(mapping["load_level"], load_level)
            & (mapping["background_flow_count"] == bg_count)
        ]
        if len(selected) == 0:
            continue
        row = selected.iloc[0]
        setting_id = row["setting_id"]
        observed = pressure_lookup.get((setting_id, QUEUE_AWARE), {})

        def pdr_value(algorithm):
            outcome = pdr_lookup.get((setting_id, algorithm), {})
            return outcome.get("aggregate_pdr", math.nan)

        condition = observed.get(
            "observed_pressure_condition", "Unknown"
        )
        reason = (
            "Provisional pressure-span anchor: official global load label is "
            "%s, while Queue-aware observed validation is %s. It is not yet "
            "a valid 40/60/80/90/100%% formal-load anchor."
            % (row["traffic_load_label"], condition)
        )
        rows.append(
            {
                "scenario_id": "P%d" % index,
                "recommended_label": "%s / %s"
                % (row["traffic_load_label"], condition),
                "setting_id": setting_id,
                "load_level": load_level,
                "background_flow_count": bg_count,
                "offered_isl_resource_load_percent": row[
                    "offered_isl_resource_load_percent"
                ],
                "traffic_load_label": row["traffic_load_label"],
                "observed_pressure_condition": condition,
                "gsl_bottleneck_flag": row["gsl_bottleneck_flag"],
                "safe_for_isl_focused_experiment": row[
                    "safe_for_isl_focused_experiment"
                ],
                "baseline_pdr_if_available": pdr_value(BASELINE),
                "queue_aware_pdr_if_available": pdr_value(QUEUE_AWARE),
                "lohi_pdr_if_available": pdr_value("algorithm_lohi_over_isls"),
                "lhtr_pdr_if_available": pdr_value("algorithm_lhtr_over_isls"),
                "recommended_for_60s": "false",
                "recommended_for_200s": "false",
                "reason": reason,
            }
        )
    return rows


def _save_plots(mapping, pressure, pdr, output_dir):
    qa_pressure = pressure[pressure["algorithm"] == QUEUE_AWARE].copy()
    merged = mapping.merge(qa_pressure, on="setting_id", suffixes=("", "_obs"))
    pdr_plot = pdr.merge(
        mapping[["setting_id", "offered_isl_resource_load_percent"]],
        on="setting_id",
    )

    plt.figure(figsize=(8, 5))
    for algorithm, group in pdr_plot.groupby("algorithm"):
        plt.scatter(
            group["offered_isl_resource_load_percent"],
            group["aggregate_pdr"],
            label=algorithm.replace("algorithm_", "").replace("_over_isls", ""),
            alpha=0.8,
        )
    plt.xlabel("Offered ISL resource load (%)")
    plt.ylabel("Aggregate PDR (outcome only)")
    plt.ylim(0, 1.03)
    plt.grid(alpha=0.25)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "offered_isl_load_vs_pdr.png"), dpi=180)
    plt.close()

    plt.figure(figsize=(8, 5))
    scatter = plt.scatter(
        merged["offered_isl_resource_load_percent"],
        merged["target_corridor_p95"],
        c=merged["background_flow_count"],
        cmap="viridis",
    )
    plt.axhline(PRESSURE_LOCALIZED_TARGET_P95, color="tab:red", linestyle="--")
    plt.xlabel("Offered ISL resource load (%)")
    plt.ylabel("Queue-aware target-corridor active p95")
    plt.colorbar(scatter, label="Background flow count")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(
        os.path.join(
            output_dir, "offered_isl_load_vs_target_corridor_utilization.png"
        ),
        dpi=180,
    )
    plt.close()

    plt.figure(figsize=(8, 5))
    plt.scatter(
        merged["offered_isl_resource_load_percent"],
        merged["links_over_90pct"],
        c=merged["load_level"],
        cmap="plasma",
    )
    plt.xlabel("Offered ISL resource load (%)")
    plt.ylabel("Directed ISLs with interval max >= 90%")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, "offered_isl_load_vs_links_over_90pct.png"),
        dpi=180,
    )
    plt.close()

    condition_order = [
        "Non-congested",
        "Localized congestion",
        "Sustained congestion",
        "Overloaded",
    ]
    colors = {
        "Non-congested": "tab:green",
        "Localized congestion": "tab:blue",
        "Sustained congestion": "tab:orange",
        "Overloaded": "tab:red",
    }
    plt.figure(figsize=(9, 6))
    for condition in condition_order:
        group = merged[merged["observed_pressure_condition"] == condition]
        if len(group):
            plt.scatter(
                group["offered_isl_resource_load_percent"],
                group["target_corridor_p95"],
                s=45 + group["links_over_90pct"] * 5,
                color=colors[condition],
                label=condition,
                alpha=0.8,
            )
    plt.xlabel("Official offered ISL resource load (%)")
    plt.ylabel("Queue-aware target-corridor active p95")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, "scenario_mapping_overview.png"), dpi=180
    )
    plt.close()

    plt.figure(figsize=(9, 6))
    for condition in condition_order:
        group = merged[merged["observed_pressure_condition"] == condition]
        if len(group):
            plt.scatter(
                group["offered_isl_resource_load_percent"],
                group["isl_samples_at_capacity"].clip(lower=1),
                color=colors[condition],
                label=condition,
                alpha=0.8,
            )
    plt.yscale("log")
    plt.xlabel("Official offered ISL resource load (%)")
    plt.ylabel("Queue-aware ISL samples at queue capacity (log scale)")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, "traffic_load_vs_observed_pressure.png"),
        dpi=180,
    )
    plt.close()


def _write_notes(output_dir):
    text = """# Congestion Mapping Notes

## Official traffic-load definition

`offered_isl_resource_load_percent = 100 * sum(flow_rate_mbps * time-averaged baseline ISL hops) / (directed_ISL_count * ISL_capacity_mbps)`

The official reference replays the existing one-second Baseline/free-one-only
forwarding-state snapshots over the 0-8 s traffic-generation window. The
supplemental fixed reference uses the first snapshot at `t=0`.

The official denominator is all 2,880 directed ISLs at 10 Mbps each. This is a
global constellation resource-demand fraction. It is intentionally independent
of Baseline PDR and Queue-aware PDR, but it can strongly dilute a geographically
localized hotspot.

## Supplemental diagnostics

- `reference_active_capacity_load_percent` normalizes the same hop demand by
  the capacity of directed ISLs touched by the Baseline reference paths.
- `peak_reference_link_offered_load_percent` is the largest per-snapshot
  reference-path offered demand on one directed ISL.
- Neither supplemental metric replaces the official global traffic label.

## Observed pressure

Observed pressure is reported per algorithm. The mapping table uses the
Queue-aware row only as adaptive validation because Queue-aware is the only
algorithm available for all 30 settings. It does not define
`traffic_load_label`.

- Non-congested: target-corridor active p95 < 0.60, no link reaches 80%, and
  no ISL queue sample reaches capacity.
- Localized congestion: target-corridor active p95 >= 0.60, at least one link
  reaches 80%, or a nonzero number of ISL queue samples reaches capacity.
- Sustained congestion: at least 1,000 ISL queue samples reach capacity, or
  the first-to-last saturation observation span is at least 4 s while at least
  one link reaches 90%.
- Overloaded: at least 25,000 ISL queue samples reach capacity, or the
  saturation observation span is at least 6 s while at least three links reach
  90%.

The saturation duration is a first-to-last observation-span proxy from the
existing congestion summary, not proof of uninterrupted queue saturation.
Utilization comes from measured throughput. GSL utilization is not treated as
throughput; GSL safety uses queue saturation and associated-loss diagnostics.
Associated loss is time/path correlation, not physical-drop proof.

## PDR role

PDR is joined only after traffic labels and observed-pressure conditions have
been assigned. It is an algorithm outcome and never participates in either
definition.
"""
    with open(
        os.path.join(output_dir, "congestion_mapping_notes.md"),
        "w",
        encoding="utf-8",
    ) as f_out:
        f_out.write(text)


def _markdown_table(frame, columns, limit=None):
    selected = frame[columns]
    if limit is not None:
        selected = selected.head(limit)
    headers = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = []
    for _, row in selected.iterrows():
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                values.append("" if not math.isfinite(value) else "%.4f" % value)
            else:
                values.append(str(value))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join([headers, separator] + rows)


def _write_report(mapping, pressure, pdr, candidates, output_dir):
    qa_pressure = pressure[pressure["algorithm"] == QUEUE_AWARE]
    merged = mapping.merge(
        qa_pressure[
            [
                "setting_id",
                "target_corridor_p95",
                "links_over_90pct",
                "isl_samples_at_capacity",
            ]
        ],
        on="setting_id",
    )
    minimum = mapping["offered_isl_resource_load_percent"].min()
    maximum = mapping["offered_isl_resource_load_percent"].max()
    labels = ", ".join(
        "%s=%d" % item
        for item in mapping["traffic_load_label"].value_counts().sort_index().items()
    )
    conditions = ", ".join(
        "%s=%d" % item
        for item in qa_pressure["observed_pressure_condition"]
        .value_counts()
        .sort_index()
        .items()
    )
    max_row = mapping.loc[
        mapping["offered_isl_resource_load_percent"].idxmax()
    ]
    target_rows = []
    for target in [40, 60, 80, 90, 100]:
        index = (
            mapping["offered_isl_resource_load_percent"] - target
        ).abs().idxmin()
        row = mapping.loc[index]
        target_rows.append(
            {
                "target_percent": target,
                "nearest_setting": row["setting_id"],
                "actual_percent": row["offered_isl_resource_load_percent"],
                "gap_percent_points": abs(
                    row["offered_isl_resource_load_percent"] - target
                ),
            }
        )
    target_frame = pd.DataFrame(target_rows)
    reference_hops = float(max_row["reference_average_isl_hop_count"])
    target_estimate_rows = []
    for target in [40, 60, 80, 90, 100]:
        required_hop_demand = (
            float(target)
            / 100.0
            * float(max_row["total_directed_isl_capacity_mbps"])
        )
        estimated_rate = required_hop_demand / reference_hops
        estimated_total_flow_count = int(math.ceil(estimated_rate / 5.0))
        target_estimate_rows.append(
            {
                "target_percent": target,
                "required_hop_demand_Mbps_hops": required_hop_demand,
                "estimated_total_rate_Mbps": estimated_rate,
                "estimated_bg_at_5Mbps_per_flow": max(
                    0, estimated_total_flow_count - 2
                ),
            }
        )
    target_estimate_frame = pd.DataFrame(target_estimate_rows)

    qa_pdr = pdr[pdr["algorithm"] == QUEUE_AWARE]
    baseline_pdr = pdr[pdr["algorithm"] == BASELINE][
        ["setting_id", "aggregate_pdr", "focus_pdr", "background_pdr"]
    ]
    pdr_summary = (
        "Queue-aware aggregate PDR 範圍為 %.4f-%.4f；Baseline 只有兩個 "
        "既有 outcome 點：\n\n%s"
        % (
            qa_pdr["aggregate_pdr"].min(),
            qa_pdr["aggregate_pdr"].max(),
            _markdown_table(
                baseline_pdr,
                [
                    "setting_id",
                    "aggregate_pdr",
                    "focus_pdr",
                    "background_pdr",
                ],
            ),
        )
    )
    observed_summary = (
        "Queue-aware measured ranges: all-ISL p95 %.4f-%.4f、active-ISL "
        "p95 %.4f-%.4f、target-corridor active p95 %.4f-%.4f、"
        "links over 90%% %d-%d、ISL capacity samples %d-%d。"
        % (
            qa_pressure["all_isl_p95"].min(),
            qa_pressure["all_isl_p95"].max(),
            qa_pressure["active_isl_p95"].min(),
            qa_pressure["active_isl_p95"].max(),
            qa_pressure["target_corridor_p95"].min(),
            qa_pressure["target_corridor_p95"].max(),
            qa_pressure["links_over_90pct"].min(),
            qa_pressure["links_over_90pct"].max(),
            qa_pressure["isl_samples_at_capacity"].min(),
            qa_pressure["isl_samples_at_capacity"].max(),
        )
    )
    target_estimate_summary = (
        "以下估算固定使用目前最重 setting 的平均 reference hop "
        "`%.4f`，並假設每 flow 5 Mbps；新增 flows 會改變選流與平均 hop，"
        "所以它只用來決定 targeted sweep 的起始尺度：\n\n%s"
        % (
            reference_hops,
            _markdown_table(
                target_estimate_frame,
                [
                    "target_percent",
                    "required_hop_demand_Mbps_hops",
                    "estimated_total_rate_Mbps",
                    "estimated_bg_at_5Mbps_per_flow",
                ],
            ),
        )
    )

    mapping_table = merged[
        [
            "setting_id",
            "offered_isl_resource_load_percent",
            "traffic_load_label",
            "observed_pressure_condition",
            "safe_for_isl_focused_experiment",
        ]
    ].copy()
    mapping_table["setting_id"] = mapping_table["setting_id"].str.replace(
        "load=", "L", regex=False
    ).str.replace(",bg=", "/B", regex=False)

    report = """# UDP/PDR ISL Load Percentage Mapping 分析報告

## 1. 總結結論

- 已成功用既有 30 個 settings、既有 UDP schedule 與 Baseline shortest-path
  forwarding states 重算 offered ISL resource load；reference replay success
  ratio 全部為 100%%，confidence 為 high。
- PDR 已完全移出 scenario definition。正式 `traffic_load_label` 只由
  routing-independent offered ISL resource load 決定；Queue-aware pressure
  只作 observed validation。
- 30 點的 official global offered load 範圍只有 **%.3f%%-%.3f%%**，
  label 分布為：%s。
- 因此目前資料**無法**對應老師想看的 40/60/80/90/100%%。最重的
  `%s` 也只有 %.3f%%。
- 目前列出 5 個 pressure-span provisional anchors，但全部
  `recommended_for_60s=false`；在補齊正式百分比 mapping 前不應直接跑
  60s 或 200s formal experiment。
- 唯一建議的下一步是：依 official 公式設計 targeted 10s calibration，
  先補可達 40%% 與 60%% 的點並重新檢查 GSL safety，再決定是否往
  80/90/100%% 延伸。

## 2. 資料來源

- `runs/comparison_calibration/src754_dst785_isl10mbps_gsl100mbps_10s/`
  下的 scenario summary 與 GSL/ISL diagnostics。
- 每個 run 的 `run_metadata.json`、`config_ns3.properties`、
  `udp_burst_schedule.csv`、`isl_corridor_load_summary.csv`。
- 每個 algorithm 的 `logs_ns3/isl_utilization.csv` 與既有
  `comparison_packet_delivery/core/` outcome/queue/loss CSV。
- Baseline reference：
  `paper/satellite_networks_state/gen_data/.../dynamic_state_1000ms_for_200s/`
  的 0-7 s、1 s forwarding-state snapshots。
- 30 個 Queue-aware 與 2 個既有 Baseline algorithm outcomes 全部通過
  GSL safety gate。

## 3. 新 congestion definition

正式公式為：

```text
offered_isl_resource_load_%% =
  100 * sum(flow_rate_Mbps * time-averaged baseline ISL hop count)
  / (2880 directed ISLs * 10 Mbps)
```

Official reference 是 traffic window 0-8 s 內的 Baseline shortest-path
time average；supplemental reference 是固定 `t=0` snapshot。兩者皆不使用
任何 PDR。正式 label 門檻為 Low <50%%、Medium 50-70%%、High 70-85%%、
Severe 85-100%%、Overload >=100%%。

由於分母是整個 constellation 的 28,800 Mbps directed-ISL capacity，
它量測的是 global resource fraction，不是 hotspot corridor 的局部 load。
因此報告另外保留 active-reference capacity 與 peak reference-link demand
作診斷，但不拿它們替換 official label。

## 4. Scenario mapping 結果

%s

Queue-aware observed condition 分布為：%s。這些 condition 只描述 adaptive
routing 下量到的壓力，不改變所有 setting 的 official `Low` label。

## 5. Observed ISL pressure

`observed_isl_pressure_summary.csv` 同時包含：

- all-ISL capacity-time mean/p50/p95/p99/max（未使用 capacity 視為 0）。
- active-ISL mean/p50/p95/p99/max。
- target-corridor active p50/p95/p99/max，以及含 idle capacity 的 p95。
- 每條 directed ISL 的 traffic-window mean 所得到的 top1/top5/top10。
- links over 60/70/80/90/100%%、queue capacity samples 與 saturation span。

__OBSERVED_RANGE__

Observed condition exact thresholds 已寫入
`scenario_definition_summary.csv` 與 `congestion_mapping_notes.md`。目前分布：
%s。

## 6. PDR outcome

`pdr_outcome_by_scenario.csv` 保留 aggregate/focus/background/min/p5 PDR、
lost packets、failed-flow count 與 dominant loss attribution。PDR 是
algorithm outcome；產生 traffic label 與 observed condition 的函式均不
讀取 PDR。

__PDR_SUMMARY__

## 7. Formal candidates

%s

這 5 點只能當「observed pressure progression」的 provisional anchors，
不能被寫成 40/60/80/90/100%% formal scenarios。

## 8. 是否需要補 simulation

需要。現有最大 official load 與 40%% 仍差 %.3f percentage points。
下表顯示每個目標目前最近的點：

%s

不建議單純把既有 `load_level` 當百分比，也不建議因 Queue-aware PDR
降低就宣稱已達 Severe/Overload。新 10s calibration 應直接由 reference
hop demand 反推 aggregate offered rate，並持續套用 GSL safety gate。

__TARGET_ESTIMATES__

## 9. 新增檔案

- `isl_load_percentage_mapping.csv`
- `scenario_definition_summary.csv`
- `observed_isl_pressure_summary.csv`
- `pdr_outcome_by_scenario.csv`
- `formal_candidate_table.csv`
- `gsl_safety_check.csv`
- `congestion_mapping_notes.md`
- `analysis_report_zh.md`
- `offered_isl_load_vs_pdr.png`
- `offered_isl_load_vs_target_corridor_utilization.png`
- `offered_isl_load_vs_links_over_90pct.png`
- `scenario_mapping_overview.png`
- `traffic_load_vs_observed_pressure.png`

## 10. 論文敘事建議

### 中文

本研究不直接將實驗參數 `load_level` 解讀為網路負載百分比，也不使用封包
傳遞率反推壅塞等級。每個 traffic setting 先依各 flow 的 offered rate 與
Baseline shortest-path reference 在 traffic window 內的平均 ISL hop count，
計算 capacity-normalized offered ISL resource demand；正式 scenario label
僅由此 routing-independent demand 決定。接著以各演算法實測的 all-ISL、
active-ISL、target-corridor 與 queue-saturation 指標驗證 hotspot 是否形成。
PDR 最後才作為相同 offered-load condition 下的演算法效能結果，因此不會
把某個 routing algorithm 的成功或失敗混入 scenario definition。

### English

We define traffic-load conditions using capacity-normalized ISL resource demand
rather than post-hoc packet-delivery outcomes. For each flow, its offered rate
is multiplied by the time-averaged ISL hop count of a reproducible Baseline
shortest-path reference and then normalized by the total directed ISL capacity.
Observed all-ISL, active-ISL, target-corridor, and queue-saturation metrics are
reported separately to validate whether a localized hotspot emerges under each
routing algorithm. Packet delivery ratio is evaluated only as an algorithmic
outcome under the resulting offered-load condition and never participates in
the congestion-level definition.

## 11. 下一步建議

只做一件事：補 targeted 10s calibration。先用 reference-hop demand 反推能
達到 official 40%% 與 60%% 的 settings，確認 flow selection 可行且 GSL
仍安全後，再決定是否有條件探索 80/90/100%%；暫不跑 60s/200s formal。
""" % (
        minimum,
        maximum,
        labels,
        max_row["setting_id"],
        max_row["offered_isl_resource_load_percent"],
        _markdown_table(
            mapping_table,
            [
                "setting_id",
                "offered_isl_resource_load_percent",
                "traffic_load_label",
                "observed_pressure_condition",
                "safe_for_isl_focused_experiment",
            ],
        ),
        conditions,
        conditions,
        _markdown_table(
            candidates,
            [
                "scenario_id",
                "setting_id",
                "offered_isl_resource_load_percent",
                "traffic_load_label",
                "observed_pressure_condition",
                "recommended_for_60s",
            ],
        ),
        40.0 - maximum,
        _markdown_table(
            target_frame,
            [
                "target_percent",
                "nearest_setting",
                "actual_percent",
                "gap_percent_points",
            ],
        ),
    )
    report = report.replace("__OBSERVED_RANGE__", observed_summary)
    report = report.replace("__PDR_SUMMARY__", pdr_summary)
    report = report.replace("__TARGET_ESTIMATES__", target_estimate_summary)
    with open(
        os.path.join(output_dir, "analysis_report_zh.md"),
        "w",
        encoding="utf-8",
    ) as f_out:
        f_out.write(report)


def build_analysis():
    scenario_summary = _read_csv(SCENARIO_SUMMARY_PATH)
    directed_isl_count = _directed_isl_count()
    traffic_stop_ns = int(
        round(float(scenario_summary["traffic_stop_s"].iloc[0]) * 1e9)
    )
    reference_states = _build_reference_states(traffic_stop_ns)
    mapping_rows = []
    pressure_rows = []
    pdr_rows = []
    gsl_rows = []

    for _, scenario in scenario_summary.iterrows():
        run_folder = str(scenario["run_folder"])
        run_dir = os.path.join(RUNS_ROOT, run_folder)
        algorithms = _algorithms_available(run_dir)
        if not algorithms:
            continue
        metadata_path = os.path.join(
            run_dir, QUEUE_AWARE, "run_metadata.json"
        )
        metadata = _read_json(metadata_path)
        schedule_path = os.path.join(
            run_dir, QUEUE_AWARE, "udp_burst_schedule.csv"
        )
        flows = _read_schedule(schedule_path)
        schedule_total_offered_rate_mbps = sum(
            flow["rate_mbps"] for flow in flows
        )
        isl_capacity = float(metadata["isl_data_rate_megabit_per_s"])
        gsl_capacity = float(metadata["gsl_data_rate_megabit_per_s"])
        reference = _reference_path_metrics(
            flows, reference_states, traffic_stop_ns, isl_capacity
        )
        total_capacity = directed_isl_count * isl_capacity
        offered_percent = (
            100.0
            * reference["reference_total_isl_hop_demand_mbps_hops"]
            / total_capacity
        )
        initial_percent = (
            100.0
            * reference[
                "initial_reference_total_isl_hop_demand_mbps_hops"
            ]
            / total_capacity
        )
        active_count = reference[
            "reference_active_directed_isl_link_count"
        ]
        active_load_percent = (
            100.0
            * reference["reference_total_isl_hop_demand_mbps_hops"]
            / (active_count * isl_capacity)
            if active_count > 0
            else math.nan
        )
        setting_id = _format_setting(
            scenario["load_level"], scenario["background_flow_count"]
        )
        mapping_row = {
            "setting_id": setting_id,
            "run_folder": run_folder,
            "load_level": float(scenario["load_level"]),
            "background_flow_count": int(scenario["background_flow_count"]),
            "per_flow_rate_mbps": float(scenario["per_flow_rate_mbps"]),
            "total_offered_rate_mbps": schedule_total_offered_rate_mbps,
            "configured_total_offered_rate_mbps": float(
                metadata["aggregate_offered_rate_mbps"]
            ),
            "focus_src": int(scenario["focus_src"]),
            "focus_dst": int(scenario["focus_dst"]),
            "duration_s": float(scenario["duration_s"]),
            "traffic_stop_s": float(scenario["traffic_stop_s"]),
            "isl_capacity_mbps": isl_capacity,
            "gsl_capacity_mbps": gsl_capacity,
            "directed_isl_link_count": directed_isl_count,
            "total_directed_isl_capacity_mbps": total_capacity,
            "reference_path_mode": (
                "baseline_shortest_path_time_average_1s_over_traffic_window"
            ),
            "reference_total_isl_hop_demand": reference[
                "reference_total_isl_hop_demand_mbps_hops"
            ],
            "reference_total_isl_hop_demand_unit": "Mbps*ISL-hop",
            "reference_average_isl_hop_count": reference[
                "reference_average_isl_hop_count"
            ],
            "offered_isl_resource_load_percent": offered_percent,
            "initial_snapshot_reference_path_mode": (
                "baseline_shortest_path_fixed_t0"
            ),
            "initial_reference_total_isl_hop_demand": reference[
                "initial_reference_total_isl_hop_demand_mbps_hops"
            ],
            "initial_offered_isl_resource_load_percent": initial_percent,
            "reference_active_directed_isl_link_count": active_count,
            "reference_active_capacity_load_percent": active_load_percent,
            "peak_reference_link_offered_rate_mbps": reference[
                "peak_reference_link_offered_rate_mbps"
            ],
            "peak_reference_link_offered_load_percent": reference[
                "peak_reference_link_offered_load_percent"
            ],
            "traffic_load_label": traffic_load_label(offered_percent),
            "queue_aware_reference_label_if_available": scenario[
                "scenario_congestion_label"
            ],
            "reference_replay_success_ratio": reference[
                "reference_replay_success_ratio"
            ],
            "confidence": reference["reference_confidence"],
            "algorithms_available": ";".join(algorithms),
            "files_available": _files_available(run_dir, algorithms),
            "baseline_improvement_space_flag": _bool_text(
                reference["peak_reference_link_offered_load_percent"] >= 100.0
            ),
            "notes": (
                "Official label uses global directed-ISL capacity and excludes "
                "PDR. Queue-aware label is auxiliary only. Active-capacity and "
                "peak-link values are supplemental hotspot diagnostics."
            ),
        }
        target_edges = _target_corridor_edges(run_dir)
        qa_pressure = None
        qa_gsl = None
        for algorithm in algorithms:
            logs_dir = os.path.join(run_dir, algorithm, "logs_ns3")
            utilization = _utilization_metrics(
                logs_dir,
                target_edges,
                traffic_stop_ns,
                directed_isl_count,
            )
            queue = _queue_saturation_metrics(
                run_dir, algorithm, traffic_stop_ns
            )
            loss = _loss_metrics(run_dir, algorithm)
            condition = observed_pressure_condition(
                utilization["target_corridor_p95"],
                utilization["links_over_80pct"],
                utilization["links_over_90pct"],
                queue["isl_samples_at_capacity"],
                queue["sustained_saturation_duration_s"],
            )
            pressure_row = {
                "setting_id": setting_id,
                "algorithm": algorithm,
                **utilization,
                **queue,
                "observed_pressure_condition": condition,
                "saturation_duration_source": (
                    "first_to_last_capacity_observation_span_proxy"
                ),
                "notes": (
                    "Observed pressure is algorithm-specific validation and "
                    "does not define traffic_load_label."
                ),
            }
            pressure_rows.append(pressure_row)

            pdr_metric = _pdr_metrics(run_dir, algorithm)
            pdr_rows.append(
                {
                    "setting_id": setting_id,
                    "traffic_load_label": mapping_row["traffic_load_label"],
                    "observed_pressure_condition": condition,
                    "algorithm": algorithm,
                    **pdr_metric,
                    "dominant_loss_attribution": loss[
                        "dominant_loss_attribution"
                    ],
                    "pdr_role": "outcome_only_not_scenario_definition",
                }
            )

            gsl_associated = loss["gsl_saturation_associated_loss"]
            mixed_associated = loss["mixed_saturation_associated_loss"]
            mixed_dominates = (
                mixed_associated > 0
                and mixed_associated
                >= max(
                    loss["isl_saturation_associated_loss"],
                    gsl_associated,
                    loss["tail_in_flight_possible_loss"],
                    loss["unclassified_loss"],
                )
            )
            gsl_bottleneck = (
                queue["gsl_samples_at_capacity"] > 0
                or gsl_associated > 0
                or gsl_capacity != 100.0
                or mixed_dominates
            )
            safe = not gsl_bottleneck
            reason_parts = []
            reason_parts.append("GSL capacity %.1f Mbps" % gsl_capacity)
            reason_parts.append(
                "GSL capacity samples %d"
                % queue["gsl_samples_at_capacity"]
            )
            reason_parts.append(
                "GSL-associated loss %d" % gsl_associated
            )
            reason_parts.append(
                "mixed-associated loss %d%s"
                % (
                    mixed_associated,
                    " (dominant)" if mixed_dominates else "",
                )
            )
            gsl_row = {
                "setting_id": setting_id,
                "algorithm": algorithm,
                "gsl_capacity_mbps": gsl_capacity,
                "gsl_bottleneck_flag": _bool_text(gsl_bottleneck),
                "gsl_saturation_samples": queue[
                    "gsl_samples_at_capacity"
                ],
                "gsl_associated_loss": gsl_associated,
                "mixed_associated_loss": mixed_associated,
                "mixed_loss_dominates": _bool_text(mixed_dominates),
                "safe_for_isl_focused_experiment": _bool_text(safe),
                "gsl_safety_reason": "; ".join(reason_parts),
                "gsl_utilization_source": "queue_occupancy_proxy",
                "associated_loss_caveat": (
                    "time/path correlation, not physical-drop proof"
                ),
            }
            gsl_rows.append(gsl_row)
            if algorithm == QUEUE_AWARE:
                qa_pressure = pressure_row
                qa_gsl = gsl_row

        if qa_pressure is None or qa_gsl is None:
            raise RuntimeError(
                "Queue-aware result is missing for %s" % run_folder
            )
        mapping_row["observed_pressure_condition"] = qa_pressure[
            "observed_pressure_condition"
        ]
        mapping_row["gsl_bottleneck_flag"] = qa_gsl[
            "gsl_bottleneck_flag"
        ]
        mapping_row["safe_for_isl_focused_experiment"] = qa_gsl[
            "safe_for_isl_focused_experiment"
        ]
        mapping_rows.append(mapping_row)

    mapping = pd.DataFrame(mapping_rows).sort_values(
        ["offered_isl_resource_load_percent", "background_flow_count"]
    )
    pressure = pd.DataFrame(pressure_rows)
    pdr = pd.DataFrame(pdr_rows)
    gsl = pd.DataFrame(gsl_rows)
    candidates = pd.DataFrame(_candidate_rows(mapping, pressure, pdr))
    definitions = pd.DataFrame(_definition_rows())
    return mapping, definitions, pressure, pdr, candidates, gsl


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    mapping, definitions, pressure, pdr, candidates, gsl = build_analysis()
    outputs = [
        (mapping, "isl_load_percentage_mapping.csv"),
        (definitions, "scenario_definition_summary.csv"),
        (pressure, "observed_isl_pressure_summary.csv"),
        (pdr, "pdr_outcome_by_scenario.csv"),
        (candidates, "formal_candidate_table.csv"),
        (gsl, "gsl_safety_check.csv"),
    ]
    for frame, filename in outputs:
        frame.to_csv(
            os.path.join(OUTPUT_DIR, filename),
            index=False,
            float_format="%.9f",
        )
    _save_plots(mapping, pressure, pdr, OUTPUT_DIR)
    _write_notes(OUTPUT_DIR)
    _write_report(mapping, pressure, pdr, candidates, OUTPUT_DIR)
    print("Wrote ISL load percentage analysis to %s" % OUTPUT_DIR)
    print(
        "Official offered load range: %.6f%% to %.6f%%"
        % (
            mapping["offered_isl_resource_load_percent"].min(),
            mapping["offered_isl_resource_load_percent"].max(),
        )
    )
    print(
        "Traffic labels: %s"
        % mapping["traffic_load_label"].value_counts().to_dict()
    )
    print(
        "Queue-aware observed conditions: %s"
        % pressure[pressure["algorithm"] == QUEUE_AWARE][
            "observed_pressure_condition"
        ]
        .value_counts()
        .to_dict()
    )


if __name__ == "__main__":
    main()
