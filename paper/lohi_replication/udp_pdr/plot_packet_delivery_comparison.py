import os
import sys

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-udp-pdr")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__)))
from dynamic_run_list import build_arg_parser, describe_selection, get_udp_pdr_run_list


def _short_label(label):
    return label.replace("algorithm_", "").replace("_over_isls", "")


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


def _timing_title(base_title, df):
    if "traffic_stop_time_s" not in df.columns or "drain_time_s" not in df.columns or len(df) == 0:
        return base_title
    traffic_stop_time_s = float(df["traffic_stop_time_s"].iloc[0])
    drain_time_s = float(df["drain_time_s"].iloc[0])
    return "%s (stop %.3gs, drain %.3gs)" % (base_title, traffic_stop_time_s, drain_time_s)


def _write_deprecated_link_drop_heatmap_notice(comparison_dir):
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
    plt.savefig(os.path.join(comparison_dir, "link_drop_heatmap.png"), dpi=180)
    plt.close()


def plot_single_run(comparison_dir):
    summary_path = os.path.join(comparison_dir, "summary_by_algorithm.csv")
    per_flow_path = os.path.join(comparison_dir, "per_flow_delivery.csv")
    queue_path = os.path.join(comparison_dir, "max_queue_occupancy_by_algorithm.csv")
    top_loss_path = os.path.join(comparison_dir, "top_loss_flows.csv")
    destination_path = os.path.join(comparison_dir, "destination_loss_summary.csv")
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
        os.path.join(comparison_dir, "aggregate_pdr.png"),
        "Aggregate PDR",
        _timing_title("Aggregate PDR", summary),
    )
    _bar_plot(
        summary,
        "algorithm",
        "focus_flow_pdr",
        os.path.join(comparison_dir, "focus_flow_pdr.png"),
        "Focus-flow PDR",
        _timing_title("Focus-flow PDR", summary),
    )
    _bar_plot(
        summary,
        "algorithm",
        "total_lost_packets",
        os.path.join(comparison_dir, "packet_loss_count_by_algorithm.png"),
        "Lost packets",
        _timing_title("Synthetic Sent-minus-Received Loss", summary),
    )
    _bar_plot(
        summary,
        "algorithm",
        "failed_flow_count",
        os.path.join(comparison_dir, "failed_flow_count.png"),
        "Failed flow count",
        _timing_title("Failed Flow Count", summary),
    )

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
    plt.savefig(os.path.join(comparison_dir, "per_flow_pdr_cdf.png"), dpi=180)
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
            plt.savefig(os.path.join(comparison_dir, "max_queue_occupancy_top_links.png"), dpi=180)
            plt.close()
            _write_deprecated_link_drop_heatmap_notice(comparison_dir)

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
            plt.savefig(os.path.join(comparison_dir, "top_loss_flows.png"), dpi=180)
            plt.close()

    if os.path.exists(destination_path):
        destination = pd.read_csv(destination_path)
        if len(destination):
            lossy = destination[destination["total_lost_packets"] > 0].copy()
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
                plt.savefig(os.path.join(comparison_dir, "destination_loss_summary.png"), dpi=180)
                plt.close()

            capacity = destination[
                destination["gsl_capacity_mbps"].notna()
                & (destination["total_offered_rate_mbps"] > 0)
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
                    os.path.join(comparison_dir, "destination_offered_rate_vs_gsl_capacity.png"),
                    dpi=180,
                )
            plt.close()

    print("  > Wrote plots under %s" % comparison_dir)


def plot_across_loads(runs_root, run_names):
    rows = []
    for run_name in run_names:
        summary_path = os.path.join(
            runs_root,
            run_name,
            "comparison_packet_delivery",
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
    os.makedirs(output_dir, exist_ok=True)
    plt.figure(figsize=(8, 5))
    for algorithm, group in df.groupby("algorithm"):
        group = group.sort_values("load_level")
        plt.plot(
            group["load_level"],
            group["aggregate_pdr"],
            marker="o",
            linewidth=2,
            label=_short_label(algorithm),
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


def main():
    parser = build_arg_parser("Plot UDP/PDR packet delivery comparison.")
    args = parser.parse_args()
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
    )
    run_names = []
    seen = set()
    for run in runs:
        if run["name"] in seen:
            continue
        seen.add(run["name"])
        run_names.append(run["name"])
        comparison_dir = os.path.join("runs", run["name"], "comparison_packet_delivery")
        plot_single_run(comparison_dir)
    plot_across_loads("runs", run_names)


if __name__ == "__main__":
    main()
