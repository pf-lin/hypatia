import math
import os
import sys

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-udp-pdr")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(__file__))
from dynamic_run_list import (
    build_arg_parser,
    capacity_identity_tag,
    describe_selection,
    get_udp_pdr_run_list,
    resolve_existing_run,
    validate_focus_pair_arguments,
)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUNS_ROOT = os.path.join(SCRIPT_DIR, "runs")
BASELINE = "algorithm_free_one_only_over_isls"
QUEUE_AWARE = "algorithm_queue_aware_over_isls"

SUMMARY_COLUMNS = [
    "run_folder",
    "focus_src",
    "focus_dst",
    "load_level",
    "background_flow_count",
    "per_flow_rate_mbps",
    "total_offered_rate_mbps",
    "isl_capacity_mbps",
    "gsl_capacity_mbps",
    "duration_s",
    "traffic_stop_s",
    "algorithm",
    "aggregate_pdr",
    "focus_pdr",
    "background_pdr",
    "min_flow_pdr",
    "p5_flow_pdr",
    "lost_packets",
    "max_isl_queue",
    "max_gsl_queue",
    "isl_samples_at_capacity",
    "gsl_samples_at_capacity",
    "p50_isl_utilization",
    "p90_isl_utilization",
    "p95_isl_utilization",
    "max_isl_utilization",
    "p95_gsl_utilization",
    "max_gsl_utilization",
    "links_over_60pct",
    "links_over_80pct",
    "links_over_90pct",
    "links_over_100pct",
    "target_corridor_utilization_p95",
    "target_corridor_utilization_max",
    "gsl_bottleneck_flag",
    "isl_bottleneck_flag",
    "target_corridor_bottleneck_flag",
    "dominant_loss_attribution",
    "algorithm_congestion_label",
    "scenario_reference_algorithm",
    "scenario_reference_available",
    "scenario_congestion_label",
    "reference_p95_isl_utilization",
    "reference_max_isl_utilization",
    "reference_target_corridor_utilization_p95",
    "reference_target_corridor_utilization_max",
    "reference_links_over_80pct",
    "reference_links_over_90pct",
    "reference_links_over_100pct",
    "reference_aggregate_pdr",
    "reference_gsl_bottleneck_flag",
    "baseline_congestion_label",
    "baseline_aggregate_pdr",
    "baseline_improvement_space_flag",
    "recommended_congestion_label",
    "recommended_for_formal",
    "safe_for_isl_focused_experiment",
    "isl_utilization_source",
    "gsl_utilization_source",
    "notes",
]

BOTTLENECK_COLUMNS = [
    "run_folder",
    "load_level",
    "background_flow_count",
    "algorithm",
    "max_isl_queue",
    "max_gsl_queue",
    "isl_samples_at_capacity",
    "gsl_samples_at_capacity",
    "gsl_bottleneck_flag",
    "dominant_loss_attribution",
    "algorithm_congestion_label",
    "scenario_reference_algorithm",
    "scenario_congestion_label",
    "safe_for_isl_focused_experiment",
    "reason",
]

MAPPING_ROWS = [
    {
        "label": "Light",
        "label_scope": "queue_aware_reference_scenario",
        "reference_algorithm": QUEUE_AWARE,
        "p95_isl_utilization_min": 0.0,
        "p95_isl_utilization_max_exclusive": 0.50,
        "additional_rule": "algorithm outcomes are labeled separately",
    },
    {
        "label": "Moderate",
        "label_scope": "queue_aware_reference_scenario",
        "reference_algorithm": QUEUE_AWARE,
        "p95_isl_utilization_min": 0.50,
        "p95_isl_utilization_max_exclusive": 0.70,
        "additional_rule": "algorithm outcomes are labeled separately",
    },
    {
        "label": "High",
        "label_scope": "queue_aware_reference_scenario",
        "reference_algorithm": QUEUE_AWARE,
        "p95_isl_utilization_min": 0.70,
        "p95_isl_utilization_max_exclusive": 0.85,
        "additional_rule": "algorithm outcomes are labeled separately",
    },
    {
        "label": "Severe",
        "label_scope": "queue_aware_reference_scenario",
        "reference_algorithm": QUEUE_AWARE,
        "p95_isl_utilization_min": 0.85,
        "p95_isl_utilization_max_exclusive": 1.00,
        "additional_rule": "algorithm outcomes are labeled separately",
    },
    {
        "label": "Overload",
        "label_scope": "queue_aware_reference_scenario",
        "reference_algorithm": QUEUE_AWARE,
        "p95_isl_utilization_min": 1.00,
        "p95_isl_utilization_max_exclusive": "",
        "additional_rule": (
            "or at least three directed ISLs reach 100% utilization under "
            "the queue-aware reference"
        ),
    },
]

