#!/usr/bin/env python3

import argparse
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-udp-pdr")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "runs" / "hotspot_5level_60s_formal_manifest.csv"
DEFAULT_FORMAL_SUMMARY = (
    SCRIPT_DIR
    / "analysis_reports"
    / "hotspot_5level_60s_formal"
    / "hotspot_5level_60s_formal_summary.csv"
)
DEFAULT_OUTPUT_DIR = (
    SCRIPT_DIR
    / "analysis_reports"
    / "hotspot_5level_60s_comparison"
)

SCENARIO_ORDER = ["H40", "H60", "H80", "H90", "H100+"]
ALGORITHM_ORDER = [
    "algorithm_free_one_only_over_isls",
    "algorithm_queue_aware_over_isls",
    "algorithm_lohi",
    "algorithm_lhtr",
]
ALGORITHM_LABELS = {
    "algorithm_free_one_only_over_isls": "Baseline",
    "algorithm_queue_aware_over_isls": "Queue-aware",
    "algorithm_lohi": "LoHi",
    "algorithm_lhtr": "LHTR",
}
ALGORITHM_COLORS = {
    "algorithm_free_one_only_over_isls": "#4D4D4D",
    "algorithm_queue_aware_over_isls": "#0072B2",
    "algorithm_lohi": "#D55E00",
    "algorithm_lhtr": "#009E73",
}
ALGORITHM_MARKERS = {
    "algorithm_free_one_only_over_isls": "o",
    "algorithm_queue_aware_over_isls": "s",
    "algorithm_lohi": "^",
    "algorithm_lhtr": "D",
}

SUMMARY_FIELDS = [
    "scenario",
    "hotspot_label",
    "load_level",
    "background_flow_count",
    "hotspot_reference_load_percent",
    "global_offered_isl_load_percent",
    "algorithm",
    "algorithm_label",
    "aggregate_pdr",
    "focus_pdr",
    "background_pdr",
    "min_pdr",
    "p5_pdr",
    "lost_packets",
    "mean_rtt_ms",
    "p95_rtt_ms",
    "mean_propagation_rtt_ms",
    "mean_queueing_delay_ms",
    "dominant_loss_attribution",
    "isl_associated_loss_proportion",
    "mixed_associated_loss_proportion",
    "gsl_associated_loss_proportion",
    "unclassified_loss_proportion",
    "isl_saturated_interface_count",
    "isl_at_capacity_sample_count",
    "focus_related_isl_at_capacity_sample_count",
    "gsl_saturated_interface_count",
    "gsl_at_capacity_sample_count",
    "max_gsl_queue_pkt",
    "mean_gsl_queue_pkt",
    "lhtr_br_selected_count",
    "lhtr_sbr_selected_count",
    "lhtr_sbr_selection_ratio",
    "lhtr_fallback_count",
    "lhtr_yellow_count",
    "lhtr_red_count",
    "lhtr_top_decision_reasons",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Build read-only cross-level comparisons for the five completed "
            "60 s UDP/PDR hotspot formal scenarios."
        )
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--formal-summary", default=str(DEFAULT_FORMAL_SUMMARY))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def require_csv(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError("Required CSV is missing: %s" % path)
    return pd.read_csv(path)


def safe_ratio(numerator, denominator):
    denominator = float(denominator)
    return float(numerator) / denominator if denominator > 0 else 0.0


def parse_flow_ids(value):
    if pd.isna(value):
        return set()
    result = set()
    for item in str(value).split(";"):
        try:
            result.add(int(item))
        except ValueError:
            continue
    return result


def first_matching(frame, **matches):
    selected = frame
    for column, value in matches.items():
        selected = selected[selected[column] == value]
    if len(selected) == 0:
        raise RuntimeError("No row matched %s" % matches)
    return selected.iloc[0]


