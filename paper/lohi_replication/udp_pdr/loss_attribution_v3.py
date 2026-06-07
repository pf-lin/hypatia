import math
import os
from collections import defaultdict

import pandas as pd

from dynamic_path_replay import build_flow_path_timeline


FLOW_PATH_TIMELINE_COLUMNS = [
    "algorithm",
    "flow_id",
    "src",
    "dst",
    "interval_start_ns",
    "interval_end_ns",
    "snapshot_time_ns",
    "replay_status",
    "path_nodes",
    "directional_hops",
    "directional_interface_keys",
    "isl_interface_keys",
    "gsl_interface_keys",
    "gsl_ambiguity",
    "hop_count",
    "diagnostic",
]

PATH_REPLAY_DIAGNOSTIC_COLUMNS = [
    "algorithm",
    "snapshot_time_ns",
    "status",
    "count",
    "total_attempts",
    "successful_attempts",
    "path_replay_success_ratio",
    "notes",
]

TAG_COVERAGE_COLUMNS = [
    "algorithm",
    "trace_family",
    "drop_source",
    "drop_events_total",
    "drop_events_with_flow_tag",
    "flow_tag_coverage_ratio",
]

LOSS_ATTRIBUTION_DETAILED_V3_COLUMNS = [
    "algorithm",
    "flow_id",
    "src",
    "dst",
    "flow_class",
    "sent_packets",
    "received_packets",
    "lost_packets",
    "exact_physical_queue_loss",
    "exact_physical_phy_loss",
    "exact_routing_loss",
    "exact_udp_send_failure_loss",
    "exact_attributed_loss",
    "exact_event_count_raw",
    "exact_event_overflow_count",
    "isl_saturation_associated_loss",
    "gsl_saturation_associated_loss",
    "mixed_saturation_associated_loss",
    "tail_in_flight_possible_loss",
    "unclassified_loss",
    "path_replay_attempts",
    "path_replay_successes",
    "path_replay_success_ratio",
    "flow_tag_coverage_ratio",
    "attribution_coverage_ratio",
    "attribution_confidence",
    "associated_interfaces",
    "saturation_overlap_windows",
    "reconciliation_error",
    "notes",
]

LOSS_ATTRIBUTION_BREAKDOWN_V3_COLUMNS = [
    "algorithm",
    "synthetic_lost_packets",
    "exact_physical_queue_loss",
    "exact_physical_phy_loss",
    "exact_routing_loss",
    "exact_udp_send_failure_loss",
    "exact_attributed_loss",
    "isl_saturation_associated_loss",
    "gsl_saturation_associated_loss",
    "mixed_saturation_associated_loss",
    "tail_in_flight_possible_loss",
    "unclassified_loss",
    "path_replay_success_ratio",
    "flow_tag_coverage_ratio",
    "attribution_coverage_ratio",
    "reconciliation_error_count",
    "attribution_confidence",
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


def read_network_node_counts(algorithm_run_dir):
    config = _read_properties(os.path.join(algorithm_run_dir, "config_ns3.properties"))
    network_dir = os.path.abspath(
        os.path.join(algorithm_run_dir, config["satellite_network_dir"])
    )
    with open(os.path.join(network_dir, "tles.txt")) as f_in:
        orbit_count, satellites_per_orbit = [
            int(value) for value in f_in.readline().split()
        ]
    num_satellites = orbit_count * satellites_per_orbit
    with open(os.path.join(network_dir, "ground_stations.txt")) as f_in:
        num_ground_stations = sum(1 for line in f_in if line.strip())
    return num_satellites, num_satellites + num_ground_stations


def _read_queue_history(logs_dir, link_type, capacity):
    path = os.path.join(
        logs_dir, "%s_queue_pkt_history.csv" % link_type.lower()
    )
    columns = ["from", "to", "interval_start_ns", "interval_end_ns", "queue_pkt"]
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame(columns=columns + ["interface_key", "link_type", "is_at_capacity"])
    try:
        df = pd.read_csv(path, header=None, names=columns)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns + ["interface_key", "link_type", "is_at_capacity"])
    for column in columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=columns).copy()
    df["from"] = df["from"].astype(int)
    df["to"] = df["to"].astype(int)
    df["interface_key"] = (
        link_type + ":" + df["from"].astype(str) + "->" + df["to"].astype(str)
    )
    df["link_type"] = link_type
    df["is_at_capacity"] = df["queue_pkt"] >= int(capacity)
    return df