SCENARIO_COLUMNS = [
    "run_folder",
    "focus_src",
    "focus_dst",
    "load_level",
    "background_flow_count",
    "per_flow_rate_mbps",
    "total_offered_rate_mbps",
    "isl_capacity_mbps",
    "gsl_capacity_mbps",
    "duration_s",
    "traffic_stop_s",
    "scenario_reference_algorithm",
    "scenario_reference_available",
    "scenario_congestion_label",
    "reference_p95_isl_utilization",
    "reference_max_isl_utilization",
    "reference_target_corridor_utilization_p95",
    "reference_target_corridor_utilization_max",
    "reference_links_over_80pct",
    "reference_links_over_90pct",
    "reference_links_over_100pct",
    "reference_aggregate_pdr",
    "reference_gsl_bottleneck_flag",
    "baseline_congestion_label",
    "baseline_aggregate_pdr",
    "baseline_improvement_space_flag",
    "safe_for_isl_focused_experiment",
    "recommended_for_formal",
    "notes",
]


def _read_properties(path):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path) as f_in:
        for raw_line in f_in:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return values


def _read_csv(path, columns=None):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame(columns=columns or [])
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns or [])


def _comparison_path(run_dir, filename):
    for subdir in ("core", "diagnostics", ""):
        path = os.path.join(run_dir, "comparison_packet_delivery", subdir, filename)
        if os.path.exists(path):
            return path
    return os.path.join(run_dir, "comparison_packet_delivery", "core", filename)


def _algorithm_row(frame, algorithm):
    if len(frame) == 0 or "algorithm" not in frame.columns:
        return {}
    selected = frame[frame["algorithm"].astype(str) == algorithm]
    return selected.iloc[0].to_dict() if len(selected) else {}


def _weighted_quantile(values, weights, quantile):
    if len(values) == 0:
        return math.nan
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


def _read_interval_csv(path, value_name, traffic_stop_ns):
    columns = ["from", "to", "interval_start_ns", "interval_end_ns", value_name]
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame(columns=columns + ["duration_ns"])
    try:
        frame = pd.read_csv(path, header=None, names=columns)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns + ["duration_ns"])
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna()
    frame["interval_start_ns"] = frame["interval_start_ns"].clip(lower=0)
    frame["interval_end_ns"] = frame["interval_end_ns"].clip(
        upper=traffic_stop_ns
    )
    frame["duration_ns"] = frame["interval_end_ns"] - frame["interval_start_ns"]
    return frame[frame["duration_ns"] > 0].copy()


def _queue_path(logs_dir, link_type):
    history = os.path.join(
        logs_dir, "%s_queue_pkt_history.csv" % link_type.lower()
    )
    if os.path.exists(history) and os.path.getsize(history) > 0:
        return history
    return os.path.join(logs_dir, "%s_queue_pkt.csv" % link_type.lower())


def _queue_metrics(logs_dir, link_type, capacity, traffic_stop_ns):
    frame = _read_interval_csv(
        _queue_path(logs_dir, link_type),
        "queue_pkt",
        traffic_stop_ns,
    )
    if len(frame) == 0:
        return {
            "max_queue": 0.0,
            "samples_at_capacity": 0,
            "p95_ratio": 0.0,
            "max_ratio": 0.0,
        }
    frame["ratio"] = frame["queue_pkt"] / float(capacity)
    return {
        "max_queue": float(frame["queue_pkt"].max()),
        "samples_at_capacity": int((frame["queue_pkt"] >= capacity).sum()),
        "p95_ratio": _weighted_quantile(
            frame["ratio"], frame["duration_ns"], 0.95
        ),
        "max_ratio": float(frame["ratio"].max()),
    }


def _target_corridor_edges(run_dir):
    path = os.path.join(run_dir, "isl_corridor_load_summary.csv")
    frame = _read_csv(path)
    if len(frame) == 0:
        return set()
    flag = frame.get("on_target_focus_corridor", pd.Series(False, index=frame.index))
    selected = frame[flag.astype(str).str.lower().isin(["true", "1"])]
    return {
        (int(row["edge_from"]), int(row["edge_to"]))
        for _, row in selected.iterrows()
    }


