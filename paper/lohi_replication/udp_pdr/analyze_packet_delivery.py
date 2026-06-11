import csv
import json
import math
import os
import sys
from itertools import combinations

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__)))
from dynamic_run_list import (
    build_arg_parser,
    describe_selection,
    get_udp_pdr_run_list,
    resolve_existing_run,
    validate_focus_pair_arguments,
)
from loss_attribution_v3 import (
    FLOW_PATH_TIMELINE_COLUMNS,
    LOSS_ATTRIBUTION_BREAKDOWN_V3_COLUMNS,
    LOSS_ATTRIBUTION_DETAILED_V3_COLUMNS,
    PATH_REPLAY_DIAGNOSTIC_COLUMNS,
    TAG_COVERAGE_COLUMNS,
    build_v3_for_algorithm,
)
from packet_delivery_outputs import (
    archive_flat_outputs,
    ensure_standard_layout,
    link_selection_diagnostic,
    output_path,
    write_deprecated_notes,
    write_output_manifest,
    write_result_guide,
)


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
    "background_flow_count",
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
    "background_flow_count",
    "algorithm",
    "dst",
    "flow_count",
    "destination_background_flow_count",
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

PHYSICAL_DROP_COLUMNS = [
    "time_ns",
    "link_type",
    "interface_type",
    "from_node",
    "to_node",
    "satellite_id",
    "ground_station_id",
    "interface_key",
    "drop_source",
    "drop_reason",
    "packet_size_bytes",
    "queue_occupancy_pkt_if_available",
    "queue_occupancy_byte_if_available",
    "queue_capacity_pkt_if_available",
    "flow_id_if_available",
    "packet_sequence_if_available",
    "packet_uid_if_available",
    "flow_tag_available",
    "trace_hook",
]

PHYSICAL_DROP_SUMMARY_COLUMNS = [
    "algorithm",
    "link_type",
    "drop_source",
    "drop_reason",
    "drop_count",
    "drop_bytes",
    "first_drop_time_ns",
    "last_drop_time_ns",
]

GSL_QUEUE_SUMMARY_COLUMNS = [
    "algorithm",
    "max_gsl_queue_pkt",
    "mean_gsl_queue_pkt",
    "nonzero_gsl_queue_samples",
    "top_gsl_queue_links",
]

LOSS_ATTRIBUTION_COLUMNS = [
    "algorithm",
    "synthetic_lost_packets",
    "physical_drop_packets",
    "send_failed_packets",
    "unexplained_loss",
    "physical_drop_coverage_ratio",
    "gsl_drop_packets",
    "isl_drop_packets",
    "unknown_drop_packets",
]

ROUTING_DROP_COLUMNS = [
    "time_ns",
    "drop_source",
    "drop_reason",
    "node_id",
    "src",
    "dst",
    "next_hop_if_available",
    "packet_size_bytes",
    "flow_id_if_available",
    "packet_sequence_if_available",
    "packet_uid_if_available",
    "flow_tag_available",
    "details",
]

UDP_SEND_FAILURE_COLUMNS = [
    "time_ns",
    "flow_id",
    "src",
    "dst",
    "packet_sequence_if_available",
    "packet_uid_if_available",
    "packet_size_bytes",
    "error_code",
    "error_message_if_available",
]

LOSS_ATTRIBUTION_DETAILED_COLUMNS = [
    "algorithm",
    "flow_id",
    "src",
    "dst",
    "flow_class",
    "sent_packets",
    "received_packets",
    "lost_packets",
    "pdr",
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
    "dominant_association",
    "associated_interfaces",
    "notes",
]

CONGESTED_INTERFACE_COLUMNS = [
    "algorithm",
    "link_type",
    "interface_key",
    "from_node",
    "to_node",
    "satellite_id",
    "ground_station_id",
    "max_queue_pkt",
    "mean_queue_pkt",
    "samples_at_capacity",
    "first_saturation_time_ns",
    "last_saturation_time_ns",
    "estimated_affected_flow_count",
    "estimated_affected_lost_packets",
    "flow_ids_passing_interface_if_available",
]

LOSS_ATTRIBUTION_BREAKDOWN_V2_COLUMNS = [
    "algorithm",
    "synthetic_lost_packets",
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
    "attribution_coverage_ratio",
]

QUEUE_SATURATION_TIMELINE_COLUMNS = [
    "algorithm",
    "time_ns",
    "link_type",
    "interface_key",
    "from_node",
    "to_node",
    "queue_pkt",
    "queue_capacity_pkt",
    "is_at_capacity",
    "estimated_active_flow_count",
    "estimated_active_lost_flow_count",
]

TOP_LOSS_FLOW_COUNT = 20
SYNTHETIC_LOSS_REASON = "udp_sent_minus_received"
MAX_QUEUE_SCOPE = "sampled/event-derived ISL net-device queue; GSL queue summarized separately when available"
PHYSICAL_DROP_TRACE_COVERAGE = (
    "DropBeforeEnqueue queue callbacks, MacTxDrop diagnostics, and "
    "PhyTxDrop/PhyRxDrop on tracked ISL/GSL NetDevices. MacTxDrop is "
    "reported as diagnostic coverage but is not added to physical queue "
    "drop counts when DropBeforeEnqueue is present."
)
QUEUE_ASSOCIATION_WARNING = (
    "Queue-saturation-associated loss is a conservative correlation based on "
    "queue occupancy and flow/path context. It should not be interpreted as a "
    "physical drop proof unless matching physical drop trace events are present."
)

SELECTION_DIAGNOSTIC_FILENAMES = [
    "flow_selection_diagnostics.csv",
    "corridor_overlap_summary.csv",
    "gsl_load_by_endpoint.csv",
    "isl_corridor_load_summary.csv",
    "fallback_phase_summary.csv",
    "corridor_concentration_summary.csv",
    "satellite_interface_load_summary.csv",
]

LHTR_DIAGNOSTIC_COLUMNS = {
    "lhtr_traffic_light_color_summary.csv": [
        "time_ns",
        "traffic_light_scoring_mode",
        "green_count",
        "yellow_count",
        "red_count",
        "qor_yellow_count",
        "qor_red_count",
        "tqor_yellow_count",
        "tqor_red_count",
        "tqor_escalated_count",
        "total_colored_links",
    ],
    "lhtr_br_sbr_summary.csv": [
        "time_ns",
        "traffic_light_scoring_mode",
        "br_selected_count",
        "sbr_selected_count",
        "fallback_count",
        "no_route_count",
        "yellow_count",
        "red_count",
        "green_count",
        "sbr_due_to_yellow_count",
        "sbr_due_to_red_count",
        "fallback_due_to_no_sbr_count",
        "fallback_due_to_sbr_red_count",
        "fallback_due_to_stretch_count",
        "no_admissible_sbr_count",
        "decision_detail_total_count",
        "decision_detail_written_count",
    ],
    "lhtr_decision_reason_summary.csv": [
        "decision_reason",
        "count",
        "percentage",
    ],
    "lhtr_fstate_decision_consistency.csv": [
        "time_ns",
        "src",
        "dst",
        "current_node",
        "case_type",
        "selected_route_type",
        "selected_next_hop",
        "fstate_next_hop",
        "match",
        "notes",
    ],
}


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


def copy_selection_diagnostics(run, comparison_dir, output_layout):
    run_dir = os.path.join("runs", run["name"])
    linked = []
    for filename in SELECTION_DIAGNOSTIC_FILENAMES:
        src = os.path.join(run_dir, filename)
        if not os.path.exists(src):
            continue
        dst = output_path(comparison_dir, filename, output_layout)
        link_selection_diagnostic(src, dst)
        linked.append(dst)
    warnings_src = os.path.join(run_dir, "flow_selection_warnings.txt")
    if os.path.exists(warnings_src):
        link_selection_diagnostic(
            warnings_src,
            output_path(
                comparison_dir,
                "flow_selection_warnings.txt",
                output_layout,
            ),
        )
    return linked


def collect_lhtr_diagnostic_summaries(algorithm_run_dir, run_name, algorithm):
    relative_dir = (
        os.environ.get("LHTR_DIAGNOSTICS_DIR", "lhtr_diagnostics").strip()
        or "lhtr_diagnostics"
    )
    relative_dir = os.path.normpath(relative_dir)
    first_component = relative_dir.split(os.sep, 1)[0]
    if (
        os.path.isabs(relative_dir)
        or relative_dir in (".", "..")
        or relative_dir.startswith(".." + os.sep)
        or first_component in {
            "dynamic_state",
            "logs_ns3",
            "queue_stats",
            "timing_results",
        }
    ):
        relative_dir = "lhtr_diagnostics"
    diagnostics_dir = os.path.join(algorithm_run_dir, relative_dir)

    summaries = {}
    for filename, columns in LHTR_DIAGNOSTIC_COLUMNS.items():
        path = os.path.join(diagnostics_dir, filename)
        if os.path.exists(path):
            try:
                frame = pd.read_csv(path)
            except pd.errors.EmptyDataError:
                frame = pd.DataFrame(columns=columns)
        else:
            frame = pd.DataFrame(columns=columns)
        for column in columns:
            if column not in frame.columns:
                frame[column] = ""
        frame = frame[columns]
        frame.insert(0, "algorithm", algorithm)
        frame.insert(0, "run_name", run_name)
        summaries[filename] = frame
    return summaries


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
            pd.read_csv(physical_path, nrows=0)
            return True
        except pd.errors.EmptyDataError:
            return False
    return not is_synthetic_sent_minus_received_drop_df(drops_df)