def sum_column(frame, column):
    if column not in frame.columns or len(frame) == 0:
        return 0
    return int(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def top_lhtr_reasons(frame, limit=5):
    if len(frame) == 0:
        return ""
    ordered = frame.copy()
    ordered["count"] = pd.to_numeric(ordered["count"], errors="coerce").fillna(0)
    ordered = ordered.sort_values("count", ascending=False).head(limit)
    return ";".join(
        "%s:%d" % (row["decision_reason"], int(row["count"]))
        for _, row in ordered.iterrows()
    )


def queue_metrics(congested, algorithm):
    alg = congested[congested["algorithm"] == algorithm].copy()
    if len(alg) == 0:
        return {
            "isl_saturated_interface_count": 0,
            "isl_at_capacity_sample_count": 0,
            "focus_related_isl_at_capacity_sample_count": 0,
            "gsl_saturated_interface_count": 0,
            "gsl_at_capacity_sample_count": 0,
        }
    alg["samples_at_capacity"] = pd.to_numeric(
        alg["samples_at_capacity"], errors="coerce"
    ).fillna(0)
    isl = alg[alg["link_type"] == "ISL"]
    gsl = alg[alg["link_type"] == "GSL"]
    focus_related = isl[
        isl["flow_ids_passing_interface_if_available"].apply(
            lambda value: bool(parse_flow_ids(value) & {0, 1})
        )
    ]
    return {
        "isl_saturated_interface_count": int(isl["interface_key"].nunique()),
        "isl_at_capacity_sample_count": int(isl["samples_at_capacity"].sum()),
        "focus_related_isl_at_capacity_sample_count": int(
            focus_related["samples_at_capacity"].sum()
        ),
        "gsl_saturated_interface_count": int(gsl["interface_key"].nunique()),
        "gsl_at_capacity_sample_count": int(gsl["samples_at_capacity"].sum()),
    }


def loss_metrics(loss_row):
    lost = int(loss_row["synthetic_lost_packets"])
    values = {
        "isl_associated_loss_proportion": loss_row[
            "isl_saturation_associated_loss"
        ],
        "mixed_associated_loss_proportion": loss_row[
            "mixed_saturation_associated_loss"
        ],
        "gsl_associated_loss_proportion": loss_row[
            "gsl_saturation_associated_loss"
        ],
        "unclassified_loss_proportion": loss_row["unclassified_loss"],
    }
    return {
        key: safe_ratio(float(value), lost)
        for key, value in values.items()
    }


def load_cross_level_summary(manifest_path, formal_summary_path):
    manifest = require_csv(manifest_path)
    formal_summary = require_csv(formal_summary_path)
    manifest["scenario_id"] = pd.Categorical(
        manifest["scenario_id"],
        categories=SCENARIO_ORDER,
        ordered=True,
    )
    manifest = manifest.sort_values("scenario_id")
    scenario_ids = manifest["scenario_id"].astype(str).tolist()
    if scenario_ids != SCENARIO_ORDER:
        raise RuntimeError(
            "Manifest scenarios must be exactly %s; got %s"
            % (SCENARIO_ORDER, scenario_ids)
        )
    if not (manifest["status"] == "complete").all():
        raise RuntimeError("All formal scenarios must be complete before analysis")

    rows = []
    for _, scenario in manifest.iterrows():
        scenario_id = str(scenario["scenario_id"])
        run_dir = SCRIPT_DIR / str(scenario["run_folder"])
        comparison = run_dir / "comparison_packet_delivery"
        core = comparison / "core"
        diagnostics = comparison / "diagnostics"

        algorithm_summary = require_csv(core / "summary_by_algorithm.csv")
        loss = require_csv(core / "loss_attribution_breakdown_v3.csv")
        congested = require_csv(core / "congested_interfaces_summary.csv")
        rtt = require_csv(core / "udp_rtt_summary_by_algorithm.csv")
        gsl_queue = require_csv(diagnostics / "gsl_queue_summary.csv")
        lhtr_br = require_csv(diagnostics / "lhtr_br_sbr_summary.csv")
        lhtr_reasons = require_csv(
            diagnostics / "lhtr_decision_reason_summary.csv"
        )

        for algorithm in ALGORITHM_ORDER:
            core_row = first_matching(algorithm_summary, algorithm=algorithm)
            formal_row = first_matching(
                formal_summary,
                scenario_id=scenario_id,
                algorithm=algorithm,
            )
            loss_row = first_matching(loss, algorithm=algorithm)
            rtt_row = first_matching(
                rtt,
                algorithm=algorithm,
                direction="754_to_785",
            )
            gsl_row = first_matching(gsl_queue, algorithm=algorithm)
            queue = queue_metrics(congested, algorithm)

            br_count = 0
            sbr_count = 0
            fallback_count = 0
            yellow_count = 0
            red_count = 0
            reasons = ""
            if algorithm == "algorithm_lhtr":
                br_count = sum_column(lhtr_br, "br_selected_count")
                sbr_count = sum_column(lhtr_br, "sbr_selected_count")
                fallback_count = sum_column(lhtr_br, "fallback_count")
                yellow_count = sum_column(lhtr_br, "yellow_count")
                red_count = sum_column(lhtr_br, "red_count")
                reasons = top_lhtr_reasons(lhtr_reasons)

            mean_queueing = float(rtt_row["mean_forward_queue_delay_ms"]) + float(
                rtt_row["mean_reverse_queue_delay_ms"]
            )
            row = {
                "scenario": scenario_id,
                "hotspot_label": scenario["label"],
                "load_level": float(scenario["load_level"]),
                "background_flow_count": int(scenario["background_flow_count"]),
                "hotspot_reference_load_percent": float(
                    scenario["hotspot_reference_load_percent"]
                ),
                "global_offered_isl_load_percent": float(
                    scenario["global_offered_isl_load_percent"]
                ),
                "algorithm": algorithm,
                "algorithm_label": ALGORITHM_LABELS[algorithm],
                "aggregate_pdr": float(core_row["aggregate_pdr"]),
                "focus_pdr": float(core_row["focus_flow_pdr"]),
                "background_pdr": float(formal_row["background_pdr"]),
                "min_pdr": float(core_row["min_flow_pdr"]),
                "p5_pdr": float(core_row["p5_flow_pdr"]),
                "lost_packets": int(core_row["total_lost_packets"]),
                "mean_rtt_ms": float(rtt_row["mean_queue_aware_rtt_ms"]),
                "p95_rtt_ms": float(rtt_row["p95_queue_aware_rtt_ms"]),
                "mean_propagation_rtt_ms": float(
                    rtt_row["mean_propagation_only_rtt_ms"]
                ),
                "mean_queueing_delay_ms": mean_queueing,
                "dominant_loss_attribution": formal_row[
                    "dominant_loss_attribution"
                ],
                **loss_metrics(loss_row),
                **queue,
                "max_gsl_queue_pkt": int(gsl_row["max_gsl_queue_pkt"]),
                "mean_gsl_queue_pkt": float(gsl_row["mean_gsl_queue_pkt"]),
                "lhtr_br_selected_count": br_count,
                "lhtr_sbr_selected_count": sbr_count,
                "lhtr_sbr_selection_ratio": safe_ratio(
                    sbr_count,
                    br_count + sbr_count,
                ),
                "lhtr_fallback_count": fallback_count,
                "lhtr_yellow_count": yellow_count,
                "lhtr_red_count": red_count,
                "lhtr_top_decision_reasons": reasons,
            }
            rows.append(row)

    result = pd.DataFrame(rows, columns=SUMMARY_FIELDS)
    result["scenario"] = pd.Categorical(
        result["scenario"],
        categories=SCENARIO_ORDER,
        ordered=True,
    )
    result["algorithm"] = pd.Categorical(
        result["algorithm"],
        categories=ALGORITHM_ORDER,
        ordered=True,
    )
    return result.sort_values(["scenario", "algorithm"]).reset_index(drop=True)


def build_rankings(summary):
    rows = []
    for scenario in SCENARIO_ORDER:
        group = summary[summary["scenario"] == scenario].copy()
        group["aggregate_pdr_rank"] = group["aggregate_pdr"].rank(
            ascending=False,
            method="min",
        )
        group["mean_rtt_rank"] = group["mean_rtt_ms"].rank(
            ascending=True,
            method="min",
        )
        group["p95_rtt_rank"] = group["p95_rtt_ms"].rank(
            ascending=True,
            method="min",
        )
        group["composite_rank_score"] = (
            group["aggregate_pdr_rank"]
            + group["mean_rtt_rank"]
            + group["p95_rtt_rank"]
        )
        group["composite_rank"] = group["composite_rank_score"].rank(
            ascending=True,
            method="min",
        )
        for _, row in group.iterrows():
            rows.append(
                {
                    "scenario": scenario,
                    "hotspot_label": row["hotspot_label"],
                    "algorithm": str(row["algorithm"]),
                    "algorithm_label": row["algorithm_label"],
                    "aggregate_pdr": row["aggregate_pdr"],
                    "aggregate_pdr_rank": int(row["aggregate_pdr_rank"]),
                    "mean_rtt_ms": row["mean_rtt_ms"],
                    "mean_rtt_rank": int(row["mean_rtt_rank"]),
                    "p95_rtt_ms": row["p95_rtt_ms"],
                    "p95_rtt_rank": int(row["p95_rtt_rank"]),
                    "composite_rank_score": int(row["composite_rank_score"]),
                    "composite_rank": int(row["composite_rank"]),
                    "composite_definition": (
                        "sum of aggregate-PDR rank (higher is better), "
                        "mean-RTT rank, and p95-RTT rank (lower is better)"
                    ),
                }
            )
    return pd.DataFrame(rows)


def write_csv(frame, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def plot_lines(
    summary,
    metric,
    title,
    ylabel,
    output_path,
    algorithms=ALGORITHM_ORDER,
    ylim=None,
    log_scale=False,
):
    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    x_values = np.arange(len(SCENARIO_ORDER))
    for algorithm in algorithms:
        data = summary[summary["algorithm"] == algorithm].set_index("scenario")
        values = [float(data.loc[level, metric]) for level in SCENARIO_ORDER]
        ax.plot(
            x_values,
            values,
            label=ALGORITHM_LABELS[algorithm],
            color=ALGORITHM_COLORS[algorithm],
            marker=ALGORITHM_MARKERS[algorithm],
            linewidth=2.2,
            markersize=6,
        )
    ax.set_xticks(x_values, SCENARIO_ORDER)
    ax.set_xlabel("Hotspot congestion level")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.35)
    if ylim is not None:
        ax.set_ylim(*ylim)
    if log_scale:
        ax.set_yscale("log")
    ax.legend(frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def plot_lhtr_sbr_ratio(summary, output_path):
    data = summary[summary["algorithm"] == "algorithm_lhtr"].set_index("scenario")
    values = [
        100.0 * float(data.loc[level, "lhtr_sbr_selection_ratio"])
        for level in SCENARIO_ORDER
    ]
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.plot(
        SCENARIO_ORDER,
        values,
        color=ALGORITHM_COLORS["algorithm_lhtr"],
        marker="D",
        linewidth=2.2,
    )
    ax.set_xlabel("Hotspot congestion level")
    ax.set_ylabel("SBR selections / (BR + SBR) (%)")
    ax.set_title("LHTR SBR usage across hotspot levels")
    ax.grid(True, linestyle="--", alpha=0.35)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def plot_lhtr_colors(summary, output_path):
    data = summary[summary["algorithm"] == "algorithm_lhtr"].set_index("scenario")
    yellow = [int(data.loc[level, "lhtr_yellow_count"]) for level in SCENARIO_ORDER]
    red = [int(data.loc[level, "lhtr_red_count"]) for level in SCENARIO_ORDER]
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.plot(
        SCENARIO_ORDER,
        yellow,
        label="Yellow observations",
        color="#E69F00",
        marker="o",
        linewidth=2.2,
    )
    ax.plot(
        SCENARIO_ORDER,
        red,
        label="Red observations",
        color="#CC3311",
        marker="s",
        linewidth=2.2,
    )
    ax.set_yscale("log")
    ax.set_xlabel("Hotspot congestion level")
    ax.set_ylabel("Observation count (log scale)")
    ax.set_title("LHTR yellow/red observations across hotspot levels")
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def plot_flow_tail(summary, output_path):
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5), sharey=True)
    for axis, metric, title in [
        (axes[0], "min_pdr", "Minimum flow PDR"),
        (axes[1], "p5_pdr", "5th-percentile flow PDR"),
    ]:
        for algorithm in ALGORITHM_ORDER:
            data = summary[summary["algorithm"] == algorithm].set_index("scenario")
            axis.plot(
                SCENARIO_ORDER,
                [float(data.loc[level, metric]) for level in SCENARIO_ORDER],
                label=ALGORITHM_LABELS[algorithm],
                color=ALGORITHM_COLORS[algorithm],
                marker=ALGORITHM_MARKERS[algorithm],
                linewidth=2.0,
            )
        axis.set_title(title)
        axis.set_xlabel("Hotspot congestion level")
        axis.grid(True, linestyle="--", alpha=0.35)
        axis.set_ylim(0, 1.03)
    axes[0].set_ylabel("PDR")
    axes[1].legend(frameon=False, fontsize=9)
    fig.suptitle("Flow-tail delivery across hotspot levels")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def plot_rtt_components(summary, output_path):
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5))
    for algorithm in ALGORITHM_ORDER:
        data = summary[summary["algorithm"] == algorithm].set_index("scenario")
        kwargs = {
            "label": ALGORITHM_LABELS[algorithm],
            "color": ALGORITHM_COLORS[algorithm],
            "marker": ALGORITHM_MARKERS[algorithm],
            "linewidth": 2.0,
        }
        axes[0].plot(
            SCENARIO_ORDER,
            [
                float(data.loc[level, "mean_propagation_rtt_ms"])
                for level in SCENARIO_ORDER
            ],
            **kwargs,
        )
        axes[1].plot(
            SCENARIO_ORDER,
            [
                float(data.loc[level, "mean_queueing_delay_ms"])
                for level in SCENARIO_ORDER
            ],
            **kwargs,
        )
    axes[0].set_title("Propagation-only RTT")
    axes[1].set_title("Estimated queueing delay")
    for axis in axes:
        axis.set_xlabel("Hotspot congestion level")
        axis.set_ylabel("Milliseconds")
        axis.grid(True, linestyle="--", alpha=0.35)
    axes[1].legend(frameon=False, fontsize=9)
    fig.suptitle("RTT components across hotspot levels")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def plot_loss_proportions(summary, output_path):
    labels = [
        "ISL-associated",
        "Mixed-associated",
        "GSL-associated",
        "Unclassified",
    ]
    columns = [
        "isl_associated_loss_proportion",
        "mixed_associated_loss_proportion",
        "gsl_associated_loss_proportion",
        "unclassified_loss_proportion",
    ]
    colors = ["#0072B2", "#CC79A7", "#E69F00", "#999999"]
    positions = np.arange(len(summary))
    bottom = np.zeros(len(summary))
    fig, ax = plt.subplots(figsize=(13.5, 5.3))
    for label, column, color in zip(labels, columns, colors):
        values = summary[column].astype(float).to_numpy()
        ax.bar(positions, values, bottom=bottom, label=label, color=color)
        bottom += values
    tick_labels = [
        "%s\n%s" % (row["scenario"], row["algorithm_label"])
        for _, row in summary.iterrows()
    ]
    ax.set_xticks(positions, tick_labels, rotation=55, ha="right")
    ax.set_ylabel("Share of synthetic lost packets")
    ax.set_ylim(0, 1.03)
    ax.set_title("Loss-attribution proportions across hotspot levels")
    ax.legend(frameon=False, ncol=4, loc="upper center")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def plot_manifest_rows():
    return [
        (
            "figures/aggregate_pdr_across_hotspot_levels.png",
            "Aggregate PDR across hotspot levels",
            "aggregate_pdr",
            "A",
            "Primary thesis result: end-to-end delivery degradation and algorithm separation.",
        ),
        (
            "figures/focus_pdr_across_hotspot_levels.png",
            "Focus-flow PDR across hotspot levels",
            "focus_pdr",
            "A",
            "Shows protection of the Johannesburg-Fukuoka focus pair.",
        ),
        (
            "figures/background_pdr_across_hotspot_levels.png",
            "Background-flow PDR across hotspot levels",
            "background_pdr",
            "B",
            "Checks whether focus-flow gains are accompanied by background degradation.",
        ),
        (
            "figures/mean_rtt_across_hotspot_levels.png",
            "Mean estimated RTT across hotspot levels",
            "mean_rtt_ms",
            "A",
            "Primary latency comparison and PDR/RTT tradeoff.",
        ),
        (
            "figures/p95_rtt_across_hotspot_levels.png",
            "P95 estimated RTT across hotspot levels",
            "p95_rtt_ms",
            "B",
            "Tail-latency support for the mean RTT result.",
        ),
        (
            "figures/lost_packets_across_hotspot_levels.png",
            "Lost packets across hotspot levels",
            "lost_packets",
            "B",
            "Absolute loss magnitude on a logarithmic scale.",
        ),
        (
            "figures/lhtr_sbr_ratio_across_hotspot_levels.png",
            "LHTR SBR usage across hotspot levels",
            "lhtr_sbr_selection_ratio",
            "A",
            "Connects LHTR behavior to increasing congestion.",
        ),
        (
            "figures/lhtr_yellow_red_across_hotspot_levels.png",
            "LHTR yellow/red observations across hotspot levels",
            "lhtr_yellow_count;lhtr_red_count",
            "B",
            "Supports the SBR activation interpretation; logarithmic count axis.",
        ),
        (
            "figures/flow_tail_pdr_across_hotspot_levels.png",
            "Flow-tail PDR across hotspot levels",
            "min_pdr;p5_pdr",
            "B",
            "Appendix fairness and worst-flow evidence.",
        ),
        (
            "figures/rtt_components_across_hotspot_levels.png",
            "RTT components across hotspot levels",
            "mean_propagation_rtt_ms;mean_queueing_delay_ms",
            "B",
            "Separates path propagation from estimated queueing.",
        ),
        (
            "figures/isl_at_capacity_samples_across_hotspot_levels.png",
            "ISL at-capacity samples across hotspot levels",
            "isl_at_capacity_sample_count",
            "C",
            "Internal congestion diagnostic; counts depend on sampled interfaces and routing paths.",
        ),
        (
            "figures/loss_attribution_proportions_across_hotspot_levels.png",
            "Loss-attribution proportions across hotspot levels",
            "loss_attribution_proportions",
            "C",
            "Diagnostic association, not physical drop proof.",
        ),
    ]