def _isl_utilization_metrics(logs_dir, target_edges, traffic_stop_ns):
    frame = _read_interval_csv(
        os.path.join(logs_dir, "isl_utilization.csv"),
        "utilization",
        traffic_stop_ns,
    )
    if len(frame) == 0:
        return {
            "p50": math.nan,
            "p90": math.nan,
            "p95": math.nan,
            "max": math.nan,
            "links_over_60": 0,
            "links_over_80": 0,
            "links_over_90": 0,
            "links_over_100": 0,
            "target_p95": math.nan,
            "target_max": math.nan,
            "source": "unknown",
        }

    # Percentiles use active directed-link time only. Including every idle ISL
    # in a large constellation would make p95 describe network sparsity instead
    # of congestion on the exercised corridor.
    active = frame[frame["utilization"] > 0].copy()
    percentile_frame = active if len(active) else frame
    max_by_link = frame.groupby(["from", "to"])["utilization"].max()
    target_mask = frame.apply(
        lambda row: (int(row["from"]), int(row["to"])) in target_edges,
        axis=1,
    )
    target = frame[target_mask & (frame["utilization"] > 0)]
    if len(target) == 0:
        target = frame[target_mask]

    return {
        "p50": _weighted_quantile(
            percentile_frame["utilization"],
            percentile_frame["duration_ns"],
            0.50,
        ),
        "p90": _weighted_quantile(
            percentile_frame["utilization"],
            percentile_frame["duration_ns"],
            0.90,
        ),
        "p95": _weighted_quantile(
            percentile_frame["utilization"],
            percentile_frame["duration_ns"],
            0.95,
        ),
        "max": float(frame["utilization"].max()),
        "links_over_60": int((max_by_link >= 0.60).sum()),
        "links_over_80": int((max_by_link >= 0.80).sum()),
        "links_over_90": int((max_by_link >= 0.90).sum()),
        "links_over_100": int((max_by_link >= 1.0 - 1e-9).sum()),
        "target_p95": (
            _weighted_quantile(
                target["utilization"], target["duration_ns"], 0.95
            )
            if len(target)
            else math.nan
        ),
        "target_max": (
            float(target["utilization"].max()) if len(target) else math.nan
        ),
        "source": "measured_throughput",
    }


def _weighted_pdr(frame):
    if len(frame) == 0:
        return math.nan
    sent = float(frame["sent_packets"].sum())
    return float(frame["received_packets"].sum()) / sent if sent > 0 else math.nan