def gsl_queue_tracking_available(algorithm_run_dir):
    logs_dir = os.path.join(algorithm_run_dir, "logs_ns3")
    for filename in [
        "gsl_queue_pkt_history.csv",
        "gsl_queue_byte_history.csv",
        "gsl_queue_pkt.csv",
        "gsl_queue_byte.csv",
        "access_queue_pkt.csv",
        "access_queue_byte.csv",
    ]:
        if os.path.exists(os.path.join(logs_dir, filename)):
            return True
    return False


def udp_send_failure_trace_available(algorithm_run_dir):
    return os.path.exists(
        os.path.join(algorithm_run_dir, "logs_ns3", "udp_send_failures.csv")
    )


def routing_drop_trace_available(algorithm_run_dir):
    return os.path.exists(
        os.path.join(algorithm_run_dir, "logs_ns3", "routing_drops.csv")
    )


def ipv4_l3_drop_trace_available(algorithm_run_dir):
    return os.path.exists(
        os.path.join(algorithm_run_dir, "logs_ns3", "ipv4_l3_drops.csv")
    )


def read_queue_capacity_pkt(algorithm_run_dir, run, link_type):
    config = parse_config_properties(os.path.join(algorithm_run_dir, "config_ns3.properties"))
    key = "isl_max_queue_size_pkts" if link_type == "ISL" else "gsl_max_queue_size_pkts"
    value = to_float_or_none(config.get(key))
    if value is not None:
        return int(value)
    run_key = "queue_size_pkt"
    value = to_float_or_none(run.get(run_key))
    if value is not None:
        return int(value)
    return None


def build_interface_key(link_type, from_node, to_node):
    try:
        from_node = int(from_node)
    except (TypeError, ValueError):
        from_node = -1
    try:
        to_node = int(to_node)
    except (TypeError, ValueError):
        to_node = -1
    return "%s:%d->%d" % (link_type, from_node, to_node)


def parse_semicolon_ints(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    result = []
    for item in str(value).split(";"):
        item = item.strip()
        if not item:
            continue
        try:
            result.append(int(float(item)))
        except ValueError:
            continue
    return result


def _normalize_drop_source(row):
    drop_source = str(row.get("drop_source", "") or "")
    trace_hook = str(row.get("trace_hook", "") or "")
    drop_reason = str(row.get("drop_reason", "") or "")
    if drop_source:
        return drop_source
    if trace_hook:
        return trace_hook
    if drop_reason in ["QueueDrop", "DropBeforeEnqueue"]:
        return "QueueDrop"
    if drop_reason in ["PhyTxDrop", "PhyRxDrop", "MacTxDrop"]:
        return drop_reason
    return "Unknown"


def read_physical_link_drops(algorithm_run_dir):
    path = os.path.join(algorithm_run_dir, "logs_ns3", "physical_link_drops.csv")
    if not os.path.exists(path):
        return pd.DataFrame(columns=PHYSICAL_DROP_COLUMNS)
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=PHYSICAL_DROP_COLUMNS)
    for col in PHYSICAL_DROP_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    if "interface_key" in df.columns:
        missing_key = df["interface_key"].astype(str).isin(["", "nan"])
        if missing_key.any():
            df.loc[missing_key, "interface_key"] = df.loc[missing_key].apply(
                lambda row: build_interface_key(row.get("link_type", "UNKNOWN"), row.get("from_node", -1), row.get("to_node", -1)),
                axis=1,
            )
    if "drop_source" in df.columns:
        df["drop_source"] = df.apply(_normalize_drop_source, axis=1)
    if "trace_hook" in df.columns:
        missing_hook = df["trace_hook"].astype(str).isin(["", "nan"])
        df.loc[missing_hook, "trace_hook"] = df.loc[missing_hook, "drop_source"]
    df = df[PHYSICAL_DROP_COLUMNS].copy()
    for col in [
        "time_ns",
        "from_node",
        "to_node",
        "satellite_id",
        "ground_station_id",
        "packet_size_bytes",
        "queue_occupancy_pkt_if_available",
        "queue_occupancy_byte_if_available",
        "queue_capacity_pkt_if_available",
        "flow_id_if_available",
        "packet_sequence_if_available",
        "packet_uid_if_available",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def read_interface_queue_drops(algorithm_run_dir):
    path = os.path.join(algorithm_run_dir, "logs_ns3", "interface_queue_drops.csv")
    if not os.path.exists(path):
        return pd.DataFrame(columns=PHYSICAL_DROP_COLUMNS)
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=PHYSICAL_DROP_COLUMNS)
    for col in PHYSICAL_DROP_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["drop_source"] = df.apply(_normalize_drop_source, axis=1)
    return df[PHYSICAL_DROP_COLUMNS].copy()


def read_udp_send_failures(algorithm_run_dir):
    path = os.path.join(algorithm_run_dir, "logs_ns3", "udp_send_failures.csv")
    if not os.path.exists(path):
        return pd.DataFrame(columns=UDP_SEND_FAILURE_COLUMNS)
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=UDP_SEND_FAILURE_COLUMNS)
    for col in UDP_SEND_FAILURE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[UDP_SEND_FAILURE_COLUMNS].copy()
    for col in [
        "time_ns",
        "flow_id",
        "src",
        "dst",
        "packet_sequence_if_available",
        "packet_uid_if_available",
        "packet_size_bytes",
        "error_code",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def read_routing_drops(algorithm_run_dir):
    path = os.path.join(algorithm_run_dir, "logs_ns3", "routing_drops.csv")
    if not os.path.exists(path):
        return pd.DataFrame(columns=ROUTING_DROP_COLUMNS)
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=ROUTING_DROP_COLUMNS)
    for col in ROUTING_DROP_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[ROUTING_DROP_COLUMNS].copy()
    for col in [
        "time_ns",
        "node_id",
        "packet_size_bytes",
        "flow_id_if_available",
        "packet_sequence_if_available",
        "packet_uid_if_available",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


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


def build_udp_flows_csv(algorithm_run_dir, run):
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
                (run["src_node_id"], run["dst_node_id"]),
                (run["dst_node_id"], run["src_node_id"]),
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
        "focus_src_node_id": run["src_node_id"],
        "focus_dst_node_id": run["dst_node_id"],
        "focus_src_name_if_available": run.get(
            "focus_src_name_if_available",
            "",
        ),
        "focus_dst_name_if_available": run.get(
            "focus_dst_name_if_available",
            "",
        ),
        "focus_pair_tag": run["focus_pair_tag"],
        "focus_flow_direction_count": run["focus_flow_direction_count"],
        "traffic_mode": run["traffic_mode"],
        "load_level": run["load_level"],
        "background_flow_count": run["background_flow_count"],
        "per_flow_rate_reference_background_flow_count": run[
            "per_flow_rate_reference_background_flow_count"
        ],
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
        "per_flow_target_rate_mbps": (
            float(flows["target_rate_mbps"].iloc[0]) if len(flows) else 0.0
        ),
        "total_target_rate_mbps": float(flows["target_rate_mbps"].sum()),
        "background_target_rate_mbps": float(
            flows[flows["flow_class"] == "background"]["target_rate_mbps"].sum()
        ),
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


def _read_queue_interval_csv(path, value_name):
    columns = ["from", "to", "interval_start_ns", "interval_end_ns", value_name]
    if not os.path.exists(path):
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, header=None, names=columns)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)
    for col in columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["from", "to", "interval_start_ns", "interval_end_ns", value_name])


def _queue_interval_path(logs_dir, link_type, value_kind):
    prefix = link_type.lower()
    history_path = os.path.join(
        logs_dir,
        "%s_queue_%s_history.csv" % (prefix, value_kind),
    )
    if os.path.exists(history_path) and os.path.getsize(history_path) > 0:
        return history_path
    return os.path.join(logs_dir, "%s_queue_%s.csv" % (prefix, value_kind))


def collect_gsl_queue_summary(algorithm_run_dir, algorithm):
    logs_dir = os.path.join(algorithm_run_dir, "logs_ns3")
    pkt_path = _queue_interval_path(logs_dir, "GSL", "pkt")
    df = _read_queue_interval_csv(pkt_path, "queue_pkt")
    if len(df) == 0:
        return {
            "algorithm": algorithm,
            "max_gsl_queue_pkt": 0,
            "mean_gsl_queue_pkt": 0.0,
            "nonzero_gsl_queue_samples": 0,
            "top_gsl_queue_links": "",
        }

    df["from"] = df["from"].astype("int64")
    df["to"] = df["to"].astype("int64")
    df["queue_pkt"] = df["queue_pkt"].astype("float64")
    max_by_link = (
        df.groupby(["from", "to"])["queue_pkt"]
        .max()
        .reset_index(name="packet_max")
        .sort_values(["packet_max", "from", "to"], ascending=[False, True, True])
    )
    top_links = []
    for _, row in max_by_link.head(8).iterrows():
        top_links.append(
            "%d->%d:%d"
            % (int(row["from"]), int(row["to"]), int(row["packet_max"]))
        )
    return {
        "algorithm": algorithm,
        "max_gsl_queue_pkt": int(df["queue_pkt"].max()),
        "mean_gsl_queue_pkt": float(df["queue_pkt"].mean()),
        "nonzero_gsl_queue_samples": int((df["queue_pkt"] > 0).sum()),
        "top_gsl_queue_links": ";".join(top_links),
    }