def _bool_series(df, column):
    if column in df.columns:
        return df[column].astype(str).str.lower().isin(["true", "1", "yes"])
    flow = (
        pd.to_numeric(df["flow_id_if_available"], errors="coerce").notna()
        if "flow_id_if_available" in df.columns
        else pd.Series(False, index=df.index)
    )
    seq = (
        pd.to_numeric(
            df["packet_sequence_if_available"], errors="coerce"
        ).notna()
        if "packet_sequence_if_available" in df.columns
        else pd.Series(False, index=df.index)
    )
    return flow & seq


def build_tag_coverage(algorithm, physical_drops, routing_drops):
    rows = []
    families = [
        ("physical", physical_drops),
        ("routing", routing_drops),
    ]
    for trace_family, frame in families:
        if frame is None or len(frame) == 0:
            continue
        frame = frame.copy()
        frame["_tagged"] = _bool_series(frame, "flow_tag_available")
        source_column = "drop_source"
        for source, group in frame.groupby(source_column, dropna=False):
            total = int(len(group))
            tagged = int(group["_tagged"].sum())
            rows.append(
                {
                    "algorithm": algorithm,
                    "trace_family": trace_family,
                    "drop_source": str(source),
                    "drop_events_total": total,
                    "drop_events_with_flow_tag": tagged,
                    "flow_tag_coverage_ratio": tagged / float(total) if total else math.nan,
                }
            )
    return pd.DataFrame(rows, columns=TAG_COVERAGE_COLUMNS)


def _to_optional_int(value):
    try:
        if pd.isna(value) or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _packet_key(row, flow_column, sequence_column, uid_column):
    flow_id = _to_optional_int(row.get(flow_column))
    sequence = _to_optional_int(row.get(sequence_column))
    if flow_id is not None and sequence is not None:
        return "flow:%d:sequence:%d" % (flow_id, sequence), flow_id
    uid = _to_optional_int(row.get(uid_column))
    if flow_id is not None and uid is not None:
        return "flow:%d:uid:%d" % (flow_id, uid), flow_id
    return None, flow_id


def _collect_exact_events(physical_drops, routing_drops, send_failures):
    events = []
    if physical_drops is not None and len(physical_drops):
        tagged = physical_drops[_bool_series(physical_drops, "flow_tag_available")]
        category_by_source = {
            "QueueDrop": "exact_physical_queue_loss",
            "DropBeforeEnqueue": "exact_physical_queue_loss",
            "PhyTxDrop": "exact_physical_phy_loss",
            "PhyRxDrop": "exact_physical_phy_loss",
        }
        for _, row in tagged.iterrows():
            category = category_by_source.get(str(row.get("drop_source", "")))
            if category is None:
                continue
            key, flow_id = _packet_key(
                row,
                "flow_id_if_available",
                "packet_sequence_if_available",
                "packet_uid_if_available",
            )
            if key is not None:
                events.append((key, flow_id, category, int(row.get("time_ns", 0) or 0)))

    if routing_drops is not None and len(routing_drops):
        tagged = routing_drops[_bool_series(routing_drops, "flow_tag_available")]
        for _, row in tagged.iterrows():
            key, flow_id = _packet_key(
                row,
                "flow_id_if_available",
                "packet_sequence_if_available",
                "packet_uid_if_available",
            )
            if key is not None:
                events.append((key, flow_id, "exact_routing_loss", int(row.get("time_ns", 0) or 0)))

    if send_failures is not None and len(send_failures):
        for _, row in send_failures.iterrows():
            key, flow_id = _packet_key(
                row,
                "flow_id",
                "packet_sequence_if_available",
                "packet_uid_if_available",
            )
            if key is not None:
                events.append(
                    (
                        key,
                        flow_id,
                        "exact_udp_send_failure_loss",
                        int(row.get("time_ns", 0) or 0),
                    )
                )

    priority = {
        "exact_routing_loss": 0,
        "exact_physical_queue_loss": 1,
        "exact_physical_phy_loss": 2,
        "exact_udp_send_failure_loss": 3,
    }
    deduplicated = {}
    for event in sorted(events, key=lambda item: (item[0], priority[item[2]], item[3])):
        deduplicated.setdefault(event[0], event)
    by_flow = defaultdict(list)
    for event in deduplicated.values():
        by_flow[event[1]].append(event)
    return by_flow


