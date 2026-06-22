#!/usr/bin/env python3

import argparse
import json
import math
import os
import re
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-udp-pdr")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
RUNS_DIR = SCRIPT_DIR / "runs"
DEFAULT_OUTPUT_DIR = (
    SCRIPT_DIR
    / "analysis_reports"
    / "lhtr_congested_window_sbr_ratio"
)

SCENARIO_ORDER = ["H40", "H60", "H80", "H90", "H100+"]
ALGORITHM_LABELS = {
    "algorithm_free_one_only_over_isls": "Baseline",
    "algorithm_queue_aware_over_isls": "Queue-aware",
    "algorithm_lohi": "LoHi",
    "algorithm_lhtr": "LHTR",
}
LABEL_TO_ALGORITHM = {
    "Baseline": "algorithm_free_one_only_over_isls",
    "Queue-aware": "algorithm_queue_aware_over_isls",
    "LoHi": "algorithm_lohi",
    "LHTR": "algorithm_lhtr",
}

SUMMARY_COLUMNS = [
    "result_scope",
    "scenario_id",
    "scenario_duration_id",
    "hotspot_label",
    "duration_s",
    "traffic_stop_s",
    "load_level",
    "background_flow_count",
    "hotspot_reference_load_percent",
    "global_offered_isl_load_percent",
    "run_folder",
    "window_size_s",
    "top_fraction",
    "total_window_count",
    "top_window_count",
    "top_window_time_ranges",
    "global_br_selected",
    "global_sbr_selected",
    "global_fallback",
    "global_no_route",
    "global_sbr_ratio",
    "global_sbr_ratio_no_fallback",
    "top25_br_selected",
    "top25_sbr_selected",
    "top25_fallback",
    "top25_no_route",
    "top25_sbr_ratio",
    "top25_sbr_ratio_no_fallback",
    "sbr_decision_share_in_top25",
    "yellow_count_total",
    "red_count_total",
    "yellow_plus_red_count_total",
    "traffic_light_link_samples_total",
    "yellow_count_top25",
    "red_count_top25",
    "yellow_plus_red_count_top25",
    "traffic_light_link_samples_top25",
    "congestion_score_total",
    "congestion_score_top25",
    "congestion_score_share_in_top25",
    "red_count_share_in_top25",
    "yellow_plus_red_share_in_top25",
    "top25_overlap_with_yellow_plus_red_rule",
    "top25_overlap_with_red_only_rule",
    "legacy_100ms_decision_colored_threshold",
    "legacy_100ms_decision_colored_top25_window_count",
    "legacy_100ms_decision_colored_top25_sbr_share",
    "lhtr_vs_lohi_pdr_gain",
    "queue_aware_vs_lhtr_gap",
    "aggregate_pdr_lhtr",
    "aggregate_pdr_lohi",
    "aggregate_pdr_queue_aware",
    "mean_rtt_lhtr",
    "mean_rtt_lohi",
    "mean_rtt_queue_aware",
    "p95_rtt_lhtr",
    "p95_rtt_lohi",
    "p95_rtt_queue_aware",
]

DETAIL_COLUMNS = [
    "window_start_s",
    "window_end_s",
    "br_selected",
    "sbr_selected",
    "fallback",
    "sbr_ratio",
    "sbr_ratio_no_fallback",
    "yellow_count",
    "red_count",
    "yellow_plus_red_count",
    "traffic_light_link_samples",
    "congestion_score",
    "is_top25_congested_window",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Recompute LHTR SBR selection ratios inside the most congested "
            "traffic-light time windows."
        )
    )
    parser.add_argument(
        "--window-size-s",
        type=float,
        default=1.0,
        help="Aggregation window size in seconds. Default: 1.",
    )
    parser.add_argument(
        "--top-fraction",
        type=float,
        default=0.25,
        help="Fraction of windows selected by congestion score. Default: 0.25.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output analysis directory.",
    )
    args = parser.parse_args()
    if args.window_size_s <= 0:
        parser.error("--window-size-s must be positive")
    if not 0 < args.top_fraction <= 1:
        parser.error("--top-fraction must satisfy 0 < value <= 1")
    return args


