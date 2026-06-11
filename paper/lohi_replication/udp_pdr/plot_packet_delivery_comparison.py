import os
import sys

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-udp-pdr")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__)))
from dynamic_run_list import (
    build_arg_parser,
    describe_selection,
    get_udp_pdr_run_list,
    resolve_existing_run,
    validate_focus_pair_arguments,
)
from packet_delivery_outputs import (
    ensure_standard_layout,
    output_path,
    resolve_input_path,
    write_output_manifest,
)


def _short_label(label):
    labels = {
        "algorithm_free_one_only_over_isls": "Baseline",
        "algorithm_queue_aware_over_isls": "Queue-aware",
        "algorithm_lohi": "LoHi",
        "algorithm_lhtr": "LHTR",
        "algorithm_tlr": "TLR",
    }
    return labels.get(
        label,
        label.replace("algorithm_", "").replace("_over_isls", ""),
    )


def _bar_plot(df, x_col, y_col, output_path, ylabel, title=None):
    plt.figure(figsize=(9, 4.8))
    labels = [_short_label(x) for x in df[x_col]]
    plt.bar(labels, df[y_col], color="#2878b5")
    plt.ylabel(ylabel)
    plt.xticks(rotation=25, ha="right")
    if title:
        plt.title(title)
    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()


def _stacked_bar(df, index_col, value_cols, output_path, ylabel, title):
    if len(df) == 0:
        return
    plot_df = df.set_index(index_col)[value_cols].copy()
    plot_df.index = [_short_label(x) for x in plot_df.index]
    plot_df.plot(kind="bar", stacked=True, figsize=(9, 4.8))
    plt.ylabel(ylabel)
    plt.xticks(rotation=25, ha="right")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()


def _timing_title(base_title, df):
    if "traffic_stop_time_s" not in df.columns or "drain_time_s" not in df.columns or len(df) == 0:
        return base_title
    traffic_stop_time_s = float(df["traffic_stop_time_s"].iloc[0])
    drain_time_s = float(df["drain_time_s"].iloc[0])
    return "%s (stop %.3gs, drain %.3gs)" % (base_title, traffic_stop_time_s, drain_time_s)


def _write_deprecated_link_drop_heatmap_notice(output_path_value):
    plt.figure(figsize=(8, 3.2))
    plt.axis("off")
    plt.text(
        0.5,
        0.62,
        "Deprecated filename",
        ha="center",
        va="center",
        fontsize=16,
        weight="bold",
    )
    plt.text(
        0.5,
        0.42,
        "Use max_queue_occupancy_top_links.png",
        ha="center",
        va="center",
        fontsize=12,
    )
    plt.text(
        0.5,
        0.25,
        "This experiment has sampled ISL queue occupancy, not a physical packet-drop heatmap.",
        ha="center",
        va="center",
        fontsize=10,
    )
    plt.tight_layout()
    plt.savefig(output_path_value, dpi=180)
    plt.close()