def _build_saturation_overlap(path_timeline, queue_history):
    saturated_by_key = defaultdict(list)
    saturated = queue_history[queue_history["is_at_capacity"] == True]
    for _, row in saturated.iterrows():
        saturated_by_key[str(row["interface_key"])].append(
            (
                int(row["interval_start_ns"]),
                int(row["interval_end_ns"]),
                str(row["link_type"]),
            )
        )

    overlap_by_flow = defaultdict(list)
    successful = path_timeline[path_timeline["replay_status"] == "success"]
    for _, row in successful.iterrows():
        path_start = int(row["interval_start_ns"])
        path_end = int(row["interval_end_ns"])
        for interface_key in str(row["directional_interface_keys"]).split(";"):
            if not interface_key:
                continue
            for queue_start, queue_end, link_type in saturated_by_key.get(interface_key, []):
                overlap_start = max(path_start, queue_start)
                overlap_end = min(path_end, queue_end)
                if overlap_end <= overlap_start:
                    continue
                overlap_by_flow[int(row["flow_id"])].append(
                    (link_type, interface_key, overlap_start, overlap_end)
                )
    return overlap_by_flow


def _path_diagnostics(algorithm, path_timeline, parser_diagnostics):
    total = int(len(path_timeline))
    successful = int((path_timeline["replay_status"] == "success").sum()) if total else 0
    ratio = successful / float(total) if total else 0.0
    rows = []
    if total:
        for status, group in path_timeline.groupby("replay_status"):
            rows.append(
                {
                    "algorithm": algorithm,
                    "snapshot_time_ns": "",
                    "status": status,
                    "count": int(len(group)),
                    "total_attempts": total,
                    "successful_attempts": successful,
                    "path_replay_success_ratio": ratio,
                    "notes": "",
                }
            )
    for diagnostic in parser_diagnostics:
        rows.append(
            {
                "algorithm": algorithm,
                "snapshot_time_ns": diagnostic.get("snapshot_time_ns", ""),
                "status": diagnostic.get("status", "parse_error"),
                "count": diagnostic.get("count", 1),
                "total_attempts": total,
                "successful_attempts": successful,
                "path_replay_success_ratio": ratio,
                "notes": diagnostic.get("notes", ""),
            }
        )
    return pd.DataFrame(rows, columns=PATH_REPLAY_DIAGNOSTIC_COLUMNS)


def _summarize_overlap_windows(overlaps):
    windows_by_interface = defaultdict(set)
    for _, interface_key, start_ns, end_ns in overlaps:
        windows_by_interface[interface_key].add((start_ns, end_ns))

    summaries = []
    for interface_key, windows in sorted(windows_by_interface.items()):
        ordered = sorted(windows)
        first_start, first_end = ordered[0]
        last_start, last_end = ordered[-1]
        summary = "%s[count=%d,first=%d-%d" % (
            interface_key,
            len(ordered),
            first_start,
            first_end,
        )
        if len(ordered) > 1:
            summary += ",last=%d-%d" % (last_start, last_end)
        summaries.append(summary + "]")
    return summaries