def infer_num_satellites_from_flows(flows):
    endpoint_values = []
    if len(flows):
        endpoint_values.extend(flows["src"].dropna().astype(int).tolist())
        endpoint_values.extend(flows["dst"].dropna().astype(int).tolist())
    return min(endpoint_values) if endpoint_values else 0


def load_interface_flow_maps(run, flows):
    run_dir = os.path.join("runs", run["name"])
    interface_to_flows = {}
    flow_to_isl = {}
    flow_to_gsl = {}

    def add_mapping(interface_key, flow_ids, link_type):
        if not interface_key or not flow_ids:
            return
        bucket = interface_to_flows.setdefault(interface_key, set())
        for flow_id in flow_ids:
            bucket.add(flow_id)
            if link_type == "ISL":
                flow_to_isl.setdefault(flow_id, set()).add(interface_key)
            elif link_type == "GSL":
                flow_to_gsl.setdefault(flow_id, set()).add(interface_key)

    isl_path = os.path.join(run_dir, "isl_corridor_load_summary.csv")
    if os.path.exists(isl_path):
        try:
            isl_df = pd.read_csv(isl_path)
        except pd.errors.EmptyDataError:
            isl_df = pd.DataFrame()
        for _, row in isl_df.iterrows():
            flow_ids = parse_semicolon_ints(
                row.get("selected_flow_ids_using_edge", row.get("selected_flow_ids", ""))
            )
            try:
                edge_from = int(row["edge_from"])
                edge_to = int(row["edge_to"])
            except (KeyError, TypeError, ValueError):
                continue
            add_mapping(build_interface_key("ISL", edge_from, edge_to), flow_ids, "ISL")

    satellite_interface_path = os.path.join(run_dir, "satellite_interface_load_summary.csv")
    if os.path.exists(satellite_interface_path):
        try:
            sat_if_df = pd.read_csv(satellite_interface_path)
        except pd.errors.EmptyDataError:
            sat_if_df = pd.DataFrame()
        for _, row in sat_if_df.iterrows():
            flow_ids = parse_semicolon_ints(row.get("selected_flow_ids", ""))
            try:
                satellite_id = int(row["satellite_id"])
            except (KeyError, TypeError, ValueError):
                continue
            add_mapping(build_interface_key("GSL", satellite_id, -1), flow_ids, "GSL")

    flow_selection_path = os.path.join(run_dir, "flow_selection_diagnostics.csv")
    if os.path.exists(flow_selection_path):
        try:
            flow_selection_df = pd.read_csv(flow_selection_path)
        except pd.errors.EmptyDataError:
            flow_selection_df = pd.DataFrame()
        if len(flow_selection_df):
            selected = flow_selection_df[
                flow_selection_df.get("selected", False).astype(str).str.lower() == "true"
            ] if "selected" in flow_selection_df.columns else flow_selection_df
            for _, row in selected.iterrows():
                try:
                    flow_id = int(float(row["flow_id"]))
                except (KeyError, TypeError, ValueError):
                    continue
                for item in str(row.get("satellite_interface_keys", "")).split(";"):
                    if ":" not in item:
                        continue
                    sat_id, _direction = item.split(":", 1)
                    try:
                        sat_id = int(sat_id)
                    except ValueError:
                        continue
                    add_mapping(build_interface_key("GSL", sat_id, -1), [flow_id], "GSL")

    # Endpoint/access-side fallback: GSL queue trackers may be attached to
    # ground-station net devices. This does not prove the exact satellite-side
    # path, but it gives a conservative access-queue association.
    for _, row in flows.iterrows():
        flow_id = int(row["flow_id"])
        src = int(row["src"])
        dst = int(row["dst"])
        add_mapping(build_interface_key("GSL", src, -1), [flow_id], "GSL")
        add_mapping(build_interface_key("GSL", dst, -1), [flow_id], "GSL")

    return interface_to_flows, flow_to_isl, flow_to_gsl


def read_queue_timeline_inputs(algorithm_run_dir, run, algorithm, flows):
    rows = []
    capacities = {
        "ISL": read_queue_capacity_pkt(algorithm_run_dir, run, "ISL"),
        "GSL": read_queue_capacity_pkt(algorithm_run_dir, run, "GSL"),
    }
    logs_dir = os.path.join(algorithm_run_dir, "logs_ns3")
    for link_type in ["ISL", "GSL"]:
        path = _queue_interval_path(logs_dir, link_type, "pkt")
        df = _read_queue_interval_csv(path, "queue_pkt")
        if len(df) == 0:
            continue
        capacity = capacities.get(link_type)
        for _, row in df.iterrows():
            from_node = int(row["from"])
            to_node = int(row["to"])
            queue_pkt = float(row["queue_pkt"])
            rows.append({
                "algorithm": algorithm,
                "interval_start_ns": int(row["interval_start_ns"]),
                "interval_end_ns": int(row["interval_end_ns"]),
                "time_ns": int(row["interval_start_ns"]),
                "link_type": link_type,
                "interface_key": build_interface_key(link_type, from_node, to_node),
                "from_node": from_node,
                "to_node": to_node,
                "queue_pkt": queue_pkt,
                "queue_capacity_pkt": capacity if capacity is not None else math.nan,
                "is_at_capacity": bool(capacity is not None and queue_pkt >= capacity),
            })
    if not rows:
        return pd.DataFrame(columns=QUEUE_SATURATION_TIMELINE_COLUMNS + ["interval_end_ns"])
    return pd.DataFrame(rows)


def build_queue_saturation_outputs(
    algorithm_run_dir,
    run,
    algorithm,
    flows,
    write_full_timeline=False,
):
    interface_to_flows, _flow_to_isl, _flow_to_gsl = load_interface_flow_maps(run, flows)
    timeline = read_queue_timeline_inputs(algorithm_run_dir, run, algorithm, flows)
    num_satellites = infer_num_satellites_from_flows(flows)
    flows_by_id = {
        int(row["flow_id"]): row
        for _, row in flows.iterrows()
    }
    flow_isl_saturated_interfaces = {}
    flow_gsl_saturated_interfaces = {}

    if len(timeline) == 0:
        empty_timeline = pd.DataFrame(columns=QUEUE_SATURATION_TIMELINE_COLUMNS)
        empty_congested = pd.DataFrame(columns=CONGESTED_INTERFACE_COLUMNS)
        return (
            empty_timeline,
            empty_congested,
            flow_isl_saturated_interfaces,
            flow_gsl_saturated_interfaces,
        )

    active_counts = []
    active_lost_counts = []
    for _, row in timeline.iterrows():
        flow_ids = sorted(interface_to_flows.get(row["interface_key"], set()))
        active = []
        active_lost = []
        for flow_id in flow_ids:
            flow = flows_by_id.get(flow_id)
            if flow is None:
                continue
            if int(flow["start_time_ns"]) <= int(row["time_ns"]) <= int(flow["end_time_ns"]):
                active.append(flow_id)
                if int(flow["lost_packets"]) > 0:
                    active_lost.append(flow_id)
        active_counts.append(len(active))
        active_lost_counts.append(len(active_lost))
        if bool(row["is_at_capacity"]):
            for flow_id in flow_ids:
                flow = flows_by_id.get(flow_id)
                if flow is None or int(flow["lost_packets"]) <= 0:
                    continue
                if row["link_type"] == "ISL":
                    flow_isl_saturated_interfaces.setdefault(flow_id, set()).add(row["interface_key"])
                elif row["link_type"] == "GSL":
                    flow_gsl_saturated_interfaces.setdefault(flow_id, set()).add(row["interface_key"])

    timeline["estimated_active_flow_count"] = active_counts
    timeline["estimated_active_lost_flow_count"] = active_lost_counts
    timeline_out = timeline[QUEUE_SATURATION_TIMELINE_COLUMNS].copy()
    if not write_full_timeline:
        timeline_out = timeline_out[
            timeline_out["is_at_capacity"] == True
        ].reset_index(drop=True)

    congested_rows = []
    saturated = timeline[timeline["is_at_capacity"] == True]
    for interface_key, group in timeline.groupby("interface_key"):
        saturated_group = group[group["is_at_capacity"] == True]
        if len(saturated_group) == 0:
            continue
        first = group.iloc[0]
        flow_ids = sorted(interface_to_flows.get(interface_key, set()))
        affected_lost = 0
        for flow_id in flow_ids:
            flow = flows_by_id.get(flow_id)
            if flow is not None:
                affected_lost += int(flow["lost_packets"])
        from_node = int(first["from_node"])
        satellite_id = from_node if num_satellites and from_node < num_satellites else ""
        ground_station_id = (
            from_node - num_satellites
            if num_satellites and from_node >= num_satellites
            else ""
        )
        congested_rows.append({
            "algorithm": algorithm,
            "link_type": first["link_type"],
            "interface_key": interface_key,
            "from_node": from_node,
            "to_node": int(first["to_node"]),
            "satellite_id": satellite_id,
            "ground_station_id": ground_station_id,
            "max_queue_pkt": int(group["queue_pkt"].max()),
            "mean_queue_pkt": float(group["queue_pkt"].mean()),
            "samples_at_capacity": int(len(saturated_group)),
            "first_saturation_time_ns": int(saturated_group["time_ns"].min()),
            "last_saturation_time_ns": int(saturated_group["time_ns"].max()),
            "estimated_affected_flow_count": int(len(flow_ids)),
            "estimated_affected_lost_packets": int(affected_lost),
            "flow_ids_passing_interface_if_available": ";".join(str(flow_id) for flow_id in flow_ids),
        })
    congested = pd.DataFrame(congested_rows, columns=CONGESTED_INTERFACE_COLUMNS)
    if len(congested):
        congested = congested.sort_values(
            ["algorithm", "samples_at_capacity", "max_queue_pkt", "interface_key"],
            ascending=[True, False, False, True],
        ).reset_index(drop=True)
    return (
        timeline_out,
        congested,
        flow_isl_saturated_interfaces,
        flow_gsl_saturated_interfaces,
    )