def plot_single_run(
    comparison_dir,
    output_layout="standard",
    write_legacy_outputs=False,
):
    if output_layout == "standard":
        ensure_standard_layout(comparison_dir)

    def source(filename):
        return resolve_input_path(comparison_dir, filename)

    def destination(filename):
        return output_path(comparison_dir, filename, output_layout)

    summary_path = source("summary_by_algorithm.csv")
    per_flow_path = source("per_flow_delivery.csv")
    queue_path = source("max_queue_occupancy_by_algorithm.csv")
    top_loss_path = source("top_loss_flows.csv")
    destination_path = source("destination_loss_summary.csv")
    physical_drop_path = source("physical_drop_summary.csv")
    gsl_queue_path = source("gsl_queue_summary.csv")
    loss_attribution_path = source("loss_attribution_summary.csv")
    loss_attribution_v2_path = source("loss_attribution_breakdown_v2.csv")
    loss_attribution_v3_path = source("loss_attribution_breakdown_v3.csv")
    tag_coverage_path = source("tag_coverage_diagnostics.csv")
    congested_interfaces_path = source("congested_interfaces_summary.csv")
    queue_saturation_timeline_path = source(
        "queue_saturation_timeline_at_capacity.csv"
    )
    if not os.path.exists(queue_saturation_timeline_path):
        queue_saturation_timeline_path = source("queue_saturation_timeline.csv")
    corridor_concentration_path = source("corridor_concentration_summary.csv")
    satellite_interface_path = source("satellite_interface_load_summary.csv")
    fallback_phase_path = source("fallback_phase_summary.csv")
    if not os.path.exists(summary_path) or not os.path.exists(per_flow_path):
        print("Skipping plots; missing analysis outputs in %s" % comparison_dir)
        return

    summary = pd.read_csv(summary_path)
    per_flow = pd.read_csv(per_flow_path)
    if len(summary) == 0:
        return

    _bar_plot(
        summary,
        "algorithm",
        "aggregate_pdr",
        destination("aggregate_pdr.png"),
        "Aggregate PDR",
        _timing_title("Aggregate PDR", summary),
    )
    _bar_plot(
        summary,
        "algorithm",
        "focus_flow_pdr",
        destination("focus_flow_pdr.png"),
        "Focus-flow PDR",
        _timing_title("Focus-flow PDR", summary),
    )
    _bar_plot(
        summary,
        "algorithm",
        "total_lost_packets",
        destination("packet_loss_count_by_algorithm.png"),
        "Lost packets",
        _timing_title("Synthetic Sent-minus-Received Loss", summary),
    )
    _bar_plot(
        summary,
        "algorithm",
        "failed_flow_count",
        destination("failed_flow_count.png"),
        "Failed flow count",
        _timing_title("Failed Flow Count", summary),
    )

    if os.path.exists(physical_drop_path):
        physical = pd.read_csv(physical_drop_path)
        algorithms = summary[["algorithm"]].drop_duplicates().sort_values("algorithm")
        if len(physical):
            by_algorithm = (
                physical.groupby("algorithm")["drop_count"]
                .sum()
                .reset_index()
                .sort_values("algorithm")
            )
            by_algorithm = algorithms.merge(by_algorithm, on="algorithm", how="left")
            by_algorithm["drop_count"] = by_algorithm["drop_count"].fillna(0)
            by_link_type = (
                physical.pivot_table(
                    index="algorithm",
                    columns="link_type",
                    values="drop_count",
                    aggfunc="sum",
                    fill_value=0,
                )
                .reset_index()
            )
            by_link_type = algorithms.merge(by_link_type, on="algorithm", how="left")
        else:
            by_algorithm = algorithms.copy()
            by_algorithm["drop_count"] = 0
            by_link_type = algorithms.copy()
        for link_type in ["ISL", "GSL", "UNKNOWN"]:
            if link_type not in by_link_type.columns:
                by_link_type[link_type] = 0
        value_cols = [col for col in ["ISL", "GSL", "UNKNOWN"] if col in by_link_type.columns]
        by_link_type[value_cols] = by_link_type[value_cols].fillna(0)
        exact_drop_total = int(by_algorithm["drop_count"].sum())
        physical_title = (
            "Physical Drop Count by Algorithm"
            if exact_drop_total
            else "No exact physical drop trace events were recorded."
        )
        _bar_plot(
            by_algorithm,
            "algorithm",
            "drop_count",
            destination("physical_drop_count_by_algorithm.png"),
            "Physical drop trace events",
            physical_title,
        )
        _stacked_bar(
            by_link_type,
            "algorithm",
            value_cols,
            destination("physical_drop_by_link_type.png"),
            "Physical drop trace events",
            (
                "Physical Drops by Link Type"
                if exact_drop_total
                else "No exact physical drop trace events were recorded."
            ),
        )

    if os.path.exists(gsl_queue_path):
        gsl_queue = pd.read_csv(gsl_queue_path)
        if len(gsl_queue):
            _bar_plot(
                gsl_queue,
                "algorithm",
                "max_gsl_queue_pkt",
                destination("gsl_queue_occupancy_by_algorithm.png"),
                "Max GSL/access queue occupancy (packets)",
                "GSL Queue Occupancy by Algorithm",
            )

    if write_legacy_outputs and os.path.exists(loss_attribution_path):
        attribution = pd.read_csv(loss_attribution_path)
        if len(attribution):
            attribution = attribution.copy()
            attribution["unexplained_loss_nonnegative"] = attribution[
                "unexplained_loss"
            ].clip(lower=0)
            _stacked_bar(
                attribution,
                "algorithm",
                [
                    "physical_drop_packets",
                    "send_failed_packets",
                    "unexplained_loss_nonnegative",
                ],
                destination("loss_attribution_breakdown.png"),
                "Packets",
                "Loss Attribution Breakdown",
            )

    if write_legacy_outputs and os.path.exists(loss_attribution_v2_path):
        attribution_v2 = pd.read_csv(loss_attribution_v2_path)
        if len(attribution_v2):
            value_cols = [
                "physical_queue_drop_packets",
                "physical_phy_drop_packets",
                "udp_send_failed_packets",
                "routing_drop_packets",
                "ipv4_l3_drop_packets",
                "isl_queue_saturation_associated_loss",
                "gsl_queue_saturation_associated_loss",
                "mixed_queue_saturation_associated_loss",
                "tail_in_flight_possible_loss",
                "unclassified_unexplained_loss",
            ]
            for col in value_cols:
                if col not in attribution_v2.columns:
                    attribution_v2[col] = 0
            _stacked_bar(
                attribution_v2,
                "algorithm",
                value_cols,
                destination("loss_attribution_breakdown_v2.png"),
                "Packets",
                "Loss Attribution Breakdown v2 (Physical and Associated)",
            )

    if os.path.exists(loss_attribution_v3_path):
        attribution_v3 = pd.read_csv(loss_attribution_v3_path)
        if len(attribution_v3):
            value_cols = [
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
            for col in value_cols:
                if col not in attribution_v3.columns:
                    attribution_v3[col] = 0
            _stacked_bar(
                attribution_v3,
                "algorithm",
                value_cols,
                destination("loss_attribution_breakdown_v3.png"),
                "Packets",
                "Loss Attribution v3: Exact Drops and Time-aware Associations",
            )

            _stacked_bar(
                attribution_v3,
                "algorithm",
                [
                    "isl_saturation_associated_loss",
                    "gsl_saturation_associated_loss",
                    "mixed_saturation_associated_loss",
                ],
                destination("saturation_overlap_by_algorithm.png"),
                "Inferred associated packets",
                "Same-window Replay-path Saturation Overlap",
            )

    if os.path.exists(tag_coverage_path):
        tag_coverage = pd.read_csv(tag_coverage_path)
        algorithms = summary[["algorithm"]].drop_duplicates().sort_values("algorithm")
        if len(tag_coverage):
            coverage = (
                tag_coverage.groupby("algorithm")
                .agg(
                    trace_event_count=("drop_events_total", "sum"),
                    tagged_event_count=("drop_events_with_flow_tag", "sum"),
                )
                .reset_index()
            )
            coverage = algorithms.merge(coverage, on="algorithm", how="left").fillna(0)
        else:
            coverage = algorithms.copy()
            coverage["trace_event_count"] = 0
            coverage["tagged_event_count"] = 0
        labels = coverage["algorithm"].map(_short_label).tolist()
        x = list(range(len(coverage)))
        width = 0.38
        plt.figure(figsize=(9, 4.8))
        plt.bar(
            [value - width / 2 for value in x],
            coverage["trace_event_count"],
            width=width,
            label="Trace events",
            color="#4c78a8",
        )
        plt.bar(
            [value + width / 2 for value in x],
            coverage["tagged_event_count"],
            width=width,
            label="Tagged events",
            color="#f2cf5b",
        )
        for index, row in coverage.iterrows():
            total = int(row["trace_event_count"])
            tagged = int(row["tagged_event_count"])
            label = "N/A" if total == 0 else "%.1f%%" % (100.0 * tagged / total)
            plt.text(index, max(total, tagged) + 0.05, label, ha="center", fontsize=9)
        plt.xticks(x, labels, rotation=25, ha="right")
        plt.ylabel("Exact trace event count")
        plt.title(
            "UdpFlowTag Coverage (N/A when no trace events)"
            if int(coverage["trace_event_count"].sum())
            else "No exact physical drop trace events were recorded; tag coverage is N/A."
        )
        plt.legend()
        plt.tight_layout()
        plt.savefig(destination("tag_coverage_diagnostics.png"), dpi=180)
        plt.close()

    if os.path.exists(congested_interfaces_path):
        congested = pd.read_csv(congested_interfaces_path)
        if len(congested):
            by_link = (
                congested.pivot_table(
                    index="algorithm",
                    columns="link_type",
                    values="samples_at_capacity",
                    aggfunc="sum",
                    fill_value=0,
                )
                .reset_index()
            )
            for link_type in ["ISL", "GSL", "UNKNOWN"]:
                if link_type not in by_link.columns:
                    by_link[link_type] = 0
            _stacked_bar(
                by_link,
                "algorithm",
                ["ISL", "GSL", "UNKNOWN"],
                destination("queue_saturation_by_link_type.png"),
                "Queue samples at capacity",
                "Queue Saturation by Link Type",
            )

            top = congested.sort_values(
                ["samples_at_capacity", "max_queue_pkt"],
                ascending=[False, False],
            ).head(20).copy()
            top["interface"] = (
                top["algorithm"].map(_short_label)
                + " "
                + top["interface_key"].astype(str)
            )
            plt.figure(figsize=(11, 6))
            plt.barh(
                top["interface"][::-1],
                top["samples_at_capacity"][::-1].astype(float),
                color="#2a9d8f",
            )
            plt.xlabel("Samples at queue capacity")
            plt.title("Top Congested Interfaces")
            plt.tight_layout()
            plt.savefig(destination("top_congested_interfaces.png"), dpi=180)
            plt.close()

    if os.path.exists(queue_saturation_timeline_path):
        timeline = pd.read_csv(queue_saturation_timeline_path)
        if len(timeline):
            if os.path.exists(congested_interfaces_path):
                congested = pd.read_csv(congested_interfaces_path)
            else:
                congested = pd.DataFrame()
            if len(congested):
                top_keys = (
                    congested.sort_values(
                        ["samples_at_capacity", "max_queue_pkt"],
                        ascending=[False, False],
                    )
                    .head(8)[["algorithm", "interface_key"]]
                    .apply(lambda row: "%s|%s" % (row["algorithm"], row["interface_key"]), axis=1)
                    .tolist()
                )
            else:
                top_keys = (
                    timeline[timeline["is_at_capacity"].astype(str).str.lower() == "true"]
                    [["algorithm", "interface_key"]]
                    .drop_duplicates()
                    .head(8)
                    .apply(lambda row: "%s|%s" % (row["algorithm"], row["interface_key"]), axis=1)
                    .tolist()
                )
            if top_keys:
                timeline = timeline.copy()
                timeline["plot_key"] = timeline.apply(
                    lambda row: "%s|%s" % (row["algorithm"], row["interface_key"]),
                    axis=1,
                )
                plt.figure(figsize=(11, 5.8))
                for plot_key, group in timeline[timeline["plot_key"].isin(top_keys)].groupby("plot_key"):
                    algorithm, interface_key = plot_key.split("|", 1)
                    label = "%s %s" % (_short_label(algorithm), interface_key)
                    group = group.sort_values("time_ns")
                    plt.plot(
                        group["time_ns"].astype(float) / 1e9,
                        group["queue_pkt"].astype(float),
                        linewidth=1.7,
                        label=label,
                    )
                plt.xlabel("Simulation time (s)")
                plt.ylabel("Queue occupancy (packets)")
                plt.title("Queue Saturation Timeline")
                plt.grid(True, alpha=0.25)
                plt.legend(fontsize=8)
                plt.tight_layout()
                plt.savefig(destination("queue_saturation_timeline.png"), dpi=180)
                plt.close()

    if os.path.exists(corridor_concentration_path):
        concentration = pd.read_csv(corridor_concentration_path)
        if len(concentration):
            row = concentration.iloc[0]
            values = [
                float(row.get("target_corridor_max_load_ratio", 0.0)),
                float(row.get("top_non_focus_edge_load_ratio", 0.0)),
            ]
            labels = ["target max", "top non-focus"]
            plt.figure(figsize=(6.5, 4.2))
            plt.bar(labels, values, color=["#1b9e77", "#d95f02"])
            plt.ylabel("Estimated load / capacity")
            plt.title("Corridor Concentration")
            plt.tight_layout()
            plt.savefig(
                destination("corridor_concentration_summary.png"),
                dpi=180,
            )
            plt.close()

    if os.path.exists(satellite_interface_path):
        satellite_interface = pd.read_csv(satellite_interface_path)
        if len(satellite_interface):
            top = satellite_interface.sort_values(
                ["load_ratio", "satellite_id"],
                ascending=[False, True],
            ).head(12)
            labels = [
                "%s %s" % (int(row["satellite_id"]), row["direction"])
                for _, row in top.iterrows()
            ]
            plt.figure(figsize=(9, 4.8))
            plt.bar(labels, top["load_ratio"].astype(float), color="#4c78a8")
            plt.ylabel("Estimated load / GSL capacity")
            plt.xticks(rotation=30, ha="right")
            plt.title("Top Satellite Interface Proxy Load")
            plt.tight_layout()
            plt.savefig(
                destination("satellite_interface_load_summary.png"),
                dpi=180,
            )
            plt.close()

    if os.path.exists(fallback_phase_path):
        fallback = pd.read_csv(fallback_phase_path)
        if len(fallback):
            plt.figure(figsize=(9, 4.8))
            plt.bar(
                fallback["phase"],
                fallback["selected_count"].astype(float),
                color="#6c5b7b",
            )
            plt.ylabel("Selected background flows")
            plt.xticks(rotation=30, ha="right")
            plt.title("Flow Selection by Fallback Phase")
            plt.tight_layout()
            plt.savefig(
                destination("fallback_phase_summary.png"),
                dpi=180,
            )
            plt.close()

    plt.figure(figsize=(7.5, 5))
    for algorithm, group in per_flow.groupby("algorithm"):
        values = sorted(group["pdr"].astype(float).tolist())
        if not values:
            continue
        y = [(i + 1) / float(len(values)) for i in range(len(values))]
        plt.plot(values, y, label=_short_label(algorithm), linewidth=2)
    plt.xlabel("Per-flow PDR")
    plt.ylabel("CDF")
    plt.xlim(0, 1.01)
    plt.ylim(0, 1.01)
    plt.title(_timing_title("Per-flow PDR CDF", summary))
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(destination("per_flow_pdr_cdf.png"), dpi=180)
    plt.close()

    if os.path.exists(queue_path):
        queue = pd.read_csv(queue_path)
        if len(queue):
            top = queue.sort_values("packet_max", ascending=False).head(20).copy()
            top["link"] = top["algorithm"].map(_short_label) + " " + top["from"].astype(str) + "->" + top["to"].astype(str)
            plt.figure(figsize=(10, 6))
            plt.barh(top["link"][::-1], top["packet_max"][::-1], color="#d1495b")
            plt.xlabel("Max queue occupancy (packets)")
            plt.title("Max ISL Queue Occupancy Top Links")
            plt.tight_layout()
            plt.savefig(destination("max_queue_occupancy_top_links.png"), dpi=180)
            plt.close()
            if write_legacy_outputs:
                _write_deprecated_link_drop_heatmap_notice(
                    destination("link_drop_heatmap.png")
                )

    if os.path.exists(top_loss_path):
        top_loss = pd.read_csv(top_loss_path)
        if len(top_loss):
            top_loss = top_loss.sort_values("lost_packets", ascending=False).head(20).copy()
            top_loss["flow"] = (
                top_loss["algorithm"].map(_short_label)
                + " f"
                + top_loss["flow_id"].astype(str)
                + " "
                + top_loss["src"].astype(str)
                + "->"
                + top_loss["dst"].astype(str)
            )
            plt.figure(figsize=(10, 6))
            plt.barh(top_loss["flow"][::-1], top_loss["lost_packets"][::-1], color="#7a5195")
            plt.xlabel("Synthetic lost packets (sent - received)")
            plt.title("Top Loss Flows")
            plt.tight_layout()
            plt.savefig(destination("top_loss_flows.png"), dpi=180)
            plt.close()

    if os.path.exists(destination_path):
        destination_summary = pd.read_csv(destination_path)
        if len(destination_summary):
            lossy = destination_summary[
                destination_summary["total_lost_packets"] > 0
            ].copy()
            if len(lossy):
                lossy = lossy.sort_values("total_lost_packets", ascending=False).head(20)
                lossy["destination"] = (
                    lossy["algorithm"].map(_short_label)
                    + " dst="
                    + lossy["dst"].astype(str)
                )
                plt.figure(figsize=(10, 6))
                plt.barh(lossy["destination"][::-1], lossy["total_lost_packets"][::-1], color="#ef5675")
                plt.xlabel("Synthetic lost packets (sent - received)")
                plt.title("Destination Loss Summary")
                plt.tight_layout()
                plt.savefig(destination("destination_loss_summary.png"), dpi=180)
                plt.close()

            capacity = destination_summary[
                destination_summary["gsl_capacity_mbps"].notna()
                & (destination_summary["total_offered_rate_mbps"] > 0)
            ].copy()
            if len(capacity):
                capacity = capacity.sort_values(
                    ["offered_to_gsl_capacity_ratio", "total_lost_packets"],
                    ascending=False,
                ).head(20)
                capacity["destination"] = (
                    capacity["algorithm"].map(_short_label)
                    + " dst="
                    + capacity["dst"].astype(str)
                )
                labels = capacity["destination"].tolist()
                x = list(range(len(labels)))
                width = 0.38
                plt.figure(figsize=(11, 5.8))
                plt.bar(
                    [value - width / 2 for value in x],
                    capacity["total_offered_rate_mbps"],
                    width=width,
                    label="Offered",
                    color="#ffa600",
                )
                plt.bar(
                    [value + width / 2 for value in x],
                    capacity["gsl_capacity_mbps"],
                    width=width,
                    label="GSL capacity",
                    color="#2f4b7c",
                )
                plt.ylabel("Mbps")
                plt.xticks(x, labels, rotation=30, ha="right")
                plt.title("Destination Offered Rate vs GSL Capacity")
                plt.legend()
                plt.tight_layout()
                plt.savefig(
                    destination("destination_offered_rate_vs_gsl_capacity.png"),
                    dpi=180,
                )
            plt.close()

    if output_layout == "standard":
        write_output_manifest(comparison_dir)
    print("  > Wrote plots under %s" % comparison_dir)


def plot_across_loads(runs_root, run_names, focus_pair_tag=None):
    rows = []
    for run_name in run_names:
        summary_path = resolve_input_path(
            os.path.join(
                runs_root,
                run_name,
                "comparison_packet_delivery",
            ),
            "summary_by_algorithm.csv",
        )
        if os.path.exists(summary_path):
            rows.append(pd.read_csv(summary_path))
    if len(rows) <= 1:
        return
    df = pd.concat(rows, ignore_index=True)
    if df["load_level"].nunique() <= 1:
        return
    output_dir = os.path.join(runs_root, "comparison_packet_delivery_across_loads")
    if focus_pair_tag:
        output_dir = os.path.join(output_dir, focus_pair_tag)
    os.makedirs(output_dir, exist_ok=True)
    plt.figure(figsize=(8, 5))
    label_columns = ["algorithm"]
    if "background_flow_count" in df.columns and df["background_flow_count"].nunique() > 1:
        label_columns = ["algorithm", "background_flow_count"]
    for label_values, group in df.groupby(label_columns):
        if not isinstance(label_values, tuple):
            label_values = (label_values,)
        algorithm = label_values[0]
        bg_suffix = (
            " bg=%s" % label_values[1]
            if len(label_values) > 1
            else ""
        )
        group = group.sort_values("load_level")
        plt.plot(
            group["load_level"],
            group["aggregate_pdr"],
            marker="o",
            linewidth=2,
            label="%s%s" % (_short_label(algorithm), bg_suffix),
        )
    plt.xlabel("Offered load multiplier")
    plt.ylabel("Aggregate PDR")
    plt.ylim(0, 1.01)
    plt.title(_timing_title("Offered Load vs PDR", df))
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "offered_load_vs_pdr.png"), dpi=180)
    plt.close()
    print("  > Wrote cross-load plot under %s" % output_dir)