def require_csv(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError("Required CSV is missing: %s" % path)
    return pd.read_csv(path)


def read_json(path):
    path = Path(path)
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def safe_ratio(numerator, denominator):
    denominator = float(denominator)
    return float(numerator) / denominator if denominator > 0 else 0.0


def numeric_column(frame, column):
    if column not in frame.columns:
        return pd.Series(0, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0)


def int_sum(frame, column):
    if column not in frame.columns:
        return 0
    return int(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def format_seconds(value):
    value = float(value)
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return ("%.3f" % value).rstrip("0").rstrip(".")


def format_pct(value, digits=3):
    return ("%.*f%%" % (digits, 100.0 * float(value)))


def format_pp(value, digits=2):
    return "%.*f pp" % (digits, 100.0 * float(value))


def resolve_run_dir(run_folder):
    run_path = Path(run_folder)
    if run_path.is_absolute():
        return run_path
    return SCRIPT_DIR / run_path


def diagnostics_dir(run_dir):
    primary = run_dir / "algorithm_lhtr" / "lhtr_diagnostics"
    if primary.is_dir():
        return primary
    fallback = run_dir / "comparison_packet_delivery" / "diagnostics"
    if fallback.is_dir():
        return fallback
    raise FileNotFoundError("No LHTR diagnostics directory under %s" % run_dir)


def manifest_rows():
    manifests = [
        (
            "5-level formal curve",
            RUNS_DIR / "hotspot_5level_60s_formal_manifest.csv",
        ),
        (
            "H80 long-duration validation",
            RUNS_DIR / "hotspot_5level_200s_formal_manifest.csv",
        ),
    ]
    rows = []
    for result_scope, path in manifests:
        if not path.is_file():
            continue
        frame = require_csv(path)
        if "status" in frame.columns:
            frame = frame[frame["status"].astype(str) == "complete"].copy()
        for _, row in frame.iterrows():
            rows.append(
                {
                    "result_scope": result_scope,
                    "scenario_id": str(row["scenario_id"]),
                    "hotspot_label": str(row.get("label", "")),
                    "load_level": float(row.get("load_level", 0.0)),
                    "background_flow_count": int(row.get("background_flow_count", 0)),
                    "hotspot_reference_load_percent": float(
                        row.get("hotspot_reference_load_percent", 0.0)
                    ),
                    "global_offered_isl_load_percent": float(
                        row.get("global_offered_isl_load_percent", 0.0)
                    ),
                    "run_folder": str(row["run_folder"]),
                    "manifest_duration_s": row.get("simulation_end_time_s", np.nan),
                    "manifest_traffic_stop_s": row.get("traffic_stop_time_s", np.nan),
                }
            )
    if not rows:
        raise RuntimeError("No complete hotspot formal manifest rows found")
    return rows


def duration_from_run_name(run_folder):
    match = re.search(r"_sim([0-9]+(?:p[0-9]+)?)s_stop([0-9]+(?:p[0-9]+)?)s", run_folder)
    if not match:
        return np.nan, np.nan
    sim_s = float(match.group(1).replace("p", "."))
    stop_s = float(match.group(2).replace("p", "."))
    return sim_s, stop_s


def run_timing(run_dir, row):
    metadata = read_json(run_dir / "algorithm_lhtr" / "run_metadata.json")
    formal = metadata.get("formal_experiment", {})
    duration_s = formal.get(
        "simulation_end_time_s",
        metadata.get("formal_duration_s", row.get("manifest_duration_s", np.nan)),
    )
    traffic_stop_s = formal.get(
        "traffic_stop_time_s",
        metadata.get("formal_traffic_stop_s", row.get("manifest_traffic_stop_s", np.nan)),
    )
    if pd.isna(duration_s) or pd.isna(traffic_stop_s):
        parsed_duration, parsed_stop = duration_from_run_name(row["run_folder"])
        if pd.isna(duration_s):
            duration_s = parsed_duration
        if pd.isna(traffic_stop_s):
            traffic_stop_s = parsed_stop
    return float(duration_s), float(traffic_stop_s)


def add_window_column(frame, window_size_s):
    result = frame.copy()
    result["time_ns"] = numeric_column(result, "time_ns")
    time_s = result["time_ns"] / 1e9
    result["window_start_s"] = np.floor(time_s / window_size_s) * window_size_s
    result["window_start_s"] = result["window_start_s"].round(9)
    return result


def aggregate_windows(br_sbr, colors, window_size_s):
    br_sbr = add_window_column(br_sbr, window_size_s)
    colors = add_window_column(colors, window_size_s)

    br_cols = [
        "br_selected_count",
        "sbr_selected_count",
        "fallback_count",
        "no_route_count",
    ]
    br_agg = (
        br_sbr.groupby("window_start_s", as_index=False)[br_cols]
        .sum()
        .rename(
            columns={
                "br_selected_count": "br_selected",
                "sbr_selected_count": "sbr_selected",
                "fallback_count": "fallback",
                "no_route_count": "no_route",
            }
        )
    )

    color_cols = ["yellow_count", "red_count", "total_colored_links"]
    for column in color_cols:
        if column not in colors.columns:
            colors[column] = 0
    color_agg = (
        colors.groupby("window_start_s", as_index=False)[color_cols]
        .sum()
        .rename(
            columns={
                "total_colored_links": "traffic_light_link_samples",
            }
        )
    )

    windows = pd.merge(br_agg, color_agg, on="window_start_s", how="outer")
    for column in [
        "br_selected",
        "sbr_selected",
        "fallback",
        "no_route",
        "yellow_count",
        "red_count",
        "traffic_light_link_samples",
    ]:
        windows[column] = numeric_column(windows, column)
    windows["window_end_s"] = windows["window_start_s"] + window_size_s
    windows["yellow_plus_red_count"] = (
        windows["yellow_count"] + windows["red_count"]
    )
    windows["congestion_score"] = (
        windows["yellow_count"] + 2.0 * windows["red_count"]
    )
    windows["sbr_ratio"] = windows.apply(
        lambda row: safe_ratio(
            row["sbr_selected"],
            row["br_selected"] + row["sbr_selected"] + row["fallback"],
        ),
        axis=1,
    )
    windows["sbr_ratio_no_fallback"] = windows.apply(
        lambda row: safe_ratio(
            row["sbr_selected"],
            row["br_selected"] + row["sbr_selected"],
        ),
        axis=1,
    )
    windows = windows.sort_values("window_start_s").reset_index(drop=True)
    count_columns = [
        "br_selected",
        "sbr_selected",
        "fallback",
        "no_route",
        "yellow_count",
        "red_count",
        "yellow_plus_red_count",
        "traffic_light_link_samples",
        "congestion_score",
    ]
    for column in count_columns:
        windows[column] = windows[column].round().astype(int)
    return windows


def top_window_indices(windows, score_column, top_count):
    ordered = windows.sort_values(
        [score_column, "red_count", "yellow_count", "window_start_s"],
        ascending=[False, False, False, True],
        kind="mergesort",
    )
    return set(ordered.head(top_count).index.tolist())


def legacy_100ms_decision_colored_metrics(br_sbr, top_fraction):
    score = numeric_column(br_sbr, "yellow_count") + numeric_column(
        br_sbr,
        "red_count",
    )
    if len(score) == 0:
        return {
            "legacy_100ms_decision_colored_threshold": 0,
            "legacy_100ms_decision_colored_top25_window_count": 0,
            "legacy_100ms_decision_colored_top25_sbr_share": 0.0,
        }
    threshold = float(score.quantile(1.0 - top_fraction, interpolation="lower"))
    selected = br_sbr[score >= threshold].copy()
    selected_sbr = int_sum(selected, "sbr_selected_count")
    total_sbr = int_sum(br_sbr, "sbr_selected_count")
    return {
        "legacy_100ms_decision_colored_threshold": threshold,
        "legacy_100ms_decision_colored_top25_window_count": int(len(selected)),
        "legacy_100ms_decision_colored_top25_sbr_share": safe_ratio(
            selected_sbr,
            total_sbr,
        ),
    }


def contiguous_ranges(windows, window_size_s):
    selected = windows[windows["is_top25_congested_window"]].copy()
    selected = selected.sort_values("window_start_s")
    ranges = []
    current_start = None
    current_end = None
    for _, row in selected.iterrows():
        start = float(row["window_start_s"])
        end = float(row["window_end_s"])
        if current_start is None:
            current_start = start
            current_end = end
        elif abs(start - current_end) <= max(1e-9, window_size_s * 1e-9):
            current_end = end
        else:
            ranges.append((current_start, current_end))
            current_start = start
            current_end = end
    if current_start is not None:
        ranges.append((current_start, current_end))
    return "; ".join(
        "%s-%ss" % (format_seconds(start), format_seconds(end))
        for start, end in ranges
    )


def performance_value(frame, algorithm, column, direction=None):
    selected = frame[frame["algorithm"] == algorithm]
    if direction is not None and "direction" in selected.columns:
        direction_rows = selected[selected["direction"] == direction]
        if len(direction_rows):
            selected = direction_rows
    if len(selected) == 0 or column not in selected.columns:
        return 0.0
    return float(pd.to_numeric(selected.iloc[0][column], errors="coerce"))


def performance_metrics(run_dir):
    core = run_dir / "comparison_packet_delivery" / "core"
    summary = require_csv(core / "summary_by_algorithm.csv")
    rtt = require_csv(core / "udp_rtt_summary_by_algorithm.csv")
    queue_alg = "algorithm_queue_aware_over_isls"
    lohi_alg = "algorithm_lohi"
    lhtr_alg = "algorithm_lhtr"
    result = {
        "aggregate_pdr_lhtr": performance_value(
            summary, lhtr_alg, "aggregate_pdr"
        ),
        "aggregate_pdr_lohi": performance_value(
            summary, lohi_alg, "aggregate_pdr"
        ),
        "aggregate_pdr_queue_aware": performance_value(
            summary, queue_alg, "aggregate_pdr"
        ),
        "mean_rtt_lhtr": performance_value(
            rtt, lhtr_alg, "mean_queue_aware_rtt_ms", "754_to_785"
        ),
        "mean_rtt_lohi": performance_value(
            rtt, lohi_alg, "mean_queue_aware_rtt_ms", "754_to_785"
        ),
        "mean_rtt_queue_aware": performance_value(
            rtt, queue_alg, "mean_queue_aware_rtt_ms", "754_to_785"
        ),
        "p95_rtt_lhtr": performance_value(
            rtt, lhtr_alg, "p95_queue_aware_rtt_ms", "754_to_785"
        ),
        "p95_rtt_lohi": performance_value(
            rtt, lohi_alg, "p95_queue_aware_rtt_ms", "754_to_785"
        ),
        "p95_rtt_queue_aware": performance_value(
            rtt, queue_alg, "p95_queue_aware_rtt_ms", "754_to_785"
        ),
    }
    result["lhtr_vs_lohi_pdr_gain"] = (
        result["aggregate_pdr_lhtr"] - result["aggregate_pdr_lohi"]
    )
    result["queue_aware_vs_lhtr_gap"] = (
        result["aggregate_pdr_queue_aware"] - result["aggregate_pdr_lhtr"]
    )
    return result


def summarize_run(row, window_size_s, top_fraction):
    run_dir = resolve_run_dir(row["run_folder"])
    diag_dir = diagnostics_dir(run_dir)
    br_sbr = require_csv(diag_dir / "lhtr_br_sbr_summary.csv")
    colors = require_csv(diag_dir / "lhtr_traffic_light_color_summary.csv")
    windows = aggregate_windows(br_sbr, colors, window_size_s)
    if len(windows) == 0:
        raise RuntimeError("No diagnostic windows for %s" % run_dir)

    top_count = max(1, int(math.ceil(len(windows) * top_fraction)))
    primary_top = top_window_indices(windows, "congestion_score", top_count)
    yellow_red_top = top_window_indices(
        windows, "yellow_plus_red_count", top_count
    )
    red_top = top_window_indices(windows, "red_count", top_count)
    windows["is_top25_congested_window"] = windows.index.isin(primary_top)

    top = windows[windows["is_top25_congested_window"]]
    duration_s, traffic_stop_s = run_timing(run_dir, row)
    scenario_duration_id = "%s_%ss" % (
        row["scenario_id"],
        format_seconds(duration_s),
    )
    global_br = int_sum(windows, "br_selected")
    global_sbr = int_sum(windows, "sbr_selected")
    global_fallback = int_sum(windows, "fallback")
    global_no_route = int_sum(windows, "no_route")
    top_br = int_sum(top, "br_selected")
    top_sbr = int_sum(top, "sbr_selected")
    top_fallback = int_sum(top, "fallback")
    top_no_route = int_sum(top, "no_route")
    score_total = int_sum(windows, "congestion_score")
    score_top = int_sum(top, "congestion_score")
    red_total = int_sum(windows, "red_count")
    red_top_count = int_sum(top, "red_count")
    yellow_red_total = int_sum(windows, "yellow_plus_red_count")
    yellow_red_top_count = int_sum(top, "yellow_plus_red_count")

    summary = {
        "result_scope": row["result_scope"],
        "scenario_id": row["scenario_id"],
        "scenario_duration_id": scenario_duration_id,
        "hotspot_label": row["hotspot_label"],
        "duration_s": duration_s,
        "traffic_stop_s": traffic_stop_s,
        "load_level": row["load_level"],
        "background_flow_count": row["background_flow_count"],
        "hotspot_reference_load_percent": row["hotspot_reference_load_percent"],
        "global_offered_isl_load_percent": row["global_offered_isl_load_percent"],
        "run_folder": row["run_folder"],
        "window_size_s": window_size_s,
        "top_fraction": top_fraction,
        "total_window_count": len(windows),
        "top_window_count": len(top),
        "top_window_time_ranges": contiguous_ranges(windows, window_size_s),
        "global_br_selected": global_br,
        "global_sbr_selected": global_sbr,
        "global_fallback": global_fallback,
        "global_no_route": global_no_route,
        "global_sbr_ratio": safe_ratio(
            global_sbr,
            global_br + global_sbr + global_fallback,
        ),
        "global_sbr_ratio_no_fallback": safe_ratio(
            global_sbr,
            global_br + global_sbr,
        ),
        "top25_br_selected": top_br,
        "top25_sbr_selected": top_sbr,
        "top25_fallback": top_fallback,
        "top25_no_route": top_no_route,
        "top25_sbr_ratio": safe_ratio(top_sbr, top_br + top_sbr + top_fallback),
        "top25_sbr_ratio_no_fallback": safe_ratio(top_sbr, top_br + top_sbr),
        "sbr_decision_share_in_top25": safe_ratio(top_sbr, global_sbr),
        "yellow_count_total": int_sum(windows, "yellow_count"),
        "red_count_total": red_total,
        "yellow_plus_red_count_total": yellow_red_total,
        "traffic_light_link_samples_total": int_sum(
            windows,
            "traffic_light_link_samples",
        ),
        "yellow_count_top25": int_sum(top, "yellow_count"),
        "red_count_top25": red_top_count,
        "yellow_plus_red_count_top25": yellow_red_top_count,
        "traffic_light_link_samples_top25": int_sum(
            top,
            "traffic_light_link_samples",
        ),
        "congestion_score_total": score_total,
        "congestion_score_top25": score_top,
        "congestion_score_share_in_top25": safe_ratio(score_top, score_total),
        "red_count_share_in_top25": safe_ratio(red_top_count, red_total),
        "yellow_plus_red_share_in_top25": safe_ratio(
            yellow_red_top_count,
            yellow_red_total,
        ),
        "top25_overlap_with_yellow_plus_red_rule": safe_ratio(
            len(primary_top & yellow_red_top),
            len(primary_top),
        ),
        "top25_overlap_with_red_only_rule": safe_ratio(
            len(primary_top & red_top),
            len(primary_top),
        ),
    }
    summary.update(legacy_100ms_decision_colored_metrics(br_sbr, top_fraction))
    summary.update(performance_metrics(run_dir))
    return summary, windows


def ordered_60s_summary(summary):
    frame = summary[summary["duration_s"].round(9) == 60.0].copy()
    frame["scenario_id"] = pd.Categorical(
        frame["scenario_id"],
        categories=SCENARIO_ORDER,
        ordered=True,
    )
    return frame.sort_values("scenario_id")


def h80_200s_row(summary):
    selected = summary[
        (summary["scenario_id"].astype(str) == "H80")
        & (summary["duration_s"].round(9) == 200.0)
    ]
    if len(selected) == 0:
        raise RuntimeError("H80 200s summary row is missing")
    return selected.iloc[0]


def plot_cross_level(summary, output_path):
    frame = ordered_60s_summary(summary)
    x = np.arange(len(frame))
    global_pct = 100.0 * frame["global_sbr_ratio_no_fallback"].astype(float)
    top_pct = 100.0 * frame["top25_sbr_ratio_no_fallback"].astype(float)
    labels = frame["scenario_id"].astype(str).tolist()

    fig, ax = plt.subplots(figsize=(8.4, 4.9))
    ax.plot(
        x,
        global_pct,
        marker="o",
        linewidth=2.2,
        color="#4D4D4D",
        label="Global SBR ratio",
    )
    ax.plot(
        x,
        top_pct,
        marker="s",
        linewidth=2.2,
        color="#0072B2",
        label="Top-25% congested-window SBR ratio",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_xlabel("Hotspot congestion level")
    ax.set_ylabel("SBR selection ratio (%)")
    ax.set_title("LHTR SBR Selection Ratio in Most Congested 25% Windows")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper left")
    ax.text(
        0.99,
        0.03,
        "Top windows: Traffic-light score = Yellow + 2 x Red",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color="#333333",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.85},
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_h80_200s_bar(row, output_path):
    labels = [
        "Global\nSBR ratio",
        "Top-25%\nSBR ratio",
        "SBR share in\nTop-25%",
    ]
    values = [
        100.0 * float(row["global_sbr_ratio_no_fallback"]),
        100.0 * float(row["top25_sbr_ratio_no_fallback"]),
        100.0 * float(row["sbr_decision_share_in_top25"]),
    ]
    colors = ["#4D4D4D", "#0072B2", "#D55E00"]
    fig, ax = plt.subplots(figsize=(7.1, 4.8))
    bars = ax.bar(labels, values, color=colors, width=0.62)
    ax.set_ylabel("Percent (%)")
    ax.set_title("H80 200s: SBR Is Concentrated in Congested Windows")
    ax.grid(True, axis="y", alpha=0.3)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height(),
            "%.3f%%" % value,
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.text(
        0.5,
        -0.18,
        "Top windows selected by traffic-light score = Yellow + 2 x Red",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=9,
        color="#333333",
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_h80_timeseries(windows, output_path):
    frame = windows.sort_values("window_start_s").copy()
    x = (frame["window_start_s"] + frame["window_end_s"]) / 2.0
    fig, ax = plt.subplots(figsize=(10.8, 4.9))
    shaded_label_added = False
    for _, row in frame[frame["is_top25_congested_window"]].iterrows():
        ax.axvspan(
            row["window_start_s"],
            row["window_end_s"],
            color="#CFE8F3",
            alpha=0.42,
            linewidth=0,
            label="Top-25% congested window" if not shaded_label_added else None,
        )
        shaded_label_added = True
    line1 = ax.plot(
        x,
        frame["congestion_score"],
        color="#0072B2",
        linewidth=1.8,
        label="Congestion score",
    )
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Traffic-light congestion score")
    ax.grid(True, axis="y", alpha=0.3)
    ax2 = ax.twinx()
    line2 = ax2.plot(
        x,
        frame["sbr_selected"],
        color="#D55E00",
        linewidth=1.5,
        label="SBR selected count",
    )
    ax2.set_ylabel("SBR selected count")
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(handles + handles2, labels + labels2, loc="upper right")
    ax.set_title("H80 200s: Traffic-Light Signal and SBR Decisions Over Time")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def markdown_metric_table(rows, columns):
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(str(row[col]) for col in columns) + " |" for row in rows]
    return "\n".join([header, separator] + body)


def report_text(summary, h80_windows):
    row = h80_200s_row(summary)
    curve = ordered_60s_summary(summary)
    closest_idx = (
        summary["sbr_decision_share_in_top25"].astype(float) - 0.509
    ).abs().idxmin()
    closest = summary.loc[closest_idx]
    legacy_share = float(row["legacy_100ms_decision_colored_top25_sbr_share"])
    legacy_count = int(row["legacy_100ms_decision_colored_top25_window_count"])
    legacy_threshold = float(row["legacy_100ms_decision_colored_threshold"])
    if abs(legacy_share - 0.509) <= 0.005:
        share_note = (
            "50.9%% 來自既有 `thesis_readiness_after_h80_200s` 報告："
            "H80 200s 以 0.1s diagnostics rows、decision-summary "
            "colored count (`yellow_count + red_count`) 的 top quartile "
            "threshold >= %.0f 選窗；因 tie 包含 %d/2000 rows，"
            "SBR share=%s。"
            % (legacy_threshold, legacy_count, format_pct(legacy_share, 1))
        )
    else:
        share_note = (
            "本次沒有在 formal diagnostics 中重現 50.9%；最接近 50.9% 的 "
            "1s primary-rule run 是 %s %ss，share=%s。"
            % (
                closest["scenario_id"],
                format_seconds(closest["duration_s"]),
                format_pct(closest["sbr_decision_share_in_top25"], 1),
            )
        )

    curve_rows = []
    for _, item in curve.iterrows():
        curve_rows.append(
            {
                "scenario": item["scenario_id"],
                "global": format_pct(item["global_sbr_ratio_no_fallback"], 4),
                "top25": format_pct(item["top25_sbr_ratio_no_fallback"], 4),
                "share": format_pct(item["sbr_decision_share_in_top25"], 1),
            }
        )

    top_windows = h80_windows[h80_windows["is_top25_congested_window"]]
    top_sbr_windows = int((top_windows["sbr_selected"] > 0).sum())
    total_top_windows = int(len(top_windows))

    return """# LHTR Congested-Window SBR Ratio Analysis

## 核心結論

原本的 global SBR ratio 會把整個網路中所有 routing decisions 放進分母，其中大多數發生在 green 或非擁塞 context，所以比例會被大量非擁塞決策稀釋。本分析改用固定規則：先以 1 秒 time window 聚合 LHTR traffic-light diagnostics，再用 `Yellow + 2 x Red` 選出每個 scenario 最擁塞的前 25% windows，最後只在這些 windows 內計算 SBR selection ratio。

H80 200s 的 global SBR ratio 是 {global_ratio}，top-25% congested-window SBR ratio 是 {top_ratio}；最擁塞的 {top_count}/{total_count} 個 windows 承載 {share} 的 SBR decisions。這表示 H80 200s 不是「沒有觸發 SBR」，而是全網平均分母稀釋；SBR 決策集中在 congestion-critical windows。

## 5-Level 60s 對照

{curve_table}

主圖位於 `figures/lhtr_top25_congested_window_sbr_ratio.png`。圖中保留 global ratio 作 baseline，並用相同 top-25% rule 比較每個 hotspot level。

## H80 200s 重點

- `global_sbr_ratio_no_fallback`: {global_ratio}
- `top25_congested_window_sbr_ratio_no_fallback`: {top_ratio}
- `sbr_decision_share_in_top25`: {share}
- `top25_window_time_ranges`: {ranges}
- top-25% windows 中有 SBR 的 window 數量：{top_sbr_windows}/{top_count}
- LHTR vs LoHi aggregate PDR gain: {pdr_gain}
- Queue-aware vs LHTR remaining PDR gap: {queue_gap}
- Mean RTT: LHTR={mean_rtt_lhtr:.1f} ms, LoHi={mean_rtt_lohi:.1f} ms, Queue-aware={mean_rtt_queue:.1f} ms

關於「top 25% most congested windows carry 50.9% of SBR decisions」：{share_note} 這個值和本任務主規格不同；本任務主規格改成 1s windows、traffic-light link samples、`Yellow + 2 x Red` score，因此 H80 200s 的 primary share 是 {share}。本報告的 `tables/lhtr_congested_window_sbr_ratio_summary.csv` 會列出所有 scenario/duration 的實際值，H80 200s detailed windows 則在 `tables/h80_200s_congested_windows.csv`。

## 為什麼原圖 ratio 這麼低？

原本 global SBR ratio 的分母包含整個網路中所有 routing decisions，其中大多數發生在非擁塞區域或 green 狀態。因此，雖然 SBR 在局部壅塞時有觸發，但在全網統計下會被大量非擁塞決策稀釋。

## 新圖如何修正？

新圖只針對 traffic-light signal 最強的前 25% 時窗計算 SBR ratio。這些時窗代表 LHTR 實際偵測到 congestion 的主要區段，因此更能反映 SBR decision 是否在需要時被啟用。Top window 的 congestion score 只使用 `lhtr_traffic_light_color_summary.csv` 中的 yellow/red link samples；BR/SBR/fallback counts 則來自 `lhtr_br_sbr_summary.csv`。

## 如何避免 cherry-picking？

1. top 25% rule 是固定比例，不是人工挑時間點。
2. congestion score 只使用 yellow/red traffic-light signal，不使用 PDR。
3. 所有 scenarios 使用相同 rule：`Yellow + 2 x Red`，排序 tie-breaker 為 score desc, red desc, yellow desc, time asc。
4. 同時保留 global ratio 作 baseline comparison。
5. 輸出所有 H80 200s windows 的 CSV，包含是否被選入 top 25%，可重現。

## 如何解釋 LHTR 效能改善？

LHTR 的改善不需要來自大量全網 SBR switching，而是來自於在少數關鍵擁塞時窗與 bottleneck corridor 中，將部分 traffic 從主要 BR path 切換到替代 SBR path。由於 hotspot loss 往往由少數關鍵 links 或 time windows 主導，即使全域 SBR ratio 很低，若 SBR decision 集中在 congestion-critical windows，仍可能帶來明顯 PDR / RTT 改善。

H80 200s 中，LHTR aggregate PDR={lhtr_pdr:.4f}，LoHi={lohi_pdr:.4f}，Queue-aware={queue_pdr:.4f}；LHTR 比 LoHi 高 {pdr_gain}，但仍距 Queue-aware {queue_gap}。RTT 上 LHTR mean RTT={mean_rtt_lhtr:.1f} ms，低於 LoHi 的 {mean_rtt_lohi:.1f} ms，但高於 Queue-aware 的 {mean_rtt_queue:.1f} ms。

## Sensitivity

Primary top-25% rule 與 `Yellow + Red` top-25% 的 overlap 為 {overlap_yellow_red}，與 `Red only` top-25% 的 overlap 為 {overlap_red_only}。若後續要更細緻區分 bottleneck corridor，可把 focus-flow/corridor-only SBR ratio 作為 diagnostics-only future work；目前資料已足夠支持 time-window concentration 的重畫圖。
""".format(
        global_ratio=format_pct(row["global_sbr_ratio_no_fallback"], 4),
        top_ratio=format_pct(row["top25_sbr_ratio_no_fallback"], 4),
        share=format_pct(row["sbr_decision_share_in_top25"], 1),
        top_count=int(row["top_window_count"]),
        total_count=int(row["total_window_count"]),
        curve_table=markdown_metric_table(
            curve_rows,
            ["scenario", "global", "top25", "share"],
        ),
        ranges=row["top_window_time_ranges"],
        top_sbr_windows=top_sbr_windows,
        pdr_gain=format_pp(row["lhtr_vs_lohi_pdr_gain"]),
        queue_gap=format_pp(row["queue_aware_vs_lhtr_gap"]),
        mean_rtt_lhtr=float(row["mean_rtt_lhtr"]),
        mean_rtt_lohi=float(row["mean_rtt_lohi"]),
        mean_rtt_queue=float(row["mean_rtt_queue_aware"]),
        share_note=share_note,
        legacy_threshold=legacy_threshold,
        lhtr_pdr=float(row["aggregate_pdr_lhtr"]),
        lohi_pdr=float(row["aggregate_pdr_lohi"]),
        queue_pdr=float(row["aggregate_pdr_queue_aware"]),
        overlap_yellow_red=format_pct(
            row["top25_overlap_with_yellow_plus_red_rule"],
            1,
        ),
        overlap_red_only=format_pct(row["top25_overlap_with_red_only_rule"], 1),
    )


def write_outputs(summary, detail_by_key, output_dir):
    figures_dir = output_dir / "figures"
    tables_dir = output_dir / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    summary = summary[SUMMARY_COLUMNS].copy()
    summary.to_csv(
        tables_dir / "lhtr_congested_window_sbr_ratio_summary.csv",
        index=False,
    )

    h80_key = "H80_200s"
    if h80_key not in detail_by_key:
        raise RuntimeError("H80_200s detailed windows are missing")
    h80_windows = detail_by_key[h80_key].copy()
    h80_detail = h80_windows[DETAIL_COLUMNS].copy()
    h80_detail.to_csv(tables_dir / "h80_200s_congested_windows.csv", index=False)

    plot_cross_level(summary, figures_dir / "lhtr_top25_congested_window_sbr_ratio.png")
    plot_h80_200s_bar(
        h80_200s_row(summary),
        figures_dir / "h80_200s_top25_congested_window_sbr_ratio.png",
    )
    plot_h80_timeseries(
        h80_windows,
        figures_dir / "h80_200s_sbr_and_congestion_score_timeseries.png",
    )

    report = report_text(summary, h80_windows)
    (output_dir / "analysis_report_zh.md").write_text(report, encoding="utf-8")


def main():
    args = parse_args()
    summaries = []
    detail_by_key = {}
    for row in manifest_rows():
        summary, windows = summarize_run(
            row,
            window_size_s=args.window_size_s,
            top_fraction=args.top_fraction,
        )
        summaries.append(summary)
        detail_by_key[summary["scenario_duration_id"]] = windows
    summary_frame = pd.DataFrame(summaries)
    summary_frame["scenario_id"] = pd.Categorical(
        summary_frame["scenario_id"],
        categories=SCENARIO_ORDER,
        ordered=True,
    )
    summary_frame = summary_frame.sort_values(
        ["duration_s", "scenario_id"],
        ascending=[True, True],
    ).reset_index(drop=True)
    summary_frame["scenario_id"] = summary_frame["scenario_id"].astype(str)
    write_outputs(summary_frame, detail_by_key, args.output_dir)
    print("Wrote analysis to %s" % args.output_dir)
    print("Rows: %d" % len(summary_frame))


if __name__ == "__main__":
    main()