def _loss_metrics(run_dir, algorithm):
    breakdown = _read_csv(
        _comparison_path(run_dir, "loss_attribution_breakdown_v3.csv")
    )
    row = _algorithm_row(breakdown, algorithm)
    categories = {
        name: int(float(row.get(name, 0) or 0))
        for name in [
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
    }
    physical = _read_csv(_comparison_path(run_dir, "physical_link_drops.csv"))
    physical = (
        physical[physical["algorithm"].astype(str) == algorithm]
        if len(physical) and "algorithm" in physical.columns
        else pd.DataFrame()
    )
    exact_isl = 0
    exact_gsl = 0
    if len(physical) and "link_type" in physical.columns:
        exact_isl = int(
            (physical["link_type"].astype(str).str.upper() == "ISL").sum()
        )
        exact_gsl = int(
            (physical["link_type"].astype(str).str.upper() == "GSL").sum()
        )
    dominant_candidates = dict(categories)
    dominant_candidates["exact_isl_physical_loss"] = exact_isl
    dominant_candidates["exact_gsl_physical_loss"] = exact_gsl
    maximum = max(dominant_candidates.values()) if dominant_candidates else 0
    dominant = (
        max(dominant_candidates, key=dominant_candidates.get)
        if maximum > 0
        else "no_loss"
    )
    return {
        **categories,
        "exact_isl_physical_loss": exact_isl,
        "exact_gsl_physical_loss": exact_gsl,
        "dominant": dominant,
    }


def congestion_label(p95_utilization, links_over_100):
    if not math.isfinite(float(p95_utilization)):
        return "Unknown"
    value = float(p95_utilization)
    if value >= 1.0 - 1e-9 or int(links_over_100) >= 3:
        return "Overload"
    if value >= 0.85:
        return "Severe"
    if value >= 0.70:
        return "High"
    if value >= 0.50:
        return "Moderate"
    return "Light"


def _bool_text(value):
    return "true" if bool(value) else "false"


def _build_row(run, algorithm):
    run_dir = os.path.join(RUNS_ROOT, run["name"])
    algorithm_dir = os.path.join(run_dir, algorithm)
    comparison_summary = _read_csv(
        _comparison_path(run_dir, "summary_by_algorithm.csv")
    )
    summary = _algorithm_row(comparison_summary, algorithm)
    per_flow = _read_csv(_comparison_path(run_dir, "per_flow_delivery.csv"))
    if len(per_flow) and "algorithm" in per_flow.columns:
        per_flow = per_flow[per_flow["algorithm"].astype(str) == algorithm]
    background = (
        per_flow[per_flow["flow_class"].astype(str) == "background"]
        if len(per_flow) and "flow_class" in per_flow.columns
        else pd.DataFrame()
    )

    properties = _read_properties(
        os.path.join(algorithm_dir, "config_ns3.properties")
    )
    isl_capacity = float(
        properties.get(
            "isl_data_rate_megabit_per_s",
            run["isl_data_rate_megabit_per_s"],
        )
    )
    gsl_capacity = float(
        properties.get(
            "gsl_data_rate_megabit_per_s",
            run["gsl_data_rate_megabit_per_s"],
        )
    )
    isl_queue_capacity = int(
        float(properties.get("isl_max_queue_size_pkts", run["queue_size_pkt"]))
    )
    gsl_queue_capacity = int(
        float(properties.get("gsl_max_queue_size_pkts", run["queue_size_pkt"]))
    )
    traffic_stop_ns = int(run["traffic_stop_time_ns"])
    logs_dir = os.path.join(algorithm_dir, "logs_ns3")
    isl_queue = _queue_metrics(
        logs_dir, "ISL", isl_queue_capacity, traffic_stop_ns
    )
    gsl_queue = _queue_metrics(
        logs_dir, "GSL", gsl_queue_capacity, traffic_stop_ns
    )
    utilization = _isl_utilization_metrics(
        logs_dir,
        _target_corridor_edges(run_dir),
        traffic_stop_ns,
    )
    loss = _loss_metrics(run_dir, algorithm)

    p95_isl = utilization["p95"]
    target_max = utilization["target_max"]
    algorithm_label = congestion_label(
        p95_isl,
        utilization["links_over_100"],
    )
    gsl_loss = (
        loss["gsl_saturation_associated_loss"]
        + loss["exact_gsl_physical_loss"]
    )
    isl_loss = (
        loss["isl_saturation_associated_loss"]
        + loss["exact_isl_physical_loss"]
    )
    mixed_loss = loss["mixed_saturation_associated_loss"]
    gsl_bottleneck = (
        gsl_queue["samples_at_capacity"] > 0
        or gsl_queue["max_ratio"] >= 1.0 - 1e-9
        or gsl_loss > 0
    )
    isl_bottleneck = (
        utilization["max"] >= 0.60
        or isl_queue["samples_at_capacity"] > 0
        or isl_loss > 0
    )
    target_bottleneck = (
        math.isfinite(float(target_max)) and float(target_max) >= 0.60
    )
    lost_packets = int(float(summary.get("total_lost_packets", 0) or 0))
    notes = [
        "ISL percentiles use duration-weighted active directed-link samples during traffic generation.",
        "GSL utilization is a queue-occupancy proxy, not measured link throughput.",
        "Associated loss is time/path correlation, not physical-drop proof.",
        "The algorithm congestion label describes this algorithm only.",
    ]
    if not os.path.exists(os.path.join(logs_dir, "isl_utilization.csv")):
        notes.append("isl_utilization.csv missing")

    per_flow_rate = float(summary.get("per_flow_target_rate_mbps", math.nan))
    total_offered = float(summary.get("total_target_rate_mbps", math.nan))
    return {
        "run_folder": run["name"],
        "focus_src": run["src_node_id"],
        "focus_dst": run["dst_node_id"],
        "load_level": run["load_level"],
        "background_flow_count": run["background_flow_count"],
        "per_flow_rate_mbps": per_flow_rate,
        "total_offered_rate_mbps": total_offered,
        "isl_capacity_mbps": isl_capacity,
        "gsl_capacity_mbps": gsl_capacity,
        "duration_s": run["simulation_end_time_s"],
        "traffic_stop_s": run["traffic_stop_time_s"],
        "algorithm": algorithm,
        "aggregate_pdr": float(summary.get("aggregate_pdr", math.nan)),
        "focus_pdr": float(summary.get("focus_flow_pdr", math.nan)),
        "background_pdr": _weighted_pdr(background),
        "min_flow_pdr": float(summary.get("min_flow_pdr", math.nan)),
        "p5_flow_pdr": float(summary.get("p5_flow_pdr", math.nan)),
        "lost_packets": lost_packets,
        "max_isl_queue": isl_queue["max_queue"],
        "max_gsl_queue": gsl_queue["max_queue"],
        "isl_samples_at_capacity": isl_queue["samples_at_capacity"],
        "gsl_samples_at_capacity": gsl_queue["samples_at_capacity"],
        "p50_isl_utilization": utilization["p50"],
        "p90_isl_utilization": utilization["p90"],
        "p95_isl_utilization": p95_isl,
        "max_isl_utilization": utilization["max"],
        "p95_gsl_utilization": gsl_queue["p95_ratio"],
        "max_gsl_utilization": gsl_queue["max_ratio"],
        "links_over_60pct": utilization["links_over_60"],
        "links_over_80pct": utilization["links_over_80"],
        "links_over_90pct": utilization["links_over_90"],
        "links_over_100pct": utilization["links_over_100"],
        "target_corridor_utilization_p95": utilization["target_p95"],
        "target_corridor_utilization_max": target_max,
        "gsl_bottleneck_flag": _bool_text(gsl_bottleneck),
        "isl_bottleneck_flag": _bool_text(isl_bottleneck),
        "target_corridor_bottleneck_flag": _bool_text(target_bottleneck),
        "dominant_loss_attribution": loss["dominant"],
        "algorithm_congestion_label": algorithm_label,
        "scenario_reference_algorithm": QUEUE_AWARE,
        "scenario_reference_available": "false",
        "scenario_congestion_label": "Unknown",
        "reference_p95_isl_utilization": math.nan,
        "reference_max_isl_utilization": math.nan,
        "reference_target_corridor_utilization_p95": math.nan,
        "reference_target_corridor_utilization_max": math.nan,
        "reference_links_over_80pct": 0,
        "reference_links_over_90pct": 0,
        "reference_links_over_100pct": 0,
        "reference_aggregate_pdr": math.nan,
        "reference_gsl_bottleneck_flag": "unknown",
        "baseline_congestion_label": "Unknown",
        "baseline_aggregate_pdr": math.nan,
        "baseline_improvement_space_flag": "false",
        "recommended_congestion_label": "Unknown",
        "recommended_for_formal": "false",
        "safe_for_isl_focused_experiment": "false",
        "isl_utilization_source": utilization["source"],
        "gsl_utilization_source": (
            "queue_occupancy_proxy"
            if os.path.exists(_queue_path(logs_dir, "GSL"))
            else "unknown"
        ),
        "notes": " ".join(notes),
    }


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) else math.nan