def build_v3_for_algorithm(
    algorithm_run_dir,
    run,
    algorithm,
    flows,
    physical_drops,
    routing_drops,
    send_failures,
):
    num_satellites, num_nodes = read_network_node_counts(algorithm_run_dir)
    timeline_rows, parser_diagnostics = build_flow_path_timeline(
        os.path.join(algorithm_run_dir, "dynamic_state"),
        flows,
        algorithm,
        num_satellites,
        num_nodes,
        int(run["simulation_end_time_ns"]),
    )
    path_timeline = pd.DataFrame(timeline_rows, columns=FLOW_PATH_TIMELINE_COLUMNS)
    path_diagnostics = _path_diagnostics(
        algorithm, path_timeline, parser_diagnostics
    )

    config = _read_properties(os.path.join(algorithm_run_dir, "config_ns3.properties"))
    isl_capacity = int(config.get("isl_max_queue_size_pkts", run["queue_size_pkt"]))
    gsl_capacity = int(config.get("gsl_max_queue_size_pkts", run["queue_size_pkt"]))
    logs_dir = os.path.join(algorithm_run_dir, "logs_ns3")
    queue_history = pd.concat(
        [
            _read_queue_history(logs_dir, "ISL", isl_capacity),
            _read_queue_history(logs_dir, "GSL", gsl_capacity),
        ],
        ignore_index=True,
    )
    overlap_by_flow = _build_saturation_overlap(path_timeline, queue_history)
    exact_by_flow = _collect_exact_events(
        physical_drops, routing_drops, send_failures
    )
    tag_coverage = build_tag_coverage(algorithm, physical_drops, routing_drops)
    tag_total = int(tag_coverage["drop_events_total"].sum()) if len(tag_coverage) else 0
    tag_with_flow = (
        int(tag_coverage["drop_events_with_flow_tag"].sum())
        if len(tag_coverage)
        else 0
    )
    tag_ratio = tag_with_flow / float(tag_total) if tag_total else math.nan

    detailed_rows = []
    category_names = [
        "exact_physical_queue_loss",
        "exact_physical_phy_loss",
        "exact_routing_loss",
        "exact_udp_send_failure_loss",
    ]
    for _, flow in flows.sort_values("flow_id").iterrows():
        flow_id = int(flow["flow_id"])
        lost = int(flow["lost_packets"])
        raw_events = exact_by_flow.get(flow_id, [])
        raw_counts = {name: 0 for name in category_names}
        for event in raw_events:
            raw_counts[event[2]] += 1
        raw_total = sum(raw_counts.values())
        remaining_for_exact = lost
        assigned_counts = {}
        for name in category_names:
            assigned = min(raw_counts[name], remaining_for_exact)
            assigned_counts[name] = assigned
            remaining_for_exact -= assigned
        exact_total = sum(assigned_counts.values())
        exact_overflow = max(raw_total - exact_total, 0)
        residual = max(lost - exact_total, 0)

        overlaps = overlap_by_flow.get(flow_id, [])
        overlap_types = {item[0] for item in overlaps}
        isl_assoc = 0
        gsl_assoc = 0
        mixed_assoc = 0
        tail_possible = 0
        unclassified = 0
        if residual:
            if overlap_types == {"ISL", "GSL"}:
                mixed_assoc = residual
            elif overlap_types == {"ISL"}:
                isl_assoc = residual
            elif overlap_types == {"GSL"}:
                gsl_assoc = residual
            elif not bool(run.get("drain_time_enabled", False)):
                tail_possible = residual
            else:
                unclassified = residual

        flow_paths = path_timeline[path_timeline["flow_id"] == flow_id]
        attempts = int(len(flow_paths))
        successes = (
            int((flow_paths["replay_status"] == "success").sum())
            if attempts
            else 0
        )
        path_ratio = successes / float(attempts) if attempts else 0.0
        associated_interfaces = sorted({item[1] for item in overlaps})
        overlap_windows = _summarize_overlap_windows(overlaps)
        reconciled = (
            exact_total
            + isl_assoc
            + gsl_assoc
            + mixed_assoc
            + tail_possible
            + unclassified
        )
        reconciliation_error = ""
        if reconciled != lost:
            reconciliation_error = "classified=%d synthetic_lost=%d" % (
                reconciled,
                lost,
            )
        if exact_overflow:
            overflow_note = "deduplicated exact events exceed synthetic loss by %d" % exact_overflow
            reconciliation_error = (
                reconciliation_error + "; " + overflow_note
                if reconciliation_error
                else overflow_note
            )

        if lost == 0:
            confidence = "not_applicable"
        elif exact_total == lost and not exact_overflow:
            confidence = "high"
        elif isl_assoc or gsl_assoc or mixed_assoc:
            confidence = "medium"
        else:
            confidence = "low"
        coverage = 1.0 - (unclassified / float(lost)) if lost else 1.0
        notes = []
        if overlaps:
            notes.append("saturation_association_is_time_and_path_overlap_not_drop_proof")
        if not os.path.exists(os.path.join(logs_dir, "isl_queue_pkt_history.csv")):
            notes.append("isl_queue_history_missing")
        if not os.path.exists(os.path.join(logs_dir, "gsl_queue_pkt_history.csv")):
            notes.append("gsl_queue_history_missing")
        if any(
            str(value).lower() == "true"
            for value in flow_paths.get("gsl_ambiguity", pd.Series(dtype=str))
        ):
            notes.append("gsl_shared_channel_queue_key_is_ambiguous")

        detailed_rows.append(
            {
                "algorithm": algorithm,
                "flow_id": flow_id,
                "src": int(flow["src"]),
                "dst": int(flow["dst"]),
                "flow_class": flow["flow_class"],
                "sent_packets": int(flow["sent_packets"]),
                "received_packets": int(flow["received_packets"]),
                "lost_packets": lost,
                **assigned_counts,
                "exact_attributed_loss": exact_total,
                "exact_event_count_raw": raw_total,
                "exact_event_overflow_count": exact_overflow,
                "isl_saturation_associated_loss": isl_assoc,
                "gsl_saturation_associated_loss": gsl_assoc,
                "mixed_saturation_associated_loss": mixed_assoc,
                "tail_in_flight_possible_loss": tail_possible,
                "unclassified_loss": unclassified,
                "path_replay_attempts": attempts,
                "path_replay_successes": successes,
                "path_replay_success_ratio": path_ratio,
                "flow_tag_coverage_ratio": tag_ratio,
                "attribution_coverage_ratio": coverage,
                "attribution_confidence": confidence,
                "associated_interfaces": ";".join(associated_interfaces),
                "saturation_overlap_windows": ";".join(overlap_windows),
                "reconciliation_error": reconciliation_error,
                "notes": "|".join(notes),
            }
        )

    detailed = pd.DataFrame(
        detailed_rows, columns=LOSS_ATTRIBUTION_DETAILED_V3_COLUMNS
    )
    totals = {
        column: int(detailed[column].sum())
        for column in [
            "lost_packets",
            "exact_physical_queue_loss",
            "exact_physical_phy_loss",
            "exact_routing_loss",
            "exact_udp_send_failure_loss",
            "exact_attributed_loss",
            "isl_saturation_associated_loss",
            "gsl_saturation_associated_loss",
            "mixed_saturation_associated_loss",
            "tail_in_flight_possible_loss",
            "unclassified_loss",
        ]
    }
    path_attempts = int(detailed["path_replay_attempts"].sum())
    path_successes = int(detailed["path_replay_successes"].sum())
    path_ratio = path_successes / float(path_attempts) if path_attempts else 0.0
    lost_total = totals["lost_packets"]
    coverage = (
        1.0 - totals["unclassified_loss"] / float(lost_total)
        if lost_total
        else 1.0
    )
    error_count = int((detailed["reconciliation_error"].astype(str) != "").sum())
    if lost_total == 0:
        confidence = "not_applicable"
    elif totals["exact_attributed_loss"] == lost_total and error_count == 0:
        confidence = "high"
    elif (
        totals["isl_saturation_associated_loss"]
        + totals["gsl_saturation_associated_loss"]
        + totals["mixed_saturation_associated_loss"]
    ):
        confidence = "medium"
    else:
        confidence = "low"
    breakdown = pd.DataFrame(
        [
            {
                "algorithm": algorithm,
                "synthetic_lost_packets": lost_total,
                **{key: value for key, value in totals.items() if key != "lost_packets"},
                "path_replay_success_ratio": path_ratio,
                "flow_tag_coverage_ratio": tag_ratio,
                "attribution_coverage_ratio": coverage,
                "reconciliation_error_count": error_count,
                "attribution_confidence": confidence,
                "notes": (
                    "exact categories use tagged stable packet keys; saturation "
                    "categories require overlapping replay path and *_queue_pkt_history.csv"
                ),
            }
        ],
        columns=LOSS_ATTRIBUTION_BREAKDOWN_V3_COLUMNS,
    )
    return (
        path_timeline,
        path_diagnostics,
        detailed,
        breakdown,
        tag_coverage,
    )