def plot_across_background_flow_counts(
    runs_root,
    run_names,
    focus_pair_tag=None,
):
    rows = []
    for run_name in run_names:
        summary_path = resolve_input_path(
            os.path.join(
                runs_root,
                run_name,
                "comparison_packet_delivery",
            ),
            "summary_by_algorithm.csv",
        )
        if os.path.exists(summary_path):
            rows.append(pd.read_csv(summary_path))
    if len(rows) <= 1:
        return
    df = pd.concat(rows, ignore_index=True)
    if "background_flow_count" not in df.columns or df["background_flow_count"].nunique() <= 1:
        return

    output_dir = os.path.join(
        runs_root,
        "comparison_packet_delivery_across_background_flow_counts",
    )
    if focus_pair_tag:
        output_dir = os.path.join(output_dir, focus_pair_tag)
    os.makedirs(output_dir, exist_ok=True)
    df.to_csv(
        os.path.join(output_dir, "summary_across_background_flow_counts.csv"),
        index=False,
    )

    metrics = [
        ("aggregate_pdr", "Aggregate PDR", "background_flow_count_vs_pdr.png"),
        ("total_lost_packets", "Lost packets", "background_flow_count_vs_loss.png"),
        ("total_sent_packets", "Sent packets", "background_flow_count_vs_sent_packets.png"),
        ("offered_rate_mbps", "Offered rate (Mbps)", "background_flow_count_vs_offered_rate.png"),
    ]
    for metric, ylabel, filename in metrics:
        if metric not in df.columns:
            continue
        plt.figure(figsize=(8, 5))
        group_columns = ["algorithm"]
        if df["load_level"].nunique() > 1:
            group_columns = ["load_level", "algorithm"]
        for label_values, group in df.groupby(group_columns):
            if not isinstance(label_values, tuple):
                label_values = (label_values,)
            if group_columns[0] == "load_level":
                load_level, algorithm = label_values
                label = "load %.3g %s" % (load_level, _short_label(algorithm))
            else:
                algorithm = label_values[0]
                label = _short_label(algorithm)
            group = group.sort_values("background_flow_count")
            plt.plot(
                group["background_flow_count"],
                group[metric],
                marker="o",
                linewidth=2,
                label=label,
            )
        plt.xlabel("Background flow count")
        plt.ylabel(ylabel)
        if metric == "aggregate_pdr":
            plt.ylim(0, 1.01)
        plt.title(ylabel + " vs Background Flow Count")
        plt.grid(True, alpha=0.25)
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, filename), dpi=180)
        plt.close()
    print("  > Wrote cross-background-flow-count plots under %s" % output_dir)


def main():
    parser = build_arg_parser("Plot UDP/PDR packet delivery comparison.")
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
    )
    run_names = []
    seen = set()
    focus_pair_tag = None
    for run in runs:
        run = resolve_existing_run(run)
        focus_pair_tag = run["focus_pair_tag"]
        if run["name"] in seen:
            continue
        seen.add(run["name"])
        run_names.append(run["name"])
        comparison_dir = os.path.join("runs", run["name"], "comparison_packet_delivery")
        plot_single_run(
            comparison_dir,
            output_layout=args.output_layout,
            write_legacy_outputs=args.write_legacy_outputs,
        )
    plot_across_loads("runs", run_names, focus_pair_tag)
    plot_across_background_flow_counts("runs", run_names, focus_pair_tag)


if __name__ == "__main__":
    main()