def _count_drop_source(df, algorithm, sources):
    if len(df) == 0:
        return 0
    alg = df[df["algorithm"] == algorithm]
    if len(alg) == 0:
        return 0
    return int(alg["drop_source"].astype(str).isin(sources).sum())


def build_physical_drop_summary(physical_drop_df):
    if len(physical_drop_df) == 0:
        return pd.DataFrame(columns=PHYSICAL_DROP_SUMMARY_COLUMNS)
    df = physical_drop_df.copy()
    df["packet_size_bytes"] = pd.to_numeric(
        df["packet_size_bytes"], errors="coerce"
    ).fillna(0)
    return (
        df.groupby(["algorithm", "link_type", "drop_source", "drop_reason"])
        .agg(
            drop_count=("drop_reason", "size"),
            drop_bytes=("packet_size_bytes", "sum"),
            first_drop_time_ns=("time_ns", "min"),
            last_drop_time_ns=("time_ns", "max"),
        )
        .reset_index()[PHYSICAL_DROP_SUMMARY_COLUMNS]
        .sort_values(["algorithm", "link_type", "drop_reason"])
    )


def build_loss_attribution_summary(summary_df, physical_drop_df, send_failure_df):
    rows = []
    for _, row in summary_df.iterrows():
        algorithm = row["algorithm"]
        synthetic_lost = int(row["total_lost_packets"])
        alg_drops = physical_drop_df[
            physical_drop_df["algorithm"] == algorithm
        ] if len(physical_drop_df) else pd.DataFrame()
        alg_send_failures = send_failure_df[
            send_failure_df["algorithm"] == algorithm
        ] if len(send_failure_df) else pd.DataFrame()

        if len(alg_drops):
            countable_drops = alg_drops[
                ~alg_drops["drop_source"].astype(str).isin(["MacTxDrop"])
            ]
        else:
            countable_drops = alg_drops
        physical_drop_packets = int(len(countable_drops))
        send_failed_packets = int(len(alg_send_failures))
        gsl_drop_packets = int((countable_drops["link_type"] == "GSL").sum()) if len(countable_drops) else 0
        isl_drop_packets = int((countable_drops["link_type"] == "ISL").sum()) if len(countable_drops) else 0
        unknown_drop_packets = (
            physical_drop_packets - gsl_drop_packets - isl_drop_packets
        )
        unexplained_loss = synthetic_lost - physical_drop_packets - send_failed_packets
        coverage = (
            physical_drop_packets / float(synthetic_lost)
            if synthetic_lost > 0
            else 0.0
        )
        rows.append({
            "algorithm": algorithm,
            "synthetic_lost_packets": synthetic_lost,
            "physical_drop_packets": physical_drop_packets,
            "send_failed_packets": send_failed_packets,
            "unexplained_loss": unexplained_loss,
            "physical_drop_coverage_ratio": coverage,
            "gsl_drop_packets": gsl_drop_packets,
            "isl_drop_packets": isl_drop_packets,
            "unknown_drop_packets": unknown_drop_packets,
        })
    return pd.DataFrame(rows, columns=LOSS_ATTRIBUTION_COLUMNS)


def _count_by_flow_id(df, flow_id_col="flow_id"):
    if len(df) == 0 or flow_id_col not in df.columns:
        return {}
    counts = {}
    valid = df[pd.to_numeric(df[flow_id_col], errors="coerce").notna()].copy()
    if len(valid) == 0:
        return counts
    valid[flow_id_col] = pd.to_numeric(valid[flow_id_col], errors="coerce").astype(int)
    for flow_id, group in valid.groupby(flow_id_col):
        counts[int(flow_id)] = int(len(group))
    return counts


def build_loss_attribution_detailed(
    algorithm,
    flows,
    physical_drop_df,
    udp_send_failure_df,
    routing_drop_df,
    flow_isl_saturated_interfaces,
    flow_gsl_saturated_interfaces,
    run,
):
    alg_physical = physical_drop_df[
        physical_drop_df["algorithm"] == algorithm
    ] if len(physical_drop_df) else pd.DataFrame(columns=physical_drop_df.columns)
    queue_sources = ["QueueDrop", "DropBeforeEnqueue"]
    phy_sources = ["PhyTxDrop", "PhyRxDrop"]
    physical_queue_by_flow = _count_by_flow_id(
        alg_physical[
            alg_physical["drop_source"].astype(str).isin(queue_sources)
        ] if len(alg_physical) else pd.DataFrame(),
        "flow_id_if_available",
    )
    physical_phy_by_flow = _count_by_flow_id(
        alg_physical[
            alg_physical["drop_source"].astype(str).isin(phy_sources)
        ] if len(alg_physical) else pd.DataFrame(),
        "flow_id_if_available",
    )
    send_by_flow = _count_by_flow_id(
        udp_send_failure_df[udp_send_failure_df["algorithm"] == algorithm]
        if len(udp_send_failure_df) else pd.DataFrame(),
        "flow_id",
    )
    routing_by_flow = _count_by_flow_id(
        routing_drop_df[routing_drop_df["algorithm"] == algorithm]
        if len(routing_drop_df) else pd.DataFrame(),
        "flow_id_if_available",
    )
    tail_possible = (
        not bool(run.get("drain_time_enabled", False))
        or int(run.get("drain_time_ns", 0)) <= 0
    )

    rows = []
    for _, row in flows.sort_values("flow_id").iterrows():
        flow_id = int(row["flow_id"])
        lost_packets = int(row["lost_packets"])
        physical_queue = physical_queue_by_flow.get(flow_id, 0)
        physical_phy = physical_phy_by_flow.get(flow_id, 0)
        send_failed = send_by_flow.get(flow_id, 0)
        routing_drop = routing_by_flow.get(flow_id, 0)
        ipv4_l3_drop = 0
        attributed_trace = physical_queue + physical_phy + send_failed + routing_drop + ipv4_l3_drop
        explainable_loss = max(lost_packets - attributed_trace, 0)
        isl_interfaces = sorted(flow_isl_saturated_interfaces.get(flow_id, set()))
        gsl_interfaces = sorted(flow_gsl_saturated_interfaces.get(flow_id, set()))
        isl_assoc = 0
        gsl_assoc = 0
        mixed_assoc = 0
        tail_loss = 0
        unclassified = 0
        dominant = ""
        if explainable_loss > 0:
            if isl_interfaces and gsl_interfaces:
                mixed_assoc = explainable_loss
                dominant = "mixed_queue_saturation_associated"
            elif isl_interfaces:
                isl_assoc = explainable_loss
                dominant = "isl_queue_saturation_associated"
            elif gsl_interfaces:
                gsl_assoc = explainable_loss
                dominant = "gsl_queue_saturation_associated"
            elif tail_possible:
                tail_loss = explainable_loss
                dominant = "tail_in_flight_possible"
            else:
                unclassified = explainable_loss
                dominant = "unclassified_unexplained"
        elif attributed_trace > 0:
            dominant = "trace_attributed"
        elif lost_packets == 0:
            dominant = "no_loss"

        notes = []
        if lost_packets > 0:
            notes.append("queue_saturation_association_is_not_physical_proof")
        if len(alg_physical) and (
            len(physical_queue_by_flow) == 0 and len(physical_phy_by_flow) == 0
        ):
            notes.append("physical_drop_trace_is_interface_level_only")
        if isl_interfaces:
            notes.append("isl_mapping_from_corridor_diagnostics")
        if gsl_interfaces:
            notes.append("gsl_mapping_from_satellite_interface_or_endpoint_proxy")
        if tail_loss:
            notes.append("traffic_stop_has_no_positive_drain_window")

        rows.append({
            "algorithm": algorithm,
            "flow_id": flow_id,
            "src": int(row["src"]),
            "dst": int(row["dst"]),
            "flow_class": row["flow_class"],
            "sent_packets": int(row["sent_packets"]),
            "received_packets": int(row["received_packets"]),
            "lost_packets": lost_packets,
            "pdr": float(row["pdr"]),
            "physical_queue_drop_packets": physical_queue,
            "physical_phy_drop_packets": physical_phy,
            "udp_send_failed_packets": send_failed,
            "routing_drop_packets": routing_drop,
            "ipv4_l3_drop_packets": ipv4_l3_drop,
            "isl_queue_saturation_associated_loss": isl_assoc,
            "gsl_queue_saturation_associated_loss": gsl_assoc,
            "mixed_queue_saturation_associated_loss": mixed_assoc,
            "tail_in_flight_possible_loss": tail_loss,
            "unclassified_unexplained_loss": unclassified,
            "dominant_association": dominant,
            "associated_interfaces": ";".join(isl_interfaces + gsl_interfaces),
            "notes": "|".join(notes),
        })
    return pd.DataFrame(rows, columns=LOSS_ATTRIBUTION_DETAILED_COLUMNS)


