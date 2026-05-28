import csv
import json
import math
import os
import sys
from itertools import combinations

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__)))
from dynamic_run_list import build_arg_parser, describe_selection, focus_dst_node_id, focus_src_node_id, get_udp_pdr_run_list


UDP_FLOW_COLUMNS = [
    "flow_id",
    "src",
    "dst",
    "start_time_ns",
    "end_time_ns",
    "sent_packets",
    "received_packets",
    "lost_packets",
    "sent_bytes",
    "received_bytes",
    "pdr",
    "offered_rate_mbps",
    "received_rate_mbps",
    "target_rate_mbps",
    "metadata",
    "flow_class",
]

AFFECTED_FLOW_COLUMNS = [
    "load_level",
    "algorithm",
    "flow_id",
    "src",
    "dst",
    "flow_class",
    "sent_packets",
    "received_packets",
    "lost_packets",
    "pdr",
    "loss_rate",
    "sent_bytes",
    "received_bytes",
    "offered_rate_mbps",
    "received_rate_mbps",
    "focus_flow",
    "destination_group_key",
]

DESTINATION_LOSS_COLUMNS = [
    "load_level",
    "algorithm",
    "dst",
    "flow_count",
    "background_flow_count",
    "focus_flow_count",
    "total_sent_packets",
    "total_received_packets",
    "total_lost_packets",
    "aggregate_pdr",
    "aggregate_loss_rate",
    "total_offered_rate_mbps",
    "total_received_rate_mbps",
    "gsl_capacity_mbps",
    "offered_to_gsl_capacity_ratio",
    "expected_capacity_limited_pdr",
    "observed_vs_capacity_limit_gap",
]

TOP_LOSS_FLOW_COUNT = 20
SYNTHETIC_LOSS_REASON = "udp_sent_minus_received"
MAX_QUEUE_SCOPE = "sampled/event-derived ISL net-device queue only"


def run_timing_fields(run):
    return {
        "simulation_end_time_s": run["simulation_end_time_s"],
        "traffic_stop_time_s": run["traffic_stop_time_s"],
        "drain_time_s": run["drain_time_s"],
        "simulation_end_time_ns": run["simulation_end_time_ns"],
        "traffic_stop_time_ns": run["traffic_stop_time_ns"],
        "drain_time_ns": run["drain_time_ns"],
        "drain_time_enabled": bool(run["drain_time_enabled"]),
    }


def parse_metadata(metadata):
    result = {}
    if not isinstance(metadata, str):
        return result
    for item in metadata.split("|"):
        if "=" in item:
            key, value = item.split("=", 1)
            result[key] = value
    return result


def format_bool(value):
    return "true" if bool(value) else "false"


def parse_config_properties(path):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path) as f_in:
        for line in f_in:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return values