def build_plot_manifest():
    return pd.DataFrame(
        plot_manifest_rows(),
        columns=[
            "plot_filename",
            "title",
            "metric",
            "tier",
            "recommended_usage",
        ],
    )


def build_output_catalog(plot_manifest):
    rows = [
        (
            "analysis_report_zh.md",
            "report",
            "A",
            "Primary Traditional Chinese interpretation and recommendation.",
        ),
        (
            "hotspot_5level_cross_level_summary.csv",
            "table",
            "A",
            "Canonical 20-row cross-level dataset.",
        ),
        (
            "hotspot_5level_algorithm_rankings.csv",
            "table",
            "B",
            "Per-level PDR and RTT rankings with an explicitly defined composite.",
        ),
        (
            "tables/aggregate_pdr_across_hotspot_levels.csv",
            "table",
            "A",
            "Data table for the primary aggregate-PDR figure.",
        ),
        (
            "tables/focus_pdr_across_hotspot_levels.csv",
            "table",
            "A",
            "Focus-pair delivery comparison.",
        ),
        (
            "tables/background_pdr_across_hotspot_levels.csv",
            "table",
            "B",
            "Background-flow delivery support.",
        ),
        (
            "tables/mean_rtt_across_hotspot_levels.csv",
            "table",
            "A",
            "Data table for the primary mean-RTT figure.",
        ),
        (
            "tables/p95_rtt_across_hotspot_levels.csv",
            "table",
            "B",
            "Tail-latency support.",
        ),
        (
            "tables/pdr_algorithm_gaps_by_level.csv",
            "table",
            "A",
            "Direct LHTR-LoHi and Queue-aware-LHTR PDR gaps.",
        ),
        (
            "tables/lhtr_diagnostics_across_hotspot_levels.csv",
            "table",
            "B",
            "SBR, yellow/red, fallback, and decision-reason support.",
        ),
        (
            "tables/flow_tail_pdr_across_hotspot_levels.csv",
            "table",
            "B",
            "Minimum and fifth-percentile flow PDR support.",
        ),
        (
            "tables/rtt_components_across_hotspot_levels.csv",
            "table",
            "B",
            "Propagation and estimated queueing components.",
        ),
        (
            "tables/lost_packets_across_hotspot_levels.csv",
            "table",
            "B",
            "Absolute lost-packet counts.",
        ),
        (
            "tables/isl_at_capacity_samples_across_hotspot_levels.csv",
            "table",
            "C",
            "Sample-dependent internal queue-pressure diagnostic.",
        ),
        (
            "tables/loss_attribution_proportions.csv",
            "table",
            "C",
            "Association breakdown; not physical drop proof.",
        ),
        (
            "hotspot_5level_plot_manifest.csv",
            "manifest",
            "C",
            "Machine-readable figure inventory.",
        ),
        (
            "hotspot_5level_output_catalog.csv",
            "manifest",
            "C",
            "Machine-readable tier classification for all final outputs.",
        ),
    ]
    rows.extend(
        (
            row["plot_filename"],
            "figure",
            row["tier"],
            row["recommended_usage"],
        )
        for _, row in plot_manifest.iterrows()
    )
    return pd.DataFrame(
        rows,
        columns=["filename", "output_type", "tier", "recommended_usage"],
    )