def _apply_scenario_reference(rows):
    enriched = [dict(row) for row in rows]
    rows_by_run = {}
    for row in enriched:
        rows_by_run.setdefault(row["run_folder"], []).append(row)

    for run_rows in rows_by_run.values():
        reference = next(
            (
                row
                for row in run_rows
                if row["algorithm"] == QUEUE_AWARE
            ),
            None,
        )
        baseline = next(
            (
                row
                for row in run_rows
                if row["algorithm"] == BASELINE
            ),
            None,
        )
        reference_available = reference is not None
        if reference_available:
            scenario_label = reference["algorithm_congestion_label"]
            reference_p95 = _finite_number(
                reference["p95_isl_utilization"]
            )
            reference_max = _finite_number(
                reference["max_isl_utilization"]
            )
            reference_target_p95 = _finite_number(
                reference["target_corridor_utilization_p95"]
            )
            reference_target_max = _finite_number(
                reference["target_corridor_utilization_max"]
            )
            reference_pdr = _finite_number(reference["aggregate_pdr"])
            reference_gsl_flag = reference["gsl_bottleneck_flag"]
            target_corridor_active = (
                math.isfinite(reference_target_max)
                and reference_target_max > 0
            )
        else:
            scenario_label = "Unknown"
            reference_p95 = math.nan
            reference_max = math.nan
            reference_target_p95 = math.nan
            reference_target_max = math.nan
            reference_pdr = math.nan
            reference_gsl_flag = "unknown"
            target_corridor_active = False

        baseline_label = (
            baseline["algorithm_congestion_label"]
            if baseline is not None
            else "Unknown"
        )
        baseline_pdr = (
            _finite_number(baseline["aggregate_pdr"])
            if baseline is not None
            else math.nan
        )
        baseline_improvement_space = False
        if reference_available and baseline is not None:
            baseline_p95 = _finite_number(
                baseline["p95_isl_utilization"]
            )
            pdr_gap = (
                reference_pdr - baseline_pdr
                if math.isfinite(reference_pdr)
                and math.isfinite(baseline_pdr)
                else 0.0
            )
            utilization_gap = (
                baseline_p95 - reference_p95
                if math.isfinite(baseline_p95)
                and math.isfinite(reference_p95)
                else 0.0
            )
            baseline_improvement_space = (
                int(baseline["lost_packets"]) > 0
                or pdr_gap >= 0.01
                or utilization_gap >= 0.10
            )

        no_gsl_contamination = all(
            row["gsl_bottleneck_flag"] != "true"
            for row in run_rows
        )
        no_dominant_mixed_loss = all(
            row["dominant_loss_attribution"]
            != "mixed_saturation_associated_loss"
            for row in run_rows
        )
        scenario_safe = (
            reference_available
            and reference["isl_utilization_source"] == "measured_throughput"
            and target_corridor_active
            and no_gsl_contamination
            and no_dominant_mixed_loss
        )
        recommended = (
            scenario_safe
            and baseline_improvement_space
            and scenario_label != "Unknown"
        )

        for row in run_rows:
            row.update(
                {
                    "scenario_reference_algorithm": QUEUE_AWARE,
                    "scenario_reference_available": _bool_text(
                        reference_available
                    ),
                    "scenario_congestion_label": scenario_label,
                    "reference_p95_isl_utilization": reference_p95,
                    "reference_max_isl_utilization": reference_max,
                    "reference_target_corridor_utilization_p95": (
                        reference_target_p95
                    ),
                    "reference_target_corridor_utilization_max": (
                        reference_target_max
                    ),
                    "reference_links_over_80pct": (
                        int(reference["links_over_80pct"])
                        if reference_available
                        else 0
                    ),
                    "reference_links_over_90pct": (
                        int(reference["links_over_90pct"])
                        if reference_available
                        else 0
                    ),
                    "reference_links_over_100pct": (
                        int(reference["links_over_100pct"])
                        if reference_available
                        else 0
                    ),
                    "reference_aggregate_pdr": reference_pdr,
                    "reference_gsl_bottleneck_flag": reference_gsl_flag,
                    "baseline_congestion_label": baseline_label,
                    "baseline_aggregate_pdr": baseline_pdr,
                    "baseline_improvement_space_flag": _bool_text(
                        baseline_improvement_space
                    ),
                    # Backward-compatible field, now explicitly scenario-scoped.
                    "recommended_congestion_label": scenario_label,
                    "recommended_for_formal": _bool_text(recommended),
                    "safe_for_isl_focused_experiment": _bool_text(
                        scenario_safe
                    ),
                }
            )
            row["notes"] = (
                row["notes"]
                + " Scenario congestion is defined by the queue-aware "
                "reference; baseline and other algorithm labels are observed "
                "outcomes, not scenario labels."
            )
    return enriched