def build_loss_attribution_breakdown_v2(
    summary_df,
    detailed_df,
    physical_drop_df,
    udp_send_failure_df,
    routing_drop_df,
):
    rows = []
    for _, row in summary_df.iterrows():
        algorithm = row["algorithm"]
        synthetic_lost = int(row["total_lost_packets"])
        alg_detail = detailed_df[
            detailed_df["algorithm"] == algorithm
        ] if len(detailed_df) else pd.DataFrame(columns=LOSS_ATTRIBUTION_DETAILED_COLUMNS)
        physical_queue = _count_drop_source(
            physical_drop_df,
            algorithm,
            ["QueueDrop", "DropBeforeEnqueue"],
        )
        physical_phy = _count_drop_source(
            physical_drop_df,
            algorithm,
            ["PhyTxDrop", "PhyRxDrop"],
        )
        udp_failed = int(
            len(udp_send_failure_df[udp_send_failure_df["algorithm"] == algorithm])
        ) if len(udp_send_failure_df) else 0
        routing_drop = int(
            len(routing_drop_df[routing_drop_df["algorithm"] == algorithm])
        ) if len(routing_drop_df) else 0
        ipv4_l3_drop = 0
        isl_assoc = int(alg_detail["isl_queue_saturation_associated_loss"].sum()) if len(alg_detail) else 0
        gsl_assoc = int(alg_detail["gsl_queue_saturation_associated_loss"].sum()) if len(alg_detail) else 0
        mixed_assoc = int(alg_detail["mixed_queue_saturation_associated_loss"].sum()) if len(alg_detail) else 0
        tail_loss = int(alg_detail["tail_in_flight_possible_loss"].sum()) if len(alg_detail) else 0
        unclassified = int(alg_detail["unclassified_unexplained_loss"].sum()) if len(alg_detail) else 0
        coverage = (
            1.0 - (unclassified / float(synthetic_lost))
            if synthetic_lost > 0
            else 1.0
        )
        rows.append({
            "algorithm": algorithm,
            "synthetic_lost_packets": synthetic_lost,
            "physical_queue_drop_packets": physical_queue,
            "physical_phy_drop_packets": physical_phy,
            "udp_send_failed_packets": udp_failed,
            "routing_drop_packets": routing_drop,
            "ipv4_l3_drop_packets": ipv4_l3_drop,
            "isl_queue_saturation_associated_loss": isl_assoc,
            "gsl_queue_saturation_associated_loss": gsl_assoc,
            "mixed_queue_saturation_associated_loss": mixed_assoc,
            "tail_in_flight_possible_loss": tail_loss,
            "unclassified_unexplained_loss": unclassified,
            "attribution_coverage_ratio": coverage,
        })
    return pd.DataFrame(rows, columns=LOSS_ATTRIBUTION_BREAKDOWN_V2_COLUMNS)


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
    group_columns = ["load_level", "background_flow_count", "algorithm", "dst"]
    for (load_level, background_flow_count, algorithm, dst), group in per_flow_df.groupby(group_columns):
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
            "background_flow_count": int(background_flow_count),
            "algorithm": algorithm,
            "dst": int(dst),
            "flow_count": int(len(group)),
            "destination_background_flow_count": int(
                (group["flow_class"] == "background").sum()
            ),
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
        .sort_values(["load_level", "background_flow_count", "algorithm", "dst"])
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
    physical_drop_summary_df,
    gsl_queue_summary_df,
    loss_attribution_df,
    loss_attribution_breakdown_v2_df,
    loss_attribution_detailed_df,
    loss_attribution_breakdown_v3_df,
    loss_attribution_detailed_v3_df,
    path_replay_diagnostics_df,
    tag_coverage_diagnostics_df,
    congested_interfaces_df,
    physical_trace_available,
    gsl_queue_available,
    udp_send_failure_available,
    routing_drop_available,
    ipv4_l3_drop_available,
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
        f_out.write("focus_src_node_id = %d\n" % run["src_node_id"])
        f_out.write("focus_dst_node_id = %d\n" % run["dst_node_id"])
        f_out.write(
            "focus_src_name_if_available = %s\n"
            % run.get("focus_src_name_if_available", "")
        )
        f_out.write(
            "focus_dst_name_if_available = %s\n"
            % run.get("focus_dst_name_if_available", "")
        )
        f_out.write("focus_pair_tag = %s\n" % run["focus_pair_tag"])
        f_out.write(
            "focus_flow_direction_count = %d\n\n"
            % run["focus_flow_direction_count"]
        )

        f_out.write("How to read this report\n")
        f_out.write("-" * 40 + "\n")
        f_out.write(
            "Synthetic loss = UDP sender count - UDP receiver count. It means "
            "a packet did not reach the UDP application before simulation end; "
            "it is not by itself a physical link-drop observation.\n"
        )
        f_out.write(
            "Exact attribution requires a matching trace event: queue/device "
            "rejection, PHY Tx/Rx drop, routing/no-route drop, or Socket::SendTo "
            "failure. Physical drop therefore means exact traced link/device drop.\n"
        )
        f_out.write(
            "Queue occupancy at capacity is saturation evidence only. Exact queue "
            "drop attribution requires Enqueue(packet) to fail and QueueDrop or "
            "DropBeforeEnqueue to fire. UdpFlowTag identifies an event after it "
            "occurs and does not create drop events, so exact counts can remain zero.\n"
        )
        f_out.write(
            "Associated attribution is inferred from same-window dynamic path replay "
            "and queue saturation. ISL associated and GSL associated identify the "
            "overlapping link type. Mixed means one flow has both ISL and GSL "
            "evidence; it is flow-level ambiguity, not packet-level proof or a "
            "division of causal loss between ISL and GSL.\n"
        )
        f_out.write(
            "Unclassified loss is the residual with no exact event or supported "
            "association. Confidence is high for exact reconciliation, medium when "
            "association evidence explains residual loss, and low when unexplained "
            "residual remains.\n\n"
        )

        f_out.write("Recommended outputs\n")
        f_out.write("-" * 40 + "\n")
        f_out.write("core/summary_by_algorithm.csv\n")
        f_out.write("core/per_flow_delivery.csv\n")
        f_out.write("core/loss_attribution_breakdown_v3.csv\n")
        f_out.write("core/loss_attribution_detailed_v3.csv\n")
        f_out.write("core/congested_interfaces_summary.csv\n")
        f_out.write("core/path_replay_diagnostics.csv\n")
        f_out.write("core/physical_drop_summary.csv\n")
        f_out.write(
            "Deprecated: legacy loss attribution v1/v2 outputs, link_drops.csv, "
            "and link_drop_heatmap.png. Do not use them as paper results.\n\n"
        )

        f_out.write("Attribution availability\n")
        f_out.write("-" * 40 + "\n")
        f_out.write(
            "physical_drop_trace_available = %s\n"
            % format_bool(physical_trace_available)
        )
        f_out.write("loss_attribution = %s\n" % loss_attribution)
        f_out.write("max_queue_scope = %s\n" % MAX_QUEUE_SCOPE)
        f_out.write(
            "physical_drop_trace_coverage = %s\n" % PHYSICAL_DROP_TRACE_COVERAGE
        )
        f_out.write(
            "gsl_queue_tracking_available = %s\n\n"
            % format_bool(gsl_queue_available)
        )
        f_out.write(
            "udp_send_failure_trace_available = %s\n\n"
            % format_bool(udp_send_failure_available)
        )
        f_out.write(
            "routing_drop_trace_available = %s\n"
            % format_bool(routing_drop_available)
        )
        f_out.write(
            "ipv4_l3_drop_trace_available = %s\n\n"
            % format_bool(ipv4_l3_drop_available)
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
        if len(gsl_queue_summary_df):
            f_out.write("GSL/access queue summary:\n")
            for _, row in gsl_queue_summary_df.iterrows():
                f_out.write(
                    "  algorithm=%s max_gsl_queue_pkt=%s mean_gsl_queue_pkt=%.6f "
                    "nonzero_samples=%s top_links=%s\n"
                    % (
                        row["algorithm"],
                        row["max_gsl_queue_pkt"],
                        float(row["mean_gsl_queue_pkt"]),
                        row["nonzero_gsl_queue_samples"],
                        row["top_gsl_queue_links"],
                    )
                )
        if len(physical_drop_summary_df):
            f_out.write("Physical drop summary:\n")
            for _, row in physical_drop_summary_df.iterrows():
                f_out.write(
                    "  algorithm=%s link_type=%s source=%s reason=%s drops=%d bytes=%d first=%s last=%s\n"
                    % (
                        row["algorithm"],
                        row["link_type"],
                        row["drop_source"],
                        row["drop_reason"],
                        int(row["drop_count"]),
                        int(row["drop_bytes"]),
                        row["first_drop_time_ns"],
                        row["last_drop_time_ns"],
                    )
                )
        else:
            f_out.write("No physical drop events were recorded by the available trace hooks.\n")
        if len(loss_attribution_df):
            f_out.write("Loss attribution summary:\n")
            for _, row in loss_attribution_df.iterrows():
                f_out.write(
                    "  algorithm=%s synthetic_lost=%d physical_drops=%d "
                    "send_failed=%d unexplained=%d gsl_drops=%d isl_drops=%d unknown_drops=%d\n"
                    % (
                        row["algorithm"],
                        int(row["synthetic_lost_packets"]),
                        int(row["physical_drop_packets"]),
                        int(row["send_failed_packets"]),
                        int(row["unexplained_loss"]),
                        int(row["gsl_drop_packets"]),
                        int(row["isl_drop_packets"]),
                        int(row["unknown_drop_packets"]),
                    )
                )
        f_out.write("\n")

        f_out.write("[Detailed Loss Attribution]\n")
        f_out.write("-" * 40 + "\n")
        f_out.write(
            "physical_queue_drop_trace_available = %s\n"
            % format_bool(physical_trace_available)
        )
        f_out.write(
            "routing_no_route_drop_trace_available = %s\n"
            % format_bool(routing_drop_available)
        )
        f_out.write(
            "ipv4_l3_drop_trace_available = %s\n"
            % format_bool(ipv4_l3_drop_available)
        )
        f_out.write(
            "queue_saturation_association_warning = %s\n"
            % QUEUE_ASSOCIATION_WARNING
        )
        if len(loss_attribution_breakdown_v2_df):
            f_out.write("Compatibility-only attribution breakdown v2:\n")
            for _, row in loss_attribution_breakdown_v2_df.iterrows():
                f_out.write(
                    "  algorithm=%s synthetic_lost=%d physical_queue=%d physical_phy=%d "
                    "udp_send_failed=%d routing=%d ipv4_l3=%d isl_assoc=%d "
                    "gsl_assoc=%d mixed_assoc=%d tail_possible=%d unclassified=%d "
                    "coverage=%.6f\n"
                    % (
                        row["algorithm"],
                        int(row["synthetic_lost_packets"]),
                        int(row["physical_queue_drop_packets"]),
                        int(row["physical_phy_drop_packets"]),
                        int(row["udp_send_failed_packets"]),
                        int(row["routing_drop_packets"]),
                        int(row["ipv4_l3_drop_packets"]),
                        int(row["isl_queue_saturation_associated_loss"]),
                        int(row["gsl_queue_saturation_associated_loss"]),
                        int(row["mixed_queue_saturation_associated_loss"]),
                        int(row["tail_in_flight_possible_loss"]),
                        int(row["unclassified_unexplained_loss"]),
                        float(row["attribution_coverage_ratio"]),
                    )
                )
        else:
            f_out.write("No detailed attribution rows were generated.\n")
        if len(loss_attribution_breakdown_v3_df):
            f_out.write("\nTime-aware attribution breakdown v3:\n")
            for _, row in loss_attribution_breakdown_v3_df.iterrows():
                f_out.write(
                    "  algorithm=%s synthetic_lost=%d exact=%d isl_assoc=%d "
                    "gsl_assoc=%d mixed_assoc=%d tail_possible=%d unclassified=%d "
                    "path_replay_success=%.6f flow_tag_coverage=%.6f "
                    "attribution_coverage=%.6f reconciliation_errors=%d confidence=%s\n"
                    % (
                        row["algorithm"],
                        int(row["synthetic_lost_packets"]),
                        int(row["exact_attributed_loss"]),
                        int(row["isl_saturation_associated_loss"]),
                        int(row["gsl_saturation_associated_loss"]),
                        int(row["mixed_saturation_associated_loss"]),
                        int(row["tail_in_flight_possible_loss"]),
                        int(row["unclassified_loss"]),
                        float(row["path_replay_success_ratio"]),
                        float(row["flow_tag_coverage_ratio"]),
                        float(row["attribution_coverage_ratio"]),
                        int(row["reconciliation_error_count"]),
                        row["attribution_confidence"],
                    )
                )
        if len(path_replay_diagnostics_df):
            f_out.write("Path replay status counts:\n")
            for _, row in path_replay_diagnostics_df.iterrows():
                f_out.write(
                    "  algorithm=%s status=%s count=%d success_ratio=%.6f notes=%s\n"
                    % (
                        row["algorithm"],
                        row["status"],
                        int(row["count"]),
                        float(row["path_replay_success_ratio"]),
                        row["notes"],
                    )
                )
        if len(tag_coverage_diagnostics_df):
            f_out.write("Flow-tag coverage by drop source:\n")
            for _, row in tag_coverage_diagnostics_df.iterrows():
                f_out.write(
                    "  algorithm=%s family=%s source=%s total=%d tagged=%d ratio=%.6f\n"
                    % (
                        row["algorithm"],
                        row["trace_family"],
                        row["drop_source"],
                        int(row["drop_events_total"]),
                        int(row["drop_events_with_flow_tag"]),
                        float(row["flow_tag_coverage_ratio"]),
                    )
                )
        if len(congested_interfaces_df):
            f_out.write("Top saturated interfaces by samples_at_capacity:\n")
            top_congested = congested_interfaces_df.sort_values(
                ["samples_at_capacity", "max_queue_pkt"],
                ascending=[False, False],
            ).head(12)
            for _, row in top_congested.iterrows():
                f_out.write(
                    "  algorithm=%s link_type=%s interface=%s max_queue_pkt=%s "
                    "samples_at_capacity=%s affected_flows=%s affected_lost=%s "
                    "first=%s last=%s\n"
                    % (
                        row["algorithm"],
                        row["link_type"],
                        row["interface_key"],
                        row["max_queue_pkt"],
                        row["samples_at_capacity"],
                        row["estimated_affected_flow_count"],
                        row["estimated_affected_lost_packets"],
                        row["first_saturation_time_ns"],
                        row["last_saturation_time_ns"],
                    )
                )
        else:
            f_out.write("No queue interfaces reached configured packet capacity in the analyzed logs.\n")
        if len(loss_attribution_detailed_df):
            classified = loss_attribution_detailed_df[
                loss_attribution_detailed_df["lost_packets"] > 0
            ]
            if len(classified):
                f_out.write("Dominant associations among lossy flows:\n")
                counts = (
                    classified.groupby("dominant_association")["flow_id"]
                    .count()
                    .reset_index(name="flow_count")
                    .sort_values(["flow_count", "dominant_association"], ascending=[False, True])
                )
                for _, row in counts.iterrows():
                    f_out.write(
                        "  %s: %d flow(s)\n"
                        % (row["dominant_association"], int(row["flow_count"]))
                    )
        f_out.write(
            "Trace coverage limitations: physical queue drops require DropBeforeEnqueue "
            "or equivalent queue trace events; MacTxDrop can overlap queue overflow and "
            "is therefore diagnostic rather than additive. v2 retains its corridor/access "
            "proxy association for compatibility. v3 accumulates dynamic_state/fstate "
            "delta snapshots and requires same-window overlap between a replayed path and "
            "a saturated interface from *_queue_pkt_history.csv. Such overlap is inferred "
            "association, not physical drop proof.\n"
        )
        dst_818 = destination_df[
            (destination_df["dst"].astype(int) == 818)
            & (destination_df["total_lost_packets"] > 0)
        ] if len(destination_df) else pd.DataFrame()
        if len(dst_818):
            f_out.write(
                "dst=818 has synthetic loss in this run; compare its aggregate "
                "offered rate with GSL capacity and the GSL queue/drop rows above.\n"
            )
        f_out.write("\n")

        f_out.write("Warnings\n")
        f_out.write("-" * 40 + "\n")
        f_out.write(
            "The synthetic sent-minus-received loss should not be interpreted as a physical per-link drop trace.\n"
        )
        f_out.write(
            "The max queue occupancy summary for routing still covers tracked ISL queues only; GSL/access queues are summarized separately and are not used by the routing algorithms.\n"
        )
        f_out.write(
            "Routing/no-route drops are covered when logs_ns3/routing_drops.csv is present; generic IPv4 L3 drops still require a dedicated Ipv4L3Protocol drop hook.\n"
        )
        if gsl_capacity_warnings:
            for warning in gsl_capacity_warnings:
                f_out.write("WARNING: %s\n" % warning)
        f_out.write("\n")

        f_out.write("Interpretation limits\n")
        f_out.write("-" * 40 + "\n")
        f_out.write(
            "Use core/physical_drop_summary.csv for exact event counts and "
            "core/loss_attribution_breakdown_v3.csv for the canonical reconciled result.\n"
        )
        f_out.write(
            "ISL/GSL/Mixed saturation categories remain associated evidence, not "
            "physical proof. Investigate exact hooks or additional forwarding traces "
            "when unclassified loss remains high.\n"
        )


def write_statistics(
    path,
    run,
    summary_df,
    focus_df,
    pairwise_df,
    queue_df,
    loss_attribution_df,
    physical_trace_available,
    gsl_queue_available,
    udp_send_failure_available,
):
    loss_attribution = (
        "physical_drop_trace"
        if physical_trace_available
        else "synthetic_sent_minus_received"
    )
    with open(path, "w") as f_out:
        f_out.write("UDP/PDR Packet Delivery Statistics\n")
        f_out.write("=" * 40 + "\n\n")
        f_out.write(
            "Focus pair: %d (%s) <-> %d (%s) [%s]\n\n"
            % (
                run["src_node_id"],
                run.get("focus_src_name_if_available", ""),
                run["dst_node_id"],
                run.get("focus_dst_name_if_available", ""),
                run["focus_pair_tag"],
            )
        )

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
        f_out.write("background_flow_count = %d\n" % run["background_flow_count"])
        f_out.write(
            "per_flow_rate_reference_background_flow_count = %d\n"
            % run["per_flow_rate_reference_background_flow_count"]
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
            "physical_drop_trace_coverage = %s\n" % PHYSICAL_DROP_TRACE_COVERAGE
        )
        f_out.write(
            "gsl_queue_tracking_available = %s\n"
            % format_bool(gsl_queue_available)
        )
        f_out.write(
            "udp_send_failure_trace_available = %s\n"
            % format_bool(udp_send_failure_available)
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
                "background_flow_count",
                "per_flow_rate_reference_background_flow_count",
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
                "per_flow_target_rate_mbps",
                "total_target_rate_mbps",
                "background_target_rate_mbps",
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

        f_out.write("Loss attribution summary\n")
        f_out.write("-" * 40 + "\n")
        if len(loss_attribution_df):
            f_out.write(loss_attribution_df.to_string(index=False))
        else:
            f_out.write("No loss attribution summary available.")
        f_out.write("\n")


def analyze_run(
    run,
    algorithms,
    output_layout="standard",
    write_legacy_outputs=False,
    write_full_diagnostics=True,
    write_full_queue_saturation_timeline=False,
):
    comparison_dir = os.path.join("runs", run["name"], "comparison_packet_delivery")
    os.makedirs(comparison_dir, exist_ok=True)
    if output_layout == "standard":
        ensure_standard_layout(comparison_dir)
        archived = archive_flat_outputs(comparison_dir)
        if archived:
            print(
                "  > Preserved %d flat-layout output(s) in categorized directories"
                % len(archived)
            )
        write_deprecated_notes(comparison_dir)
        write_result_guide(comparison_dir)
    copied_diagnostics = copy_selection_diagnostics(
        run,
        comparison_dir,
        output_layout,
    )
    if copied_diagnostics:
        print("  > Linked flow-selection diagnostics under %s" % comparison_dir)

    def result_path(filename):
        return output_path(comparison_dir, filename, output_layout)

    per_flow_frames = []
    summary_rows = []
    focus_rows = []
    link_drop_frames = []
    queue_frames = []
    physical_drop_frames = []
    udp_send_failure_frames = []
    routing_drop_frames = []
    loss_attribution_detailed_frames = []
    flow_path_timeline_frames = []
    path_replay_diagnostic_frames = []
    loss_attribution_detailed_v3_frames = []
    loss_attribution_breakdown_v3_frames = []
    tag_coverage_diagnostic_frames = []
    congested_interface_frames = []
    queue_saturation_timeline_frames = []
    lhtr_diagnostic_frames = {
        filename: [] for filename in LHTR_DIAGNOSTIC_COLUMNS
    }
    gsl_queue_summary_rows = []
    gsl_capacity_by_algorithm = {}
    gsl_capacity_warnings = []
    physical_trace_available_any = False
    gsl_queue_available_any = False
    udp_send_failure_available_any = False
    routing_drop_available_any = False
    ipv4_l3_drop_available_any = False

    for algorithm in algorithms:
        algorithm_run_dir = os.path.join("runs", run["name"], algorithm)
        if not os.path.isdir(algorithm_run_dir):
            print("Skipping missing run directory: %s" % algorithm_run_dir)
            continue
        print("Processing %s" % algorithm_run_dir)

        if algorithm == "algorithm_lhtr":
            summaries = collect_lhtr_diagnostic_summaries(
                algorithm_run_dir,
                run["name"],
                algorithm,
            )
            for filename, frame in summaries.items():
                if len(frame):
                    lhtr_diagnostic_frames[filename].append(frame)

        gsl_capacity_mbps = read_gsl_capacity_mbps(algorithm_run_dir, run)
        gsl_capacity_by_algorithm[algorithm] = gsl_capacity_mbps
        if gsl_capacity_mbps is None:
            gsl_capacity_warnings.append(
                "Could not read gsl_data_rate_megabit_per_s for %s" % algorithm
            )
        gsl_queue_available_any = (
            gsl_queue_available_any or gsl_queue_tracking_available(algorithm_run_dir)
        )
        udp_send_failure_available_any = (
            udp_send_failure_available_any
            or udp_send_failure_trace_available(algorithm_run_dir)
        )
        routing_drop_available_any = (
            routing_drop_available_any
            or routing_drop_trace_available(algorithm_run_dir)
        )
        ipv4_l3_drop_available_any = (
            ipv4_l3_drop_available_any
            or ipv4_l3_drop_trace_available(algorithm_run_dir)
        )

        flows, udp_flows_path = build_udp_flows_csv(algorithm_run_dir, run)
        print("  > Wrote %s" % udp_flows_path)

        flows.insert(0, "algorithm", algorithm)
        flows.insert(0, "background_flow_count", run["background_flow_count"])
        flows.insert(
            0,
            "per_flow_rate_reference_background_flow_count",
            run["per_flow_rate_reference_background_flow_count"],
        )
        flows.insert(0, "load_level", run["load_level"])
        flows.insert(0, "traffic_mode", run["traffic_mode"])
        flows.insert(0, "focus_pair_tag", run["focus_pair_tag"])
        flows.insert(0, "focus_dst_node_id", run["dst_node_id"])
        flows.insert(0, "focus_src_node_id", run["src_node_id"])
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
                "focus_src_node_id",
                "focus_dst_node_id",
                "focus_pair_tag",
                "background_flow_count",
                "per_flow_rate_reference_background_flow_count",
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
        physical_drops = read_physical_link_drops(algorithm_run_dir)
        if len(physical_drops):
            physical_drops.insert(0, "algorithm", algorithm)
            physical_drops.insert(0, "run_name", run["name"])
            physical_drop_frames.append(physical_drops)
        else:
            physical_drops.insert(0, "algorithm", algorithm)
            physical_drops.insert(0, "run_name", run["name"])

        udp_send_failures = read_udp_send_failures(algorithm_run_dir)
        if len(udp_send_failures):
            udp_send_failures.insert(0, "algorithm", algorithm)
            udp_send_failures.insert(0, "run_name", run["name"])
            udp_send_failure_frames.append(udp_send_failures)
        else:
            udp_send_failures.insert(0, "algorithm", algorithm)
            udp_send_failures.insert(0, "run_name", run["name"])

        routing_drops = read_routing_drops(algorithm_run_dir)
        if len(routing_drops):
            routing_drops.insert(0, "algorithm", algorithm)
            routing_drops.insert(0, "run_name", run["name"])
            routing_drop_frames.append(routing_drops)
        else:
            routing_drops.insert(0, "algorithm", algorithm)
            routing_drops.insert(0, "run_name", run["name"])

        (
            queue_timeline,
            congested_interfaces,
            flow_isl_saturated_interfaces,
            flow_gsl_saturated_interfaces,
        ) = build_queue_saturation_outputs(
            algorithm_run_dir,
            run,
            algorithm,
            flows,
            write_full_timeline=write_full_queue_saturation_timeline,
        )
        if len(queue_timeline):
            queue_saturation_timeline_frames.append(queue_timeline)
        if len(congested_interfaces):
            congested_interface_frames.append(congested_interfaces)
        detailed = build_loss_attribution_detailed(
            algorithm,
            flows,
            physical_drops,
            udp_send_failures,
            routing_drops,
            flow_isl_saturated_interfaces,
            flow_gsl_saturated_interfaces,
            run,
        )
        loss_attribution_detailed_frames.append(detailed)
        (
            flow_path_timeline_v3,
            path_replay_diagnostics_v3,
            loss_attribution_detailed_v3,
            loss_attribution_breakdown_v3,
            tag_coverage_diagnostics_v3,
        ) = build_v3_for_algorithm(
            algorithm_run_dir,
            run,
            algorithm,
            flows,
            physical_drops,
            routing_drops,
            udp_send_failures,
        )
        flow_path_timeline_frames.append(flow_path_timeline_v3)
        path_replay_diagnostic_frames.append(path_replay_diagnostics_v3)
        loss_attribution_detailed_v3_frames.append(loss_attribution_detailed_v3)
        loss_attribution_breakdown_v3_frames.append(loss_attribution_breakdown_v3)
        tag_coverage_diagnostic_frames.append(tag_coverage_diagnostics_v3)

        gsl_queue_summary_rows.append(
            collect_gsl_queue_summary(algorithm_run_dir, algorithm)
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
    physical_drop_df = (
        pd.concat(physical_drop_frames, ignore_index=True)
        if physical_drop_frames
        else pd.DataFrame(columns=["run_name", "algorithm"] + PHYSICAL_DROP_COLUMNS)
    )
    udp_send_failure_df = (
        pd.concat(udp_send_failure_frames, ignore_index=True)
        if udp_send_failure_frames
        else pd.DataFrame(columns=["run_name", "algorithm"] + UDP_SEND_FAILURE_COLUMNS)
    )
    routing_drop_df = (
        pd.concat(routing_drop_frames, ignore_index=True)
        if routing_drop_frames
        else pd.DataFrame(columns=["run_name", "algorithm"] + ROUTING_DROP_COLUMNS)
    )
    loss_attribution_detailed_df = (
        pd.concat(loss_attribution_detailed_frames, ignore_index=True)
        if loss_attribution_detailed_frames
        else pd.DataFrame(columns=LOSS_ATTRIBUTION_DETAILED_COLUMNS)
    )
    flow_path_timeline_df = (
        pd.concat(flow_path_timeline_frames, ignore_index=True)
        if flow_path_timeline_frames
        else pd.DataFrame(columns=FLOW_PATH_TIMELINE_COLUMNS)
    )
    path_replay_diagnostics_df = (
        pd.concat(path_replay_diagnostic_frames, ignore_index=True)
        if path_replay_diagnostic_frames
        else pd.DataFrame(columns=PATH_REPLAY_DIAGNOSTIC_COLUMNS)
    )
    loss_attribution_detailed_v3_df = (
        pd.concat(loss_attribution_detailed_v3_frames, ignore_index=True)
        if loss_attribution_detailed_v3_frames
        else pd.DataFrame(columns=LOSS_ATTRIBUTION_DETAILED_V3_COLUMNS)
    )
    loss_attribution_breakdown_v3_df = (
        pd.concat(loss_attribution_breakdown_v3_frames, ignore_index=True)
        if loss_attribution_breakdown_v3_frames
        else pd.DataFrame(columns=LOSS_ATTRIBUTION_BREAKDOWN_V3_COLUMNS)
    )
    tag_coverage_diagnostics_df = (
        pd.concat(tag_coverage_diagnostic_frames, ignore_index=True)
        if tag_coverage_diagnostic_frames
        else pd.DataFrame(columns=TAG_COVERAGE_COLUMNS)
    )
    congested_interfaces_df = (
        pd.concat(congested_interface_frames, ignore_index=True)
        if congested_interface_frames
        else pd.DataFrame(columns=CONGESTED_INTERFACE_COLUMNS)
    )
    queue_saturation_timeline_df = (
        pd.concat(queue_saturation_timeline_frames, ignore_index=True)
        if queue_saturation_timeline_frames
        else pd.DataFrame(columns=QUEUE_SATURATION_TIMELINE_COLUMNS)
    )
    lhtr_diagnostic_dfs = {}
    for filename, columns in LHTR_DIAGNOSTIC_COLUMNS.items():
        frames = lhtr_diagnostic_frames[filename]
        lhtr_diagnostic_dfs[filename] = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=["run_name", "algorithm"] + columns)
        )
    gsl_queue_summary_df = pd.DataFrame(
        gsl_queue_summary_rows,
        columns=GSL_QUEUE_SUMMARY_COLUMNS,
    )
    physical_drop_summary_df = build_physical_drop_summary(physical_drop_df)
    loss_attribution_df = build_loss_attribution_summary(
        summary_df,
        physical_drop_df,
        udp_send_failure_df,
    )
    loss_attribution_breakdown_v2_df = build_loss_attribution_breakdown_v2(
        summary_df,
        loss_attribution_detailed_df,
        physical_drop_df,
        udp_send_failure_df,
        routing_drop_df,
    )
    pairwise_df = build_pairwise(summary_df, per_flow_df)
    affected_df = build_affected_flows(per_flow_df)
    top_loss_df = build_top_loss_flows(affected_df)
    destination_df = build_destination_loss_summary(
        per_flow_df,
        gsl_capacity_by_algorithm,
    )

    per_flow_df.to_csv(result_path("per_flow_delivery.csv"), index=False)
    summary_df.to_csv(result_path("summary_by_algorithm.csv"), index=False)
    focus_df.to_csv(result_path("focus_flow_delivery.csv"), index=False)
    pairwise_df.to_csv(result_path("pairwise_algorithm_comparison.csv"), index=False)
    affected_df.to_csv(result_path("affected_flows.csv"), index=False)
    top_loss_df.to_csv(result_path("top_loss_flows.csv"), index=False)
    destination_df.to_csv(result_path("destination_loss_summary.csv"), index=False)
    physical_drop_df.to_csv(result_path("physical_link_drops.csv"), index=False)
    udp_send_failure_df.to_csv(result_path("udp_send_failures.csv"), index=False)
    routing_drop_df.to_csv(result_path("routing_drops.csv"), index=False)
    physical_drop_summary_df.to_csv(result_path("physical_drop_summary.csv"), index=False)
    gsl_queue_summary_df.to_csv(result_path("gsl_queue_summary.csv"), index=False)
    path_replay_diagnostics_df.to_csv(
        result_path("path_replay_diagnostics.csv"),
        index=False,
    )
    loss_attribution_detailed_v3_df.to_csv(
        result_path("loss_attribution_detailed_v3.csv"),
        index=False,
    )
    loss_attribution_breakdown_v3_df.to_csv(
        result_path("loss_attribution_breakdown_v3.csv"),
        index=False,
    )
    tag_coverage_diagnostics_df.to_csv(
        result_path("tag_coverage_diagnostics.csv"),
        index=False,
    )
    congested_interfaces_df.to_csv(
        result_path("congested_interfaces_summary.csv"),
        index=False,
    )
    if write_full_diagnostics:
        flow_path_timeline_df.to_csv(
            result_path("flow_path_timeline.csv"),
            index=False,
        )
    timeline_filename = (
        "queue_saturation_timeline.csv"
        if write_full_queue_saturation_timeline
        else "queue_saturation_timeline_at_capacity.csv"
    )
    queue_saturation_timeline_df.to_csv(
        result_path(timeline_filename),
        index=False,
    )
    for filename, frame in lhtr_diagnostic_dfs.items():
        frame.to_csv(result_path(filename), index=False)
    if write_legacy_outputs or output_layout == "flat":
        link_drops_df.to_csv(result_path("link_drops.csv"), index=False)
        loss_attribution_df.to_csv(
            result_path("loss_attribution_summary.csv"),
            index=False,
        )
        loss_attribution_detailed_df.to_csv(
            result_path("loss_attribution_detailed.csv"),
            index=False,
        )
        loss_attribution_breakdown_v2_df.to_csv(
            result_path("loss_attribution_breakdown_v2.csv"),
            index=False,
        )
        if not physical_trace_available_any:
            link_drops_df.to_csv(
                result_path("synthetic_link_drops.csv"),
                index=False,
            )
    queue_df.to_csv(
        result_path("max_queue_occupancy_by_algorithm.csv"),
        index=False,
    )
    write_statistics(
        result_path("statistics.txt"),
        run,
        summary_df,
        focus_df,
        pairwise_df,
        queue_df,
        loss_attribution_df,
        physical_trace_available_any,
        gsl_queue_available_any,
        udp_send_failure_available_any,
    )
    write_loss_diagnostics(
        result_path("loss_diagnostics.txt"),
        run,
        summary_df,
        focus_df,
        affected_df,
        destination_df,
        queue_df,
        physical_drop_summary_df,
        gsl_queue_summary_df,
        loss_attribution_df,
        loss_attribution_breakdown_v2_df,
        loss_attribution_detailed_df,
        loss_attribution_breakdown_v3_df,
        loss_attribution_detailed_v3_df,
        path_replay_diagnostics_df,
        tag_coverage_diagnostics_df,
        congested_interfaces_df,
        physical_trace_available_any,
        gsl_queue_available_any,
        udp_send_failure_available_any,
        routing_drop_available_any,
        ipv4_l3_drop_available_any,
        gsl_capacity_warnings,
    )
    if output_layout == "standard":
        write_output_manifest(comparison_dir)
    print("  > Wrote comparison outputs under %s" % comparison_dir)
    return comparison_dir


def main():
    parser = build_arg_parser("Analyze UDP/PDR packet delivery results.")
    args = parser.parse_args()
    validate_focus_pair_arguments(parser, args)
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
    )

    seen_run_names = set()
    for run in runs:
        run = resolve_existing_run(run)
        if run["name"] in seen_run_names:
            continue
        seen_run_names.add(run["name"])
        analyze_run(
            run,
            algorithms,
            output_layout=args.output_layout,
            write_legacy_outputs=args.write_legacy_outputs,
            write_full_diagnostics=args.write_full_diagnostics,
            write_full_queue_saturation_timeline=(
                args.write_full_queue_saturation_timeline
            ),
        )


if __name__ == "__main__":
    main()