def write_metric_table(summary, metric, path):
    table = summary.pivot(
        index="scenario",
        columns="algorithm_label",
        values=metric,
    ).reindex(SCENARIO_ORDER)
    table = table.reindex(
        columns=[ALGORITHM_LABELS[item] for item in ALGORITHM_ORDER]
    )
    table.index.name = "scenario"
    write_csv(table.reset_index(), path)


def pdr_gap_table(summary):
    pivot = summary.pivot(
        index="scenario",
        columns="algorithm_label",
        values="aggregate_pdr",
    ).reindex(SCENARIO_ORDER)
    rows = []
    ideal_order = ["Baseline", "LoHi", "LHTR", "Queue-aware"]
    for scenario, row in pivot.iterrows():
        ordered = list(row.sort_values().index)
        rows.append(
            {
                "scenario": scenario,
                "baseline_pdr": row["Baseline"],
                "lohi_pdr": row["LoHi"],
                "lhtr_pdr": row["LHTR"],
                "queue_aware_pdr": row["Queue-aware"],
                "lhtr_minus_lohi_percentage_points": 100.0
                * (row["LHTR"] - row["LoHi"]),
                "queue_aware_minus_lhtr_percentage_points": 100.0
                * (row["Queue-aware"] - row["LHTR"]),
                "observed_ascending_order": " < ".join(ordered),
                "matches_ideal_order": ordered == ideal_order,
            }
        )
    return pd.DataFrame(rows)