def _scenario_summary_rows(rows):
    summaries = []
    rows_by_run = {}
    for row in rows:
        rows_by_run.setdefault(row["run_folder"], []).append(row)
    for run_rows in rows_by_run.values():
        reference = next(
            (
                row
                for row in run_rows
                if row["algorithm"] == QUEUE_AWARE
            ),
            run_rows[0],
        )
        summaries.append(
            {
                column: reference.get(column, "")
                for column in SCENARIO_COLUMNS
            }
        )
    return summaries


def _bottleneck_rows(rows):
    output = []
    for row in rows:
        reasons = []
        if row["gsl_bottleneck_flag"] == "true":
            reasons.append("this algorithm has GSL queue/loss evidence")
        if row["dominant_loss_attribution"] == "mixed_saturation_associated_loss":
            reasons.append("this algorithm has dominant mixed associated loss")
        reasons.append(
            "algorithm outcome=%s; queue-aware-reference scenario=%s"
            % (
                row["algorithm_congestion_label"],
                row["scenario_congestion_label"],
            )
        )
        if row["safe_for_isl_focused_experiment"] == "true":
            reasons.append(
                "scenario has measured target-corridor activity without "
                "GSL contamination"
            )
        else:
            reasons.append(
                "scenario reference/safety requirements are not satisfied"
            )
        output.append(
            {
                **{column: row[column] for column in BOTTLENECK_COLUMNS[:-1]},
                "reason": "; ".join(reasons),
            }
        )
    return output