def load_run_metadata(algorithm_run_dir):
    path = os.path.join(algorithm_run_dir, "run_metadata.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f_in:
        return json.load(f_in)


def to_float_or_none(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_gsl_capacity_mbps(algorithm_run_dir, run):
    config = parse_config_properties(os.path.join(algorithm_run_dir, "config_ns3.properties"))
    value = to_float_or_none(config.get("gsl_data_rate_megabit_per_s"))
    if value is not None:
        return value

    metadata = load_run_metadata(algorithm_run_dir)
    value = to_float_or_none(metadata.get("gsl_data_rate_megabit_per_s"))
    if value is not None:
        return value
    value = to_float_or_none(metadata.get("run", {}).get("gsl_data_rate_megabit_per_s"))
    if value is not None:
        return value

    return to_float_or_none(run.get("gsl_data_rate_megabit_per_s"))


def is_synthetic_sent_minus_received_drop_df(df):
    if df is None or len(df) == 0:
        return True
    if "drop_reason" not in df.columns:
        return False
    if not (df["drop_reason"].astype(str) == SYNTHETIC_LOSS_REASON).all():
        return False
    if "link_type" in df.columns and not (df["link_type"].astype(str) == "flow_summary").all():
        return False
    return True


def physical_drop_trace_available(algorithm_run_dir, drops_df):
    logs_dir = os.path.join(algorithm_run_dir, "logs_ns3")
    physical_path = os.path.join(logs_dir, "physical_link_drops.csv")
    if os.path.exists(physical_path):
        try:
            return len(pd.read_csv(physical_path)) > 0
        except pd.errors.EmptyDataError:
            return False
    return not is_synthetic_sent_minus_received_drop_df(drops_df)


def gsl_queue_tracking_available(algorithm_run_dir):
    logs_dir = os.path.join(algorithm_run_dir, "logs_ns3")
    for filename in [
        "gsl_queue_pkt.csv",
        "gsl_queue_byte.csv",
        "access_queue_pkt.csv",
        "access_queue_byte.csv",
    ]:
        if os.path.exists(os.path.join(logs_dir, filename)):
            return True
    return False


def read_udp_burst_csv(path, incoming=False):
    columns = [
        "flow_id",
        "src",
        "dst",
        "target_rate_mbps",
        "start_time_ns",
        "duration_ns",
        "rate_with_headers_mbps",
        "rate_payload_mbps",
        "packets",
        "bytes_with_headers",
        "bytes_payload",
        "metadata",
    ]
    rows = []
    with open(path, newline="") as f_in:
        reader = csv.reader(f_in)
        for row in reader:
            if not row:
                continue
            # Metadata is generated without commas, but keep this guard for older logs.
            if len(row) > 12:
                row = row[:11] + [",".join(row[11:])]
            rows.append(row)
    df = pd.DataFrame(rows, columns=columns)
    int_cols = [
        "flow_id",
        "src",
        "dst",
        "start_time_ns",
        "duration_ns",
        "packets",
        "bytes_with_headers",
        "bytes_payload",
    ]
    float_cols = ["target_rate_mbps", "rate_with_headers_mbps", "rate_payload_mbps"]
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
    for col in float_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    suffix = "_incoming" if incoming else "_outgoing"
    return df.rename(columns={col: col + suffix for col in [
        "rate_with_headers_mbps",
        "rate_payload_mbps",
        "packets",
        "bytes_with_headers",
        "bytes_payload",
    ]})


def build_udp_flows_csv(algorithm_run_dir):
    logs_dir = os.path.join(algorithm_run_dir, "logs_ns3")
    outgoing_path = os.path.join(logs_dir, "udp_bursts_outgoing.csv")
    incoming_path = os.path.join(logs_dir, "udp_bursts_incoming.csv")
    if not os.path.exists(outgoing_path):
        raise RuntimeError("Missing UDP outgoing summary: %s" % outgoing_path)
    if not os.path.exists(incoming_path):
        raise RuntimeError("Missing UDP incoming summary: %s" % incoming_path)

    outgoing = read_udp_burst_csv(outgoing_path, incoming=False)
    incoming = read_udp_burst_csv(incoming_path, incoming=True)
    merged = outgoing.merge(
        incoming[
            [
                "flow_id",
                "packets_incoming",
                "bytes_payload_incoming",
                "rate_payload_mbps_incoming",
            ]
        ],
        on="flow_id",
        how="left",
    ).fillna({
        "packets_incoming": 0,
        "bytes_payload_incoming": 0,
        "rate_payload_mbps_incoming": 0.0,
    })

    rows = []
    for _, row in merged.iterrows():
        sent_packets = int(row["packets_outgoing"])
        received_packets = int(row["packets_incoming"])
        lost_packets = max(sent_packets - received_packets, 0)
        pdr = float(received_packets) / float(sent_packets) if sent_packets > 0 else 0.0
        metadata = row["metadata"]
        metadata_map = parse_metadata(metadata)
        flow_class = metadata_map.get("class", "")
        if not flow_class:
            pair = (int(row["src"]), int(row["dst"]))
            flow_class = "focus" if pair in {
                (focus_src_node_id, focus_dst_node_id),
                (focus_dst_node_id, focus_src_node_id),
            } else "background"
        rows.append({
            "flow_id": int(row["flow_id"]),
            "src": int(row["src"]),
            "dst": int(row["dst"]),
            "start_time_ns": int(row["start_time_ns"]),
            "end_time_ns": int(row["start_time_ns"] + row["duration_ns"]),
            "sent_packets": sent_packets,
            "received_packets": received_packets,
            "lost_packets": lost_packets,
            "sent_bytes": int(row["bytes_payload_outgoing"]),
            "received_bytes": int(row["bytes_payload_incoming"]),
            "pdr": pdr,
            "offered_rate_mbps": float(row["rate_payload_mbps_outgoing"]),
            "received_rate_mbps": float(row["rate_payload_mbps_incoming"]),
            "target_rate_mbps": float(row["target_rate_mbps"]),
            "metadata": metadata,
            "flow_class": flow_class,
        })

    df = pd.DataFrame(rows, columns=UDP_FLOW_COLUMNS)
    output_path = os.path.join(logs_dir, "udp_flows.csv")
    df.to_csv(output_path, index=False)
    return df, output_path


def jain_fairness(values):
    values = [float(v) for v in values if not math.isnan(float(v))]
    if not values:
        return 0.0
    numerator = sum(values) ** 2
    denominator = len(values) * sum(v * v for v in values)
    return numerator / denominator if denominator > 0 else 0.0


def summarize_algorithm(run, algorithm, flows):
    focus = flows[flows["flow_class"] == "focus"]
    total_sent_packets = int(flows["sent_packets"].sum())
    total_received_packets = int(flows["received_packets"].sum())
    total_lost_packets = int(flows["lost_packets"].sum())
    total_sent_bytes = int(flows["sent_bytes"].sum())
    total_received_bytes = int(flows["received_bytes"].sum())
    aggregate_pdr = (
        total_received_packets / float(total_sent_packets)
        if total_sent_packets > 0
        else 0.0
    )
    focus_sent = int(focus["sent_packets"].sum()) if len(focus) else 0
    focus_received = int(focus["received_packets"].sum()) if len(focus) else 0
    focus_pdr = focus_received / float(focus_sent) if focus_sent > 0 else 0.0
    pdr_values = flows["pdr"]
    summary = {
        "run_name": run["name"],
        "traffic_mode": run["traffic_mode"],
        "load_level": run["load_level"],
        "algorithm": algorithm,
    }
    summary.update(run_timing_fields(run))
    summary.update({
        "flow_count": int(len(flows)),
        "focus_flow_count": int(len(focus)),
        "total_sent_packets": total_sent_packets,
        "total_received_packets": total_received_packets,
        "total_lost_packets": total_lost_packets,
        "aggregate_pdr": aggregate_pdr,
        "aggregate_loss_rate": 1.0 - aggregate_pdr,
        "focus_flow_pdr": focus_pdr,
        "total_sent_bytes": total_sent_bytes,
        "total_received_bytes": total_received_bytes,
        "offered_rate_mbps": float(flows["offered_rate_mbps"].sum()),
        "received_rate_mbps": float(flows["received_rate_mbps"].sum()),
        "mean_flow_pdr": float(pdr_values.mean()) if len(pdr_values) else 0.0,
        "median_flow_pdr": float(pdr_values.median()) if len(pdr_values) else 0.0,
        "p5_flow_pdr": float(pdr_values.quantile(0.05)) if len(pdr_values) else 0.0,
        "min_flow_pdr": float(pdr_values.min()) if len(pdr_values) else 0.0,
        "failed_flow_count": int((flows["received_packets"] == 0).sum()),
        "pdr_lt_0_9_count": int((flows["pdr"] < 0.9).sum()),
        "pdr_lt_0_5_count": int((flows["pdr"] < 0.5).sum()),
        "jain_fairness": jain_fairness(flows["received_rate_mbps"].tolist()),
    })
    return summary


def write_synthetic_link_drops(algorithm_run_dir, algorithm, flows):
    logs_dir = os.path.join(algorithm_run_dir, "logs_ns3")
    output_path = os.path.join(logs_dir, "link_drops.csv")
    if os.path.exists(output_path):
        try:
            existing = pd.read_csv(output_path)
        except pd.errors.EmptyDataError:
            existing = pd.DataFrame()
        if not is_synthetic_sent_minus_received_drop_df(existing):
            return output_path
    columns = [
        "time_ns",
        "link_type",
        "from_node",
        "to_node",
        "queue_type",
        "drop_reason",
        "packet_size_bytes",
        "flow_id_if_available",
        "queue_occupancy_pkt_if_available",
        "queue_occupancy_byte_if_available",
        "drop_count",
    ]
    rows = []
    for _, row in flows.iterrows():
        if int(row["lost_packets"]) <= 0:
            continue
        rows.append({
            "time_ns": int(row["end_time_ns"]),
            "link_type": "flow_summary",
            "from_node": int(row["src"]),
            "to_node": int(row["dst"]),
            "queue_type": "unknown",
            "drop_reason": "udp_sent_minus_received",
            "packet_size_bytes": 1472,
            "flow_id_if_available": int(row["flow_id"]),
            "queue_occupancy_pkt_if_available": "",
            "queue_occupancy_byte_if_available": "",
            "drop_count": int(row["lost_packets"]),
        })
    pd.DataFrame(rows, columns=columns).to_csv(output_path, index=False)
    return output_path


def collect_queue_summary(algorithm_run_dir, run_name, algorithm):
    queue_dir = os.path.join(algorithm_run_dir, "queue_stats")
    rows = []
    if os.path.isdir(queue_dir):
        for filename in sorted(os.listdir(queue_dir)):
            if not filename.startswith("queue_stats_") or not filename.endswith(".csv"):
                continue
            time_ns = int(filename[len("queue_stats_"):-len(".csv")])
            path = os.path.join(queue_dir, filename)
            df = pd.read_csv(path)
            for _, row in df.iterrows():
                rows.append({
                    "run_name": run_name,
                    "algorithm": algorithm,
                    "from": int(row["from"]),
                    "to": int(row["to"]),
                    "time_ns": time_ns,
                    "packet_max": int(row["packet_max"]),
                })
    if not rows:
        return pd.DataFrame(columns=["run_name", "algorithm", "from", "to", "time_ns", "packet_max"])
    df = pd.DataFrame(rows)
    return (
        df.groupby(["run_name", "algorithm", "from", "to"])["packet_max"]
        .max()
        .reset_index()
        .sort_values(["algorithm", "packet_max"], ascending=[True, False])
    )


def build_pairwise(summary_df, per_flow_df):
    rows = []
    summaries = {row["algorithm"]: row for _, row in summary_df.iterrows()}
    for algorithm_a, algorithm_b in combinations(sorted(summaries.keys()), 2):
        a = summaries[algorithm_a]
        b = summaries[algorithm_b]
        flows_a = per_flow_df[per_flow_df["algorithm"] == algorithm_a].set_index("flow_id")
        flows_b = per_flow_df[per_flow_df["algorithm"] == algorithm_b].set_index("flow_id")
        shared = sorted(set(flows_a.index) & set(flows_b.index))
        diffs = flows_a.loc[shared]["pdr"] - flows_b.loc[shared]["pdr"] if shared else pd.Series(dtype=float)
        rows.append({
            "algorithm_a": algorithm_a,
            "algorithm_b": algorithm_b,
            "aggregate_pdr_diff": float(a["aggregate_pdr"] - b["aggregate_pdr"]),
            "focus_flow_pdr_diff": float(a["focus_flow_pdr"] - b["focus_flow_pdr"]),
            "flows_a_better": int((diffs > 0).sum()) if len(diffs) else 0,
            "flows_a_worse": int((diffs < 0).sum()) if len(diffs) else 0,
            "mean_per_flow_pdr_diff": float(diffs.mean()) if len(diffs) else 0.0,
            "p5_flow_pdr_diff": float(a["p5_flow_pdr"] - b["p5_flow_pdr"]),
            "failed_flow_reduction": int(b["failed_flow_count"] - a["failed_flow_count"]),
        })
    return pd.DataFrame(rows)


def add_flow_diagnostic_columns(flows):
    flows = flows.copy()
    flows["loss_rate"] = 0.0
    sent_mask = flows["sent_packets"].astype(float) > 0
    flows.loc[sent_mask, "loss_rate"] = (
        flows.loc[sent_mask, "lost_packets"].astype(float)
        / flows.loc[sent_mask, "sent_packets"].astype(float)
    )
    flows["focus_flow"] = flows["flow_class"] == "focus"
    flows["destination_group_key"] = "dst=" + flows["dst"].astype(str)
    return flows


def build_affected_flows(per_flow_df):
    columns = [col for col in AFFECTED_FLOW_COLUMNS if col in per_flow_df.columns]
    affected = per_flow_df[per_flow_df["lost_packets"] > 0].copy()
    if len(affected) == 0:
        return pd.DataFrame(columns=columns)
    return (
        affected.sort_values(["load_level", "algorithm", "flow_id"])
        .reset_index(drop=True)[columns]
    )


def build_top_loss_flows(affected_df, top_k=TOP_LOSS_FLOW_COUNT):
    if len(affected_df) == 0:
        return affected_df.copy()
    return (
        affected_df.sort_values(
            ["lost_packets", "loss_rate", "algorithm", "flow_id"],
            ascending=[False, False, True, True],
        )
        .head(top_k)
        .reset_index(drop=True)
    )


def build_destination_loss_summary(per_flow_df, gsl_capacity_by_algorithm):
    rows = []
    for (load_level, algorithm, dst), group in per_flow_df.groupby(["load_level", "algorithm", "dst"]):
        total_sent_packets = int(group["sent_packets"].sum())
        total_received_packets = int(group["received_packets"].sum())
        total_lost_packets = int(group["lost_packets"].sum())
        offered_rate_column = "target_rate_mbps" if "target_rate_mbps" in group.columns else "offered_rate_mbps"
        total_offered_rate_mbps = float(group[offered_rate_column].sum())
        total_received_rate_mbps = float(group["received_rate_mbps"].sum())
        aggregate_pdr = (
            total_received_packets / float(total_sent_packets)
            if total_sent_packets > 0
            else 0.0
        )
        aggregate_loss_rate = 1.0 - aggregate_pdr
        gsl_capacity_mbps = gsl_capacity_by_algorithm.get(algorithm)
        if gsl_capacity_mbps is not None and gsl_capacity_mbps > 0:
            offered_to_capacity = total_offered_rate_mbps / gsl_capacity_mbps
            expected_capacity_limited_pdr = (
                min(1.0, gsl_capacity_mbps / total_offered_rate_mbps)
                if total_offered_rate_mbps > 0
                else 1.0
            )
            observed_gap = aggregate_pdr - expected_capacity_limited_pdr
        else:
            gsl_capacity_mbps = math.nan
            offered_to_capacity = math.nan
            expected_capacity_limited_pdr = math.nan
            observed_gap = math.nan
        rows.append({
            "load_level": load_level,
            "algorithm": algorithm,
            "dst": int(dst),
            "flow_count": int(len(group)),
            "background_flow_count": int((group["flow_class"] == "background").sum()),
            "focus_flow_count": int((group["flow_class"] == "focus").sum()),
            "total_sent_packets": total_sent_packets,
            "total_received_packets": total_received_packets,
            "total_lost_packets": total_lost_packets,
            "aggregate_pdr": aggregate_pdr,
            "aggregate_loss_rate": aggregate_loss_rate,
            "total_offered_rate_mbps": total_offered_rate_mbps,
            "total_received_rate_mbps": total_received_rate_mbps,
            "gsl_capacity_mbps": gsl_capacity_mbps,
            "offered_to_gsl_capacity_ratio": offered_to_capacity,
            "expected_capacity_limited_pdr": expected_capacity_limited_pdr,
            "observed_vs_capacity_limit_gap": observed_gap,
        })
    if not rows:
        return pd.DataFrame(columns=DESTINATION_LOSS_COLUMNS)
    return (
        pd.DataFrame(rows, columns=DESTINATION_LOSS_COLUMNS)
        .sort_values(["load_level", "algorithm", "dst"])
        .reset_index(drop=True)
    )


def write_loss_diagnostics(
    path,
    run,
    summary_df,
    focus_df,
    affected_df,
    destination_df,
    queue_df,
    physical_trace_available,
    gsl_queue_available,
    gsl_capacity_warnings,
):
    loss_attribution = (
        "physical_drop_trace"
        if physical_trace_available
        else "synthetic_sent_minus_received"
    )
    with open(path, "w") as f_out:
        f_out.write("UDP/PDR Loss Attribution Diagnostics\n")
        f_out.write("=" * 40 + "\n\n")

        f_out.write("Attribution availability\n")
        f_out.write("-" * 40 + "\n")
        f_out.write(
            "physical_drop_trace_available = %s\n"
            % format_bool(physical_trace_available)
        )
        f_out.write("loss_attribution = %s\n" % loss_attribution)
        f_out.write("max_queue_scope = %s\n" % MAX_QUEUE_SCOPE)
        f_out.write(
            "gsl_queue_tracking_available = %s\n\n"
            % format_bool(gsl_queue_available)
        )

        f_out.write("Key observations\n")
        f_out.write("-" * 40 + "\n")
        if len(affected_df):
            total_lost = int(affected_df["lost_packets"].sum())
            f_out.write(
                "Synthetic sent-minus-received loss appears in %d flow rows, "
                "for %d packets total.\n"
                % (len(affected_df), total_lost)
            )
            top_flow = affected_df.sort_values("lost_packets", ascending=False).iloc[0]
            f_out.write(
                "Top loss flow: load=%s algorithm=%s flow_id=%s src=%s dst=%s "
                "class=%s lost_packets=%s pdr=%.6f.\n"
                % (
                    top_flow["load_level"],
                    top_flow["algorithm"],
                    top_flow["flow_id"],
                    top_flow["src"],
                    top_flow["dst"],
                    top_flow["flow_class"],
                    top_flow["lost_packets"],
                    float(top_flow["pdr"]),
                )
            )
        else:
            f_out.write("No synthetic sent-minus-received flow loss observed.\n")

        if len(focus_df):
            focus_pdr_min = float(focus_df["pdr"].min())
            focus_loss = int(focus_df["lost_packets"].sum())
            f_out.write(
                "Focus-flow minimum PDR is %.6f, with %d focus-flow lost packets.\n"
                % (focus_pdr_min, focus_loss)
            )
            adaptive_focus = focus_df[
                focus_df["algorithm"] != "algorithm_free_one_only_over_isls"
            ]
            if len(adaptive_focus):
                f_out.write(
                    "Non-baseline focus-flow minimum PDR is %.6f, with %d non-baseline focus-flow lost packets.\n"
                    % (
                        float(adaptive_focus["pdr"].min()),
                        int(adaptive_focus["lost_packets"].sum()),
                    )
                )

        adaptive_affected = affected_df[
            affected_df["algorithm"] != "algorithm_free_one_only_over_isls"
        ]
        if len(adaptive_affected):
            adaptive_destinations = sorted(set(adaptive_affected["dst"].astype(int).tolist()))
            adaptive_classes = sorted(set(adaptive_affected["flow_class"].astype(str).tolist()))
            f_out.write(
                "Non-baseline affected flows are in classes=%s and destinations=%s.\n"
                % (
                    ",".join(adaptive_classes),
                    ",".join(str(value) for value in adaptive_destinations),
                )
            )

        lossy_destinations = destination_df[destination_df["total_lost_packets"] > 0]
        if len(lossy_destinations):
            f_out.write("Top destination aggregates by synthetic loss:\n")
            top_destinations = lossy_destinations.sort_values(
                "total_lost_packets", ascending=False
            ).head(8)
            for _, row in top_destinations.iterrows():
                f_out.write(
                    "  load=%s algorithm=%s dst=%d flows=%d lost=%d "
                    "offered=%.6f Mbps received=%.6f Mbps gsl_capacity=%s "
                    "expected_capacity_limited_pdr=%s observed_pdr=%.6f\n"
                    % (
                        row["load_level"],
                        row["algorithm"],
                        int(row["dst"]),
                        int(row["flow_count"]),
                        int(row["total_lost_packets"]),
                        float(row["total_offered_rate_mbps"]),
                        float(row["total_received_rate_mbps"]),
                        (
                            "%.6f" % float(row["gsl_capacity_mbps"])
                            if not math.isnan(float(row["gsl_capacity_mbps"]))
                            else ""
                        ),
                        (
                            "%.6f" % float(row["expected_capacity_limited_pdr"])
                            if not math.isnan(float(row["expected_capacity_limited_pdr"]))
                            else ""
                        ),
                        float(row["aggregate_pdr"]),
                    )
                )

        overloaded = destination_df[
            destination_df["offered_to_gsl_capacity_ratio"].notna()
            & (destination_df["offered_to_gsl_capacity_ratio"] > 1.0)
        ]
        if len(overloaded):
            f_out.write(
                "Destinations with aggregate offered rate above configured GSL capacity "
                "can indicate an access-side/GSL bottleneck or another untracked queue/device layer.\n"
            )
        if len(queue_df):
            f_out.write(
                "The max-queue heatmap is based on sampled/event-derived ISL queue occupancy. "
                "It is not a physical packet-drop heatmap.\n"
            )
            f_out.write(
                "Use max_queue_occupancy_top_links.png for this plot; "
                "the legacy name link_drop_heatmap.png is deprecated if present.\n"
            )
        f_out.write("\n")

        f_out.write("Warnings\n")
        f_out.write("-" * 40 + "\n")
        f_out.write(
            "The synthetic sent-minus-received loss should not be interpreted as a physical per-link drop trace.\n"
        )
        f_out.write(
            "The max queue occupancy summary only covers tracked ISL queues and may not include GSL/access queues or device-level drop events.\n"
        )
        if gsl_capacity_warnings:
            for warning in gsl_capacity_warnings:
                f_out.write("WARNING: %s\n" % warning)
        f_out.write("\n")

        f_out.write("Recommended next steps\n")
        f_out.write("-" * 40 + "\n")
        f_out.write(
            "Enable GSL queue tracking and/or physical drop tracing to confirm access-side bottleneck attribution.\n"
        )
        f_out.write(
            "Consider UDP SendTo error logging, no-route/forwarding drop tracing, and FlowMonitor only as follow-up instrumentation work.\n"
        )


def write_statistics(
    path,
    run,
    summary_df,
    focus_df,
    pairwise_df,
    queue_df,
    physical_trace_available,
    gsl_queue_available,
):
    loss_attribution = (
        "physical_drop_trace"
        if physical_trace_available
        else "synthetic_sent_minus_received"
    )
    with open(path, "w") as f_out:
        f_out.write("UDP/PDR Packet Delivery Statistics\n")
        f_out.write("=" * 40 + "\n\n")

        f_out.write("Run timing\n")
        f_out.write("-" * 40 + "\n")
        f_out.write(
            "Simulation end time: %.6f s (%d ns)\n"
            % (run["simulation_end_time_s"], run["simulation_end_time_ns"])
        )
        f_out.write(
            "Traffic stop time: %.6f s (%d ns)\n"
            % (run["traffic_stop_time_s"], run["traffic_stop_time_ns"])
        )
        f_out.write(
            "Drain time: %.6f s (%d ns)\n"
            % (run["drain_time_s"], run["drain_time_ns"])
        )
        f_out.write(
            "drain_time_enabled = %s\n"
            % ("true" if run["drain_time_enabled"] else "false")
        )
        f_out.write(
            "PDR definition: packets received by simulation end divided by "
            "packets sent during the active traffic interval.\n\n"
        )

        f_out.write("Attribution diagnostics\n")
        f_out.write("-" * 40 + "\n")
        f_out.write(
            "physical_drop_trace_available = %s\n"
            % format_bool(physical_trace_available)
        )
        f_out.write("loss_attribution = %s\n" % loss_attribution)
        f_out.write("max_queue_scope = sampled/event-derived ISL queue\n")
        f_out.write(
            "gsl_queue_tracking_available = %s\n"
            % format_bool(gsl_queue_available)
        )
        f_out.write(
            "PDR is an end-to-end delivery metric. Queue occupancy and "
            "utilization logs provide supporting congestion evidence, but "
            "packet loss is not attributed to physical link drops unless "
            "physical drop tracing is enabled.\n"
        )
        f_out.write(
            "The max-queue heatmap is based on sampled/event-derived ISL "
            "queue occupancy. It is not a physical packet-drop heatmap.\n"
        )
        f_out.write(
            "Use max_queue_occupancy_top_links.png for this plot; "
            "the legacy name link_drop_heatmap.png is deprecated if present.\n\n"
        )

        f_out.write("Per algorithm summary\n")
        f_out.write("-" * 40 + "\n")
        for _, row in summary_df.iterrows():
            f_out.write("algorithm: %s\n" % row["algorithm"])
            for key in [
                "flow_count",
                "simulation_end_time_s",
                "traffic_stop_time_s",
                "drain_time_s",
                "drain_time_enabled",
                "total_sent_packets",
                "total_received_packets",
                "total_lost_packets",
                "aggregate_pdr",
                "aggregate_loss_rate",
                "focus_flow_pdr",
                "total_sent_bytes",
                "total_received_bytes",
                "offered_rate_mbps",
                "received_rate_mbps",
                "mean_flow_pdr",
                "median_flow_pdr",
                "p5_flow_pdr",
                "min_flow_pdr",
                "failed_flow_count",
                "pdr_lt_0_9_count",
                "pdr_lt_0_5_count",
                "jain_fairness",
            ]:
                f_out.write("  %s: %s\n" % (key, row[key]))
            f_out.write("\n")

        f_out.write("Focus flow summary\n")
        f_out.write("-" * 40 + "\n")
        if len(focus_df):
            f_out.write(focus_df.to_string(index=False))
        f_out.write("\n\n")

        f_out.write("Pairwise comparison\n")
        f_out.write("-" * 40 + "\n")
        if len(pairwise_df):
            f_out.write(pairwise_df.to_string(index=False))
        f_out.write("\n\n")

        f_out.write("Top congested ISL links by max queue occupancy\n")
        f_out.write("-" * 40 + "\n")
        if len(queue_df):
            f_out.write(queue_df.head(20).to_string(index=False))
        else:
            f_out.write("No queue summary available yet.")
        f_out.write("\n")


def analyze_run(run, algorithms):
    comparison_dir = os.path.join("runs", run["name"], "comparison_packet_delivery")
    os.makedirs(comparison_dir, exist_ok=True)

    per_flow_frames = []
    summary_rows = []
    focus_rows = []
    link_drop_frames = []
    queue_frames = []
    gsl_capacity_by_algorithm = {}
    gsl_capacity_warnings = []
    physical_trace_available_any = False
    gsl_queue_available_any = False

    for algorithm in algorithms:
        algorithm_run_dir = os.path.join("runs", run["name"], algorithm)
        if not os.path.isdir(algorithm_run_dir):
            print("Skipping missing run directory: %s" % algorithm_run_dir)
            continue
        print("Processing %s" % algorithm_run_dir)

        gsl_capacity_mbps = read_gsl_capacity_mbps(algorithm_run_dir, run)
        gsl_capacity_by_algorithm[algorithm] = gsl_capacity_mbps
        if gsl_capacity_mbps is None:
            gsl_capacity_warnings.append(
                "Could not read gsl_data_rate_megabit_per_s for %s" % algorithm
            )
        gsl_queue_available_any = (
            gsl_queue_available_any or gsl_queue_tracking_available(algorithm_run_dir)
        )

        flows, udp_flows_path = build_udp_flows_csv(algorithm_run_dir)
        print("  > Wrote %s" % udp_flows_path)

        flows.insert(0, "algorithm", algorithm)
        flows.insert(0, "load_level", run["load_level"])
        flows.insert(0, "traffic_mode", run["traffic_mode"])
        flows.insert(0, "run_name", run["name"])
        for key, value in run_timing_fields(run).items():
            flows[key] = value
        flows = add_flow_diagnostic_columns(flows)
        per_flow_frames.append(flows)

        summary_rows.append(summarize_algorithm(run, algorithm, flows))

        focus = flows[flows["flow_class"] == "focus"].copy()
        if len(focus):
            focus_rows.append(focus[[
                "run_name",
                "algorithm",
                "flow_id",
                "simulation_end_time_s",
                "traffic_stop_time_s",
                "drain_time_s",
                "drain_time_enabled",
                "src",
                "dst",
                "sent_packets",
                "received_packets",
                "lost_packets",
                "pdr",
                "sent_bytes",
                "received_bytes",
                "offered_rate_mbps",
                "received_rate_mbps",
            ]])

        link_drops_path = write_synthetic_link_drops(algorithm_run_dir, algorithm, flows)
        drops = pd.read_csv(link_drops_path)
        physical_trace_available_any = (
            physical_trace_available_any
            or physical_drop_trace_available(algorithm_run_dir, drops)
        )
        if len(drops):
            drops.insert(0, "algorithm", algorithm)
            drops.insert(0, "run_name", run["name"])
            link_drop_frames.append(drops)

        queue_frames.append(collect_queue_summary(algorithm_run_dir, run["name"], algorithm))

    if not per_flow_frames:
        raise RuntimeError("No UDP flow summaries found for run %s" % run["name"])

    per_flow_df = pd.concat(per_flow_frames, ignore_index=True)
    summary_df = pd.DataFrame(summary_rows)
    focus_df = pd.concat(focus_rows, ignore_index=True) if focus_rows else pd.DataFrame()
    link_drops_df = pd.concat(link_drop_frames, ignore_index=True) if link_drop_frames else pd.DataFrame()
    queue_df = pd.concat(queue_frames, ignore_index=True) if queue_frames else pd.DataFrame()
    pairwise_df = build_pairwise(summary_df, per_flow_df)
    affected_df = build_affected_flows(per_flow_df)
    top_loss_df = build_top_loss_flows(affected_df)
    destination_df = build_destination_loss_summary(
        per_flow_df,
        gsl_capacity_by_algorithm,
    )

    per_flow_df.to_csv(os.path.join(comparison_dir, "per_flow_delivery.csv"), index=False)
    summary_df.to_csv(os.path.join(comparison_dir, "summary_by_algorithm.csv"), index=False)
    focus_df.to_csv(os.path.join(comparison_dir, "focus_flow_delivery.csv"), index=False)
    pairwise_df.to_csv(os.path.join(comparison_dir, "pairwise_algorithm_comparison.csv"), index=False)
    affected_df.to_csv(os.path.join(comparison_dir, "affected_flows.csv"), index=False)
    top_loss_df.to_csv(os.path.join(comparison_dir, "top_loss_flows.csv"), index=False)
    destination_df.to_csv(os.path.join(comparison_dir, "destination_loss_summary.csv"), index=False)
    link_drops_df.to_csv(os.path.join(comparison_dir, "link_drops.csv"), index=False)
    if not physical_trace_available_any:
        link_drops_df.to_csv(os.path.join(comparison_dir, "synthetic_link_drops.csv"), index=False)
    queue_df.to_csv(os.path.join(comparison_dir, "max_queue_occupancy_by_algorithm.csv"), index=False)
    write_statistics(
        os.path.join(comparison_dir, "statistics.txt"),
        run,
        summary_df,
        focus_df,
        pairwise_df,
        queue_df,
        physical_trace_available_any,
        gsl_queue_available_any,
    )
    write_loss_diagnostics(
        os.path.join(comparison_dir, "loss_diagnostics.txt"),
        run,
        summary_df,
        focus_df,
        affected_df,
        destination_df,
        queue_df,
        physical_trace_available_any,
        gsl_queue_available_any,
        gsl_capacity_warnings,
    )
    print("  > Wrote comparison outputs under %s" % comparison_dir)
    return comparison_dir


def main():
    parser = build_arg_parser("Analyze UDP/PDR packet delivery results.")
    args = parser.parse_args()
    selected_mode, modes, load_levels, algorithms = describe_selection(args)
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

    seen_run_names = set()
    for run in runs:
        if run["name"] in seen_run_names:
            continue
        seen_run_names.add(run["name"])
        analyze_run(run, algorithms)


if __name__ == "__main__":
    main()