def fmt_pp(value):
    return "%.2f percentage points" % float(value)


def write_report(summary, output_catalog, pdr_gaps, output_dir):
    output_dir = Path(output_dir)
    lhtr = summary[summary["algorithm"] == "algorithm_lhtr"].set_index("scenario")
    lohi = summary[summary["algorithm"] == "algorithm_lohi"].set_index("scenario")
    queue = summary[
        summary["algorithm"] == "algorithm_queue_aware_over_isls"
    ].set_index("scenario")
    baseline = summary[
        summary["algorithm"] == "algorithm_free_one_only_over_isls"
    ].set_index("scenario")

    largest_lhtr_gain = pdr_gaps.loc[
        pdr_gaps["lhtr_minus_lohi_percentage_points"].idxmax()
    ]
    largest_queue_gap = pdr_gaps.loc[
        pdr_gaps["queue_aware_minus_lhtr_percentage_points"].idxmax()
    ]
    ideal_levels = pdr_gaps[pdr_gaps["matches_ideal_order"]]["scenario"].tolist()
    sbr_ratios = {
        level: 100.0 * float(lhtr.loc[level, "lhtr_sbr_selection_ratio"])
        for level in SCENARIO_ORDER
    }

    tier_lines = []
    for tier in ["A", "B", "C"]:
        tier_lines.append("### Tier %s" % tier)
        for _, row in output_catalog[output_catalog["tier"] == tier].iterrows():
            tier_lines.append(
                "- `%s` (%s): %s"
                % (
                    row["filename"],
                    row["output_type"],
                    row["recommended_usage"],
                )
            )
        tier_lines.append("")

    report = f"""# 5-Level UDP/PDR 60s Formal Cross-Level Analysis

## 1. 分析範圍

本報告只讀取既有五個 60 秒 formal runs 的 compact comparison CSV；沒有執行
step 1、step 2、step 3，也沒有修改任何 routing algorithm。X 軸固定為
`H40, H60, H80, H90, H100+`。RTT 是 queue-history-based estimated RTT，
不是 packet-level measured RTT。

## 2. Main result

- 五個 level 構成清楚的性能退化曲線。Baseline aggregate PDR 從
  {baseline.loc["H40", "aggregate_pdr"]:.4f} 降至
  {baseline.loc["H100+", "aggregate_pdr"]:.4f}；Queue-aware 從
  {queue.loc["H40", "aggregate_pdr"]:.4f} 降至
  {queue.loc["H100+", "aggregate_pdr"]:.4f}；LoHi 從
  {lohi.loc["H40", "aggregate_pdr"]:.4f} 降至
  {lohi.loc["H100+", "aggregate_pdr"]:.4f}；LHTR 從
  {lhtr.loc["H40", "aggregate_pdr"]:.4f} 降至
  {lhtr.loc["H100+", "aggregate_pdr"]:.4f}。
- `Baseline < LoHi < LHTR < Queue-aware` 在
  `{", ".join(ideal_levels)}` 成立。H40 不成立，因為 LHTR
  ({lhtr.loc["H40", "aggregate_pdr"]:.6f}) 略高於 Queue-aware
  ({queue.loc["H40", "aggregate_pdr"]:.6f})，差距只有
  {abs(100.0 * (lhtr.loc["H40", "aggregate_pdr"] - queue.loc["H40", "aggregate_pdr"])):.03f}
  percentage points；沒有重複實驗或信賴區間時，不應把這個微小差距解讀成穩定勝出。
- LHTR 相對 LoHi 的最大 aggregate-PDR 改善出現在
  **{largest_lhtr_gain["scenario"]}**，為
  **{fmt_pp(largest_lhtr_gain["lhtr_minus_lohi_percentage_points"])}**。
- Queue-aware 相對 LHTR 的最大差距出現在
  **{largest_queue_gap["scenario"]}**，為
  **{fmt_pp(largest_queue_gap["queue_aware_minus_lhtr_percentage_points"])}**。

## 3. RTT interpretation

- Baseline mean RTT 從 {baseline.loc["H40", "mean_rtt_ms"]:.1f} ms 增至
  {baseline.loc["H100+", "mean_rtt_ms"]:.1f} ms，顯示固定路徑上的 queueing
  隨壓力快速累積。
- Queue-aware 維持最低且最平滑的 RTT，從
  {queue.loc["H40", "mean_rtt_ms"]:.1f} ms 增至
  {queue.loc["H100+", "mean_rtt_ms"]:.1f} ms。
- LHTR 在 H40/H60 與 Queue-aware 接近，但 H80 之後 gap 擴大。它以較高 RTT
  換得顯著優於 LoHi 的 PDR，但沒有達到 Queue-aware 的全域調適效果。
- LoHi mean RTT 從 {lohi.loc["H40", "mean_rtt_ms"]:.1f} ms 增至
  {lohi.loc["H100+", "mean_rtt_ms"]:.1f} ms。從現有資料可推論，manager
  路徑約束與較有限的壅塞繞行使部分路徑承受較長 queue delay；這是 queue/path
  association，不能單獨視為 policy 因果證明。

## 4. LHTR diagnostics

- SBR ratio 隨 congestion level 單調增加：H40={sbr_ratios["H40"]:.6f}%、
  H60={sbr_ratios["H60"]:.6f}%、H80={sbr_ratios["H80"]:.6f}%、
  H90={sbr_ratios["H90"]:.6f}%、H100+={sbr_ratios["H100+"]:.6f}%。
- Yellow/red observations 同步大幅增加，方向與 SBR activation 一致。
- 即使 yellow/red 增加，LHTR 仍落後 Queue-aware，因為 SBR 在全部 BR+SBR
  decisions 中仍是少數；`no_alternative_candidate` 與
  `sbr_stretch_too_high` 也是主要 decision reasons，表示偵測壅塞不等於每次
  都有可接受的替代路徑。
- H40 壓力低，BR 已足以維持近乎完整交付，因此 LHTR 與 Queue-aware 幾乎相同；
  其微小領先不宜過度解讀。
- H90/H100+ 中 LHTR 分別比 LoHi 高
  {100.0 * (lhtr.loc["H90", "aggregate_pdr"] - lohi.loc["H90", "aggregate_pdr"]):.2f}
  與
  {100.0 * (lhtr.loc["H100+", "aggregate_pdr"] - lohi.loc["H100+", "aggregate_pdr"]):.2f}
  percentage points，足以支持「LHTR 在 severe/overload 下優於 LoHi」的敘事；
  但同時必須呈現它仍明顯落後 Queue-aware。

## 5. Queue and loss interpretation

- 所有演算法在各 level 的 dominant loss 都是 ISL-saturation-associated loss。
  GSL max queue 僅為低個位數，支持此實驗主要量測 ISL bottleneck。
- `isl_at_capacity_sample_count` 比 max queue 更有資訊量，因為 max ISL queue
  幾乎都會到 100。
- Loss attribution 是 time/path/queue association，不是 physical drop proof；
  因此 attribution proportion 圖列為 diagnostics only。

## 6. Output tiers

{os.linesep.join(tier_lines)}
## 7. Recommendation

1. **Main figure candidate: H80。** 四個演算法排序完整，且 LHTR 相對 LoHi
   改善最大，最適合說明 traffic-light rerouting 的價值。
2. **Stress-test candidate: H100+。** 它最能顯示 overload 下的性能邊界，
   也是 Queue-aware 與 LHTR gap 最大的 level。
3. 建議做 targeted 200s，而不是五個 level 全跑。優先順序是 **H80 first**，
   確認主要敘事在長時間下穩定；資源允許時再跑 **H100+** 作 stress test。
4. 在改 LHTR/LoHi policy 前，應先做更深入的 path/decision diagnostics：
   分析 `no_alternative_candidate`、stretch rejection、SBR 生效時間與 focus-flow
   loss/RTT 的時間對齊。現有結果不足以直接支持 policy 修改。
5. 若只選兩個後續 level，選 **H80 + H100+**。

## 8. Ranking definition

`hotspot_5level_algorithm_rankings.csv` 分別計算 aggregate PDR（高者較佳）、
mean RTT 與 p95 RTT（低者較佳）的 level-internal rank。Composite score 是三個
rank 的等權總和；它只用於摘要，不取代個別 PDR/RTT 指標。

## 9. Limitations

- 每個 scenario 目前只有一個 60s run，沒有重複實驗與 confidence interval。
- BG flow count 在 level 間改變，因此這是一條 formal scenario severity curve，
  不是只改單一連續自變數的 controlled sweep。
- Estimated RTT 包含 replayed path 與 queue history，不能宣稱為封包實測 RTT。
- H40 的 Queue-aware/LHTR 差距太小，需重複或長時間 run 才能判斷穩定性。
"""
    (output_dir / "analysis_report_zh.md").write_text(report, encoding="utf-8")