def _recommendations(rows):
    frame = pd.DataFrame(_scenario_summary_rows(rows))
    columns = [
        "scenario_label",
        "reference_algorithm",
        "load_level",
        "background_flow_count",
        "isl_capacity_mbps",
        "gsl_capacity_mbps",
        "p95_isl_utilization",
        "max_isl_utilization",
        "target_corridor_utilization_p95",
        "target_corridor_utilization_max",
        "baseline_pdr",
        "baseline_congestion_label",
        "queue_aware_pdr",
        "queue_aware_congestion_label",
        "gsl_bottleneck_flag",
        "baseline_improvement_space_flag",
        "safe_for_isl_focused_experiment",
        "recommended_duration",
        "recommended_algorithms",
        "reason",
    ]
    if len(frame) == 0:
        return pd.DataFrame(columns=columns)
    midpoints = {
        "Light": 0.35,
        "Moderate": 0.60,
        "High": 0.775,
        "Severe": 0.925,
        "Overload": 1.00,
    }
    recommendations = []
    for label in ["Light", "Moderate", "High", "Severe", "Overload"]:
        candidates = frame[
            frame["scenario_congestion_label"] == label
        ].copy()
        candidates = candidates[
            candidates["safe_for_isl_focused_experiment"] == "true"
        ]
        candidates = candidates[
            candidates["recommended_for_formal"] == "true"
        ]
        if len(candidates):
            candidates["distance"] = (
                candidates["reference_p95_isl_utilization"] - midpoints[label]
            ).abs()
            candidates = candidates.sort_values(
                [
                    "reference_gsl_bottleneck_flag",
                    "distance",
                    "background_flow_count",
                ]
            )
            row = candidates.iloc[0]
            recommendations.append(
                {
                    "scenario_label": label,
                    "reference_algorithm": row[
                        "scenario_reference_algorithm"
                    ],
                    "load_level": row["load_level"],
                    "background_flow_count": row["background_flow_count"],
                    "isl_capacity_mbps": row["isl_capacity_mbps"],
                    "gsl_capacity_mbps": row["gsl_capacity_mbps"],
                    "p95_isl_utilization": row[
                        "reference_p95_isl_utilization"
                    ],
                    "max_isl_utilization": row[
                        "reference_max_isl_utilization"
                    ],
                    "target_corridor_utilization_p95": row[
                        "reference_target_corridor_utilization_p95"
                    ],
                    "target_corridor_utilization_max": row[
                        "reference_target_corridor_utilization_max"
                    ],
                    "baseline_pdr": row["baseline_aggregate_pdr"],
                    "baseline_congestion_label": row[
                        "baseline_congestion_label"
                    ],
                    "queue_aware_pdr": row["reference_aggregate_pdr"],
                    "queue_aware_congestion_label": row[
                        "scenario_congestion_label"
                    ],
                    "gsl_bottleneck_flag": row[
                        "reference_gsl_bottleneck_flag"
                    ],
                    "baseline_improvement_space_flag": row[
                        "baseline_improvement_space_flag"
                    ],
                    "safe_for_isl_focused_experiment": row[
                        "safe_for_isl_focused_experiment"
                    ],
                    "recommended_duration": "60s",
                    "recommended_algorithms": (
                        "algorithm_free_one_only_over_isls;"
                        "algorithm_queue_aware_over_isls;"
                        "algorithm_lohi;algorithm_lhtr"
                    ),
                    "reason": (
                        "Queue-aware reference is closest to the %s band; "
                        "baseline outcome=%s and improvement_space=%s."
                        % (
                            label,
                            row["baseline_congestion_label"],
                            row["baseline_improvement_space_flag"],
                        )
                    ),
                }
            )
        else:
            recommendations.append(
                {
                    "scenario_label": label,
                    "reference_algorithm": QUEUE_AWARE,
                    "load_level": "",
                    "background_flow_count": "",
                    "isl_capacity_mbps": "",
                    "gsl_capacity_mbps": "",
                    "p95_isl_utilization": "",
                    "max_isl_utilization": "",
                    "target_corridor_utilization_p95": "",
                    "target_corridor_utilization_max": "",
                    "baseline_pdr": "",
                    "baseline_congestion_label": "",
                    "queue_aware_pdr": "",
                    "queue_aware_congestion_label": "",
                    "gsl_bottleneck_flag": "",
                    "baseline_improvement_space_flag": "",
                    "safe_for_isl_focused_experiment": "",
                    "recommended_duration": "",
                    "recommended_algorithms": "",
                    "reason": (
                        "No formal-ready Queue-aware-reference setting reached "
                        "this band; complete Baseline improvement-space "
                        "validation or extend the sweep."
                    ),
                }
            )
    return pd.DataFrame(recommendations, columns=columns)


def _plot_outputs(frame, output_dir):
    if len(frame) == 0:
        return
    os.makedirs(output_dir, exist_ok=True)
    markers = ["o", "s", "^", "D", "x"]
    for metric, ylabel, filename in [
        (
            "aggregate_pdr",
            "Aggregate PDR",
            "isl_utilization_vs_pdr.png",
        )
    ]:
        plt.figure(figsize=(8, 5))
        for index, (algorithm, group) in enumerate(frame.groupby("algorithm")):
            plt.scatter(
                group["p95_isl_utilization"],
                group[metric],
                label=algorithm,
                marker=markers[index % len(markers)],
                s=55,
            )
        plt.xlabel("Measured p95 active-ISL utilization")
        plt.ylabel(ylabel)
        plt.ylim(0, 1.02)
        plt.grid(True, alpha=0.25)
        plt.legend(fontsize=8)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, filename), dpi=180)
        plt.close()

    plt.figure(figsize=(8, 5))
    for index, (algorithm, group) in enumerate(frame.groupby("algorithm")):
        plt.scatter(
            group["p95_isl_utilization"],
            group["max_gsl_utilization"],
            label=algorithm,
            marker=markers[index % len(markers)],
            s=55,
        )
    plt.axhline(1.0, color="tab:red", linestyle="--", linewidth=1)
    plt.xlabel("Measured p95 active-ISL utilization")
    plt.ylabel("Max GSL queue occupancy ratio (proxy)")
    plt.grid(True, alpha=0.25)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "gsl_vs_isl_saturation.png"), dpi=180)
    plt.close()

    label_order = ["Light", "Moderate", "High", "Severe", "Overload"]
    scenario_frame = frame.drop_duplicates("run_folder")
    counts = (
        scenario_frame["scenario_congestion_label"]
        .value_counts()
        .reindex(label_order)
        .fillna(0)
    )
    counts.plot(kind="bar", figsize=(9, 5))
    plt.xlabel("Queue-aware-reference scenario congestion label")
    plt.ylabel("Unique traffic setting count")
    plt.xticks(rotation=0)
    plt.grid(True, axis="y", alpha=0.25)
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, "congestion_level_summary.png"), dpi=180
    )
    plt.close()

    algorithm_counts = (
        frame.groupby(["algorithm_congestion_label", "algorithm"])
        .size()
        .unstack(fill_value=0)
        .reindex(label_order)
        .fillna(0)
    )
    algorithm_counts.plot(kind="bar", figsize=(10, 5))
    plt.xlabel("Observed algorithm congestion label")
    plt.ylabel("Algorithm-run count")
    plt.xticks(rotation=0)
    plt.grid(True, axis="y", alpha=0.25)
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, "algorithm_congestion_outcomes.png"),
        dpi=180,
    )
    plt.close()