def validate_outputs(output_dir, output_catalog):
    output_dir = Path(output_dir)
    required = [
        output_dir / filename
        for filename in output_catalog["filename"]
    ]
    missing = [str(path) for path in required if not path.is_file()]
    empty = [
        str(path)
        for path in required
        if path.is_file() and path.stat().st_size == 0
    ]
    if missing or empty:
        raise RuntimeError(
            "Output validation failed; missing=%s empty=%s" % (missing, empty)
        )


def main():
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    runs_dir = (SCRIPT_DIR / "runs").resolve()
    if output_dir == runs_dir or runs_dir in output_dir.parents:
        raise RuntimeError("Analysis output must not be written inside runs/")

    figures_dir = output_dir / "figures"
    tables_dir = output_dir / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    summary = load_cross_level_summary(args.manifest, args.formal_summary)
    rankings = build_rankings(summary)
    plot_manifest = build_plot_manifest()
    output_catalog = build_output_catalog(plot_manifest)
    gaps = pdr_gap_table(summary)

    write_csv(summary, output_dir / "hotspot_5level_cross_level_summary.csv")
    write_csv(rankings, output_dir / "hotspot_5level_algorithm_rankings.csv")
    write_csv(plot_manifest, output_dir / "hotspot_5level_plot_manifest.csv")
    write_csv(output_catalog, output_dir / "hotspot_5level_output_catalog.csv")
    write_csv(gaps, tables_dir / "pdr_algorithm_gaps_by_level.csv")

    metric_tables = {
        "aggregate_pdr": "aggregate_pdr_across_hotspot_levels.csv",
        "focus_pdr": "focus_pdr_across_hotspot_levels.csv",
        "background_pdr": "background_pdr_across_hotspot_levels.csv",
        "mean_rtt_ms": "mean_rtt_across_hotspot_levels.csv",
        "p95_rtt_ms": "p95_rtt_across_hotspot_levels.csv",
        "lost_packets": "lost_packets_across_hotspot_levels.csv",
        "isl_at_capacity_sample_count": (
            "isl_at_capacity_samples_across_hotspot_levels.csv"
        ),
    }
    for metric, filename in metric_tables.items():
        write_metric_table(summary, metric, tables_dir / filename)
    write_csv(
        summary[summary["algorithm"] == "algorithm_lhtr"][
            [
                "scenario",
                "lhtr_br_selected_count",
                "lhtr_sbr_selected_count",
                "lhtr_sbr_selection_ratio",
                "lhtr_fallback_count",
                "lhtr_yellow_count",
                "lhtr_red_count",
                "lhtr_top_decision_reasons",
            ]
        ],
        tables_dir / "lhtr_diagnostics_across_hotspot_levels.csv",
    )
    write_csv(
        summary[
            [
                "scenario",
                "algorithm_label",
                "isl_associated_loss_proportion",
                "mixed_associated_loss_proportion",
                "gsl_associated_loss_proportion",
                "unclassified_loss_proportion",
            ]
        ],
        tables_dir / "loss_attribution_proportions.csv",
    )
    write_csv(
        summary[
            [
                "scenario",
                "algorithm_label",
                "min_pdr",
                "p5_pdr",
            ]
        ],
        tables_dir / "flow_tail_pdr_across_hotspot_levels.csv",
    )
    write_csv(
        summary[
            [
                "scenario",
                "algorithm_label",
                "mean_propagation_rtt_ms",
                "mean_queueing_delay_ms",
                "mean_rtt_ms",
                "p95_rtt_ms",
            ]
        ],
        tables_dir / "rtt_components_across_hotspot_levels.csv",
    )

    plot_lines(
        summary,
        "aggregate_pdr",
        "Aggregate PDR across hotspot levels",
        "Aggregate PDR",
        figures_dir / "aggregate_pdr_across_hotspot_levels.png",
        ylim=(0, 1.03),
    )
    plot_lines(
        summary,
        "focus_pdr",
        "Focus-flow PDR across hotspot levels",
        "Focus-flow PDR",
        figures_dir / "focus_pdr_across_hotspot_levels.png",
        ylim=(0, 1.03),
    )
    plot_lines(
        summary,
        "background_pdr",
        "Background-flow PDR across hotspot levels",
        "Background-flow PDR",
        figures_dir / "background_pdr_across_hotspot_levels.png",
        ylim=(0, 1.03),
    )
    plot_lines(
        summary,
        "mean_rtt_ms",
        "Mean estimated RTT across hotspot levels",
        "Mean estimated RTT (ms)",
        figures_dir / "mean_rtt_across_hotspot_levels.png",
    )
    plot_lines(
        summary,
        "p95_rtt_ms",
        "P95 estimated RTT across hotspot levels",
        "P95 estimated RTT (ms)",
        figures_dir / "p95_rtt_across_hotspot_levels.png",
    )
    plot_lines(
        summary,
        "lost_packets",
        "Lost packets across hotspot levels",
        "Lost packets (log scale)",
        figures_dir / "lost_packets_across_hotspot_levels.png",
        log_scale=True,
    )
    plot_lines(
        summary,
        "isl_at_capacity_sample_count",
        "ISL at-capacity samples across hotspot levels",
        "At-capacity sample count (log scale)",
        figures_dir / "isl_at_capacity_samples_across_hotspot_levels.png",
        log_scale=True,
    )
    plot_lhtr_sbr_ratio(
        summary,
        figures_dir / "lhtr_sbr_ratio_across_hotspot_levels.png",
    )
    plot_lhtr_colors(
        summary,
        figures_dir / "lhtr_yellow_red_across_hotspot_levels.png",
    )
    plot_flow_tail(
        summary,
        figures_dir / "flow_tail_pdr_across_hotspot_levels.png",
    )
    plot_rtt_components(
        summary,
        figures_dir / "rtt_components_across_hotspot_levels.png",
    )
    plot_loss_proportions(
        summary,
        figures_dir / "loss_attribution_proportions_across_hotspot_levels.png",
    )

    write_report(summary, output_catalog, gaps, output_dir)
    validate_outputs(output_dir, output_catalog)
    print("Cross-level summary: %s" % (
        output_dir / "hotspot_5level_cross_level_summary.csv"
    ))
    print("Rankings: %s" % (
        output_dir / "hotspot_5level_algorithm_rankings.csv"
    ))
    print("Plot manifest: %s" % (
        output_dir / "hotspot_5level_plot_manifest.csv"
    ))
    print("Report: %s" % (output_dir / "analysis_report_zh.md"))
    print("Figures generated: %d" % len(plot_manifest))


if __name__ == "__main__":
    main()