def _write_outputs(rows, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    rows = _apply_scenario_reference(rows)
    frame = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    frame.to_csv(
        os.path.join(output_dir, "isl_focused_calibration_summary.csv"),
        index=False,
    )
    frame.sort_values(
        ["algorithm", "load_level", "background_flow_count"]
    ).to_csv(
        os.path.join(output_dir, "isl_focused_calibration_by_algorithm.csv"),
        index=False,
    )
    pd.DataFrame(
        _scenario_summary_rows(rows),
        columns=SCENARIO_COLUMNS,
    ).to_csv(
        os.path.join(output_dir, "isl_focused_scenario_summary.csv"),
        index=False,
    )
    pd.DataFrame(
        _bottleneck_rows(rows), columns=BOTTLENECK_COLUMNS
    ).to_csv(
        os.path.join(output_dir, "isl_gsl_bottleneck_check.csv"),
        index=False,
    )
    pd.DataFrame(MAPPING_ROWS).to_csv(
        os.path.join(output_dir, "congestion_level_mapping.csv"),
        index=False,
    )
    _recommendations(rows).to_csv(
        os.path.join(output_dir, "formal_scenario_recommendations.csv"),
        index=False,
    )
    _plot_outputs(frame, output_dir)


def main():
    parser = build_arg_parser(
        "Analyze ISL-focused UDP/PDR congestion calibration results."
    )
    args = parser.parse_args()
    validate_focus_pair_arguments(parser, args)
    selected_mode, _, load_levels, algorithms = describe_selection(args)
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
        args.isl_data_rate_megabit_per_s,
        args.gsl_data_rate_megabit_per_s,
        args.backpressure_queue_source,
        args.backpressure_fallback,
        args.backpressure_diagnostics,
        args.backpressure_diagnostics_sample_limit,
    )

    rows = []
    seen = set()
    for requested_run in runs:
        run = resolve_existing_run(requested_run, RUNS_ROOT)
        key = (run["name"], run["dynamic_state_algorithm"])
        if key in seen:
            continue
        seen.add(key)
        algorithm_dir = os.path.join(
            RUNS_ROOT, run["name"], run["dynamic_state_algorithm"]
        )
        summary_path = _comparison_path(
            os.path.join(RUNS_ROOT, run["name"]),
            "summary_by_algorithm.csv",
        )
        if not os.path.isdir(algorithm_dir) or not os.path.exists(summary_path):
            print("Skipping incomplete calibration run: %s" % algorithm_dir)
            continue
        row = _build_row(run, run["dynamic_state_algorithm"])
        rows.append(row)

    if not rows:
        print("No completed calibration results found.")
        return

    rows_by_run = {}
    for row in rows:
        rows_by_run.setdefault(row["run_folder"], []).append(row)
    for run_name, run_rows in rows_by_run.items():
        output_dir = os.path.join(
            RUNS_ROOT,
            run_name,
            "comparison_packet_delivery",
            "calibration",
        )
        _write_outputs(run_rows, output_dir)
        print("Wrote per-run calibration outputs under %s" % output_dir)

    first = rows[0]
    aggregate_tag = "%s_%s_%gs" % (
        "src%d_dst%d" % (first["focus_src"], first["focus_dst"]),
        capacity_identity_tag(
            first["isl_capacity_mbps"], first["gsl_capacity_mbps"]
        ),
        float(first["duration_s"]),
    )
    aggregate_dir = os.path.join(
        RUNS_ROOT, "comparison_calibration", aggregate_tag
    )
    _write_outputs(rows, aggregate_dir)
    print("Wrote aggregate calibration outputs under %s" % aggregate_dir)


if __name__ == "__main__":
    main()
