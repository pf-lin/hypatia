import bisect
import csv
import json
import math
import os
import sys
from dataclasses import dataclass

os.environ.setdefault("MPLCONFIGDIR", "/tmp/hypatia-mpl-cache")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/hypatia-xdg-cache")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
os.makedirs(os.environ["XDG_CACHE_HOME"], exist_ok=True)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from astropy import units as u

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "../../.."))
SATGENPY_DIR = os.path.join(REPO_ROOT, "satgenpy")
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, SATGENPY_DIR)

from dynamic_path_replay import (
    apply_fstate_delta,
    list_fstate_snapshots,
    parse_fstate_delta,
    replay_path,
)
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
    write_output_manifest,
    write_result_guide,
)
from satgen.distance_tools import create_basic_ground_station_for_satellite_shadow
from satgen.ground_stations import read_ground_stations_extended
from satgen.isls import read_isls
from satgen.post_analysis.graph_tools import compute_path_length_without_graph
from satgen.tles import read_tles


SPEED_OF_LIGHT_M_PER_S = 299792458.0
DEFAULT_PACKET_SIZE_BYTES = 1500
LEGACY_FOCUS_PAIR = (738, 793)

RTT_TIMESERIES_COLUMNS = [
    "algorithm",
    "time_ns",
    "src",
    "dst",
    "direction",
    "forward_hop_count",
    "reverse_hop_count",
    "forward_prop_delay_ms",
    "reverse_prop_delay_ms",
    "propagation_only_rtt_ms",
    "forward_transmission_delay_ms",
    "reverse_transmission_delay_ms",
    "forward_queue_delay_ms",
    "reverse_queue_delay_ms",
    "queue_aware_rtt_ms",
    "queue_delay_source",
    "queue_samples_found_count",
    "queue_samples_missing_count",
    "missing_queue_hop_count",
    "queue_delay_missing_reason",
    "path_replay_status",
]

PATH_TIMESERIES_COLUMNS = [
    "algorithm",
    "time_ns",
    "src",
    "dst",
    "direction",
    "forward_path",
    "reverse_path",
    "forward_links",
    "reverse_links",
    "forward_hop_count",
    "reverse_hop_count",
    "forward_contains_target_corridor_if_available",
    "reverse_contains_target_corridor_if_available",
    "path_replay_status",
]

SUMMARY_COLUMNS = [
    "algorithm",
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

COMPONENT_COLUMNS = [
    "algorithm",
    "direction",
    "component",
    "mean_ms",
    "median_ms",
    "p95_ms",
    "max_ms",
    "sample_count",
]

COMPONENT_FIELDS = {
    "forward_prop_delay": "forward_prop_delay_ms",
    "reverse_prop_delay": "reverse_prop_delay_ms",
    "forward_transmission_delay": "forward_transmission_delay_ms",
    "reverse_transmission_delay": "reverse_transmission_delay_ms",
    "forward_queue_delay": "forward_queue_delay_ms",
    "reverse_queue_delay": "reverse_queue_delay_ms",
}

ALGORITHM_LABELS = {
    "algorithm_free_one_only_over_isls": "Baseline",
    "algorithm_queue_aware_over_isls": "Queue-aware",
    "algorithm_lohi": "LoHi",
    "algorithm_tlr": "TLR",
    "algorithm_lhtr": "LHTR",
}


@dataclass
class NetworkContext:
    network_dir: str
    satellites: list
    ground_stations: list
    list_isls: list
    epoch: object
    max_gsl_length_m: float
    max_isl_length_m: float

    @property
    def num_satellites(self):
        return len(self.satellites)

    @property
    def num_nodes(self):
        return len(self.satellites) + len(self.ground_stations)


@dataclass
class QueueSeries:
    end_times_ns: list
    values: list

    def latest_not_after(self, time_ns):
        index = bisect.bisect_right(self.end_times_ns, int(time_ns)) - 1
        if index < 0:
            return None
        return self.values[index]


def parse_comma_separated_seconds(value):
    if value is None:
        return None
    result = []
    for item in str(value).split(","):
        item = item.strip()
        if not item:
            continue
        seconds = float(item)
        if seconds < 0:
            raise ValueError("Sample times must be non-negative: %s" % item)
        result.append(seconds)
    if not result:
        raise ValueError("At least one sample time is required")
    return result


def build_sample_times_ns(
    simulation_end_time_s,
    traffic_stop_time_s,
    interval_s,
    explicit_times=None,
):
    upper_bound_s = min(float(simulation_end_time_s), float(traffic_stop_time_s))
    if explicit_times is not None:
        times_s = explicit_times
    else:
        if interval_s <= 0:
            raise ValueError("--rtt-sample-interval-s must be positive")
        count = int(math.floor(upper_bound_s / float(interval_s)))
        times_s = [index * float(interval_s) for index in range(count + 1)]
        if not math.isclose(times_s[-1], upper_bound_s):
            times_s.append(upper_bound_s)
    return sorted(
        {
            int(round(seconds * 1e9))
            for seconds in times_s
            if seconds <= float(simulation_end_time_s)
        }
    )


def _read_properties(path):
    values = {}
    with open(path) as f_in:
        for raw_line in f_in:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    return values


def _read_float_property(properties, key, default):
    try:
        return float(properties.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def discover_focus_pair(run_dir, algorithms, requested_src, requested_dst):
    for algorithm in algorithms:
        metadata_path = os.path.join(run_dir, algorithm, "run_metadata.json")
        if not os.path.exists(metadata_path):
            continue
        try:
            with open(metadata_path) as f_in:
                metadata = json.load(f_in)
            return (
                int(metadata["focus_src_node_id"]),
                int(metadata["focus_dst_node_id"]),
                "run_metadata.json",
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass

    for algorithm in algorithms:
        schedule_path = os.path.join(run_dir, algorithm, "udp_burst_schedule.csv")
        if not os.path.exists(schedule_path):
            continue
        focus_pairs = []
        with open(schedule_path, newline="") as f_in:
            for row in csv.reader(f_in):
                if len(row) >= 8 and "class=focus" in row[7]:
                    focus_pairs.append((int(row[1]), int(row[2])))
        if focus_pairs:
            return focus_pairs[0][0], focus_pairs[0][1], "udp_burst_schedule.csv"

    if requested_src is not None and requested_dst is not None:
        source = (
            "legacy_default"
            if (int(requested_src), int(requested_dst)) == LEGACY_FOCUS_PAIR
            else "step_3_cli"
        )
        return int(requested_src), int(requested_dst), source
    return LEGACY_FOCUS_PAIR[0], LEGACY_FOCUS_PAIR[1], "legacy_default"


def load_network_context(algorithm_run_dir):
    config = _read_properties(
        os.path.join(algorithm_run_dir, "config_ns3.properties")
    )
    network_dir = os.path.abspath(
        os.path.join(algorithm_run_dir, config["satellite_network_dir"])
    )
    ground_stations = read_ground_stations_extended(
        os.path.join(network_dir, "ground_stations.txt")
    )
    tles = read_tles(os.path.join(network_dir, "tles.txt"))
    satellites = tles["satellites"]
    list_isls = read_isls(
        os.path.join(network_dir, "isls.txt"),
        len(satellites),
    )
    description = _read_properties(os.path.join(network_dir, "description.txt"))
    return NetworkContext(
        network_dir=network_dir,
        satellites=satellites,
        ground_stations=ground_stations,
        list_isls=list_isls,
        epoch=tles["epoch"],
        max_gsl_length_m=float(description["max_gsl_length_m"]),
        max_isl_length_m=float(description["max_isl_length_m"]),
    )


def replay_focus_paths(dynamic_state_dir, sample_times_ns, src, dst, network):
    snapshots = list_fstate_snapshots(dynamic_state_dir)
    state = {}
    snapshot_index = 0
    parse_error = ""
    results = {}
    for time_ns in sorted(sample_times_ns):
        while (
            snapshot_index < len(snapshots)
            and snapshots[snapshot_index][0] <= time_ns
        ):
            _, path = snapshots[snapshot_index]
            try:
                apply_fstate_delta(state, parse_fstate_delta(path))
            except ValueError as exc:
                parse_error = str(exc)
            snapshot_index += 1
        forward = replay_path(
            state,
            src,
            dst,
            network.num_satellites,
            network.num_nodes,
        )
        reverse = replay_path(
            state,
            dst,
            src,
            network.num_satellites,
            network.num_nodes,
        )
        status = (
            "success"
            if forward.success and reverse.success and not parse_error
            else "forward:%s;reverse:%s%s"
            % (
                forward.status,
                reverse.status,
                ";fstate_parse_error" if parse_error else "",
            )
        )
        results[time_ns] = {
            "forward": forward,
            "reverse": reverse,
            "status": status,
        }
    return results


def scan_queue_history(path, link_type, target_keys):
    series = {}
    if not target_keys or not os.path.exists(path) or os.path.getsize(path) == 0:
        return series
    with open(path) as f_in:
        for line_number, raw_line in enumerate(f_in, 1):
            parts = raw_line.strip().split(",")
            if len(parts) != 5:
                continue
            try:
                from_node = int(parts[0])
                to_node = int(parts[1])
                interval_end_ns = int(parts[3])
                value = float(parts[4])
            except ValueError:
                continue
            key = "%s:%d->%d" % (link_type, from_node, to_node)
            if key not in target_keys:
                continue
            item = series.setdefault(key, QueueSeries([], []))
            item.end_times_ns.append(interval_end_ns)
            item.values.append(value)
    for item in series.values():
        if item.end_times_ns != sorted(item.end_times_ns):
            pairs = sorted(zip(item.end_times_ns, item.values))
            item.end_times_ns[:] = [pair[0] for pair in pairs]
            item.values[:] = [pair[1] for pair in pairs]
    return series


def load_queue_indexes(logs_dir, target_keys):
    byte_index = {}
    packet_index = {}
    for link_type in ["ISL", "GSL"]:
        link_keys = {key for key in target_keys if key.startswith(link_type + ":")}
        byte_path = os.path.join(
            logs_dir,
            "%s_queue_byte_history.csv" % link_type.lower(),
        )
        link_byte_index = scan_queue_history(byte_path, link_type, link_keys)
        byte_index.update(link_byte_index)
        fallback_keys = link_keys.difference(link_byte_index)
        if fallback_keys:
            packet_path = os.path.join(
                logs_dir,
                "%s_queue_pkt_history.csv" % link_type.lower(),
            )
            packet_index.update(
                scan_queue_history(packet_path, link_type, fallback_keys)
            )
    return byte_index, packet_index


def capacity_for_key(interface_key, config):
    prefix = interface_key.split(":", 1)[0].lower()
    property_name = "%s_data_rate_megabit_per_s" % prefix
    return _read_float_property(config, property_name, 10.0) * 1e6


def path_transmission_delay_s(interface_keys, config, packet_size_bytes):
    return sum(
        packet_size_bytes * 8.0 / capacity_for_key(key, config)
        for key in interface_keys
    )


def path_queue_delay_s(
    interface_keys,
    time_ns,
    config,
    packet_size_bytes,
    byte_index,
    packet_index,
):
    total_s = 0.0
    found = 0
    missing = 0
    sources = set()
    missing_keys = []
    for key in interface_keys:
        capacity_bps = capacity_for_key(key, config)
        byte_value = (
            byte_index[key].latest_not_after(time_ns)
            if key in byte_index
            else None
        )
        if byte_value is not None:
            total_s += byte_value * 8.0 / capacity_bps
            sources.add("queue_bytes")
            found += 1
            continue
        packet_value = (
            packet_index[key].latest_not_after(time_ns)
            if key in packet_index
            else None
        )
        if packet_value is not None:
            total_s += (
                packet_value * packet_size_bytes * 8.0 / capacity_bps
            )
            sources.add("queue_packets_fallback")
            found += 1
            continue
        sources.add("missing_queue_data")
        missing += 1
        missing_keys.append(key)
    return {
        "delay_s": total_s,
        "found": found,
        "missing": missing,
        "sources": sources,
        "missing_keys": missing_keys,
    }


def propagation_delay_s(path, time_ns, network):
    length_m = compute_path_length_without_graph(
        list(path),
        network.epoch,
        time_ns,
        network.satellites,
        network.ground_stations,
        network.list_isls,
        network.max_gsl_length_m,
        network.max_isl_length_m,
    )
    return length_m / SPEED_OF_LIGHT_M_PER_S


def load_target_corridor_edges(comparison_dir):
    path = os.path.join(
        comparison_dir,
        "diagnostics",
        "isl_corridor_load_summary.csv",
    )
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError):
        return None
    required = {"edge_from", "edge_to", "on_target_focus_corridor"}
    if not required.issubset(df.columns):
        return None
    mask = (
        df["on_target_focus_corridor"]
        .astype(str)
        .str.lower()
        .isin(["true", "1", "yes"])
    )
    return {
        (int(row["edge_from"]), int(row["edge_to"]))
        for _, row in df[mask].iterrows()
    }


def path_contains_corridor(path, corridor_edges):
    if corridor_edges is None:
        return ""
    return any(
        (int(path[index - 1]), int(path[index])) in corridor_edges
        for index in range(1, len(path))
    )


def _format_path(path):
    return ";".join(str(node) for node in path)


def _format_links(result):
    return ";".join(result.directional_hops)


def _queue_source_text(forward_queue, reverse_queue):
    sources = forward_queue["sources"].union(reverse_queue["sources"])
    order = ["queue_bytes", "queue_packets_fallback", "missing_queue_data"]
    return ";".join(source for source in order if source in sources)


def _missing_reason_text(forward_queue, reverse_queue):
    missing = forward_queue["missing_keys"] + reverse_queue["missing_keys"]
    if not missing:
        return ""
    return (
        "no completed queue sample at or before time for "
        + ";".join(sorted(set(missing)))
    )


def make_direction_rows(
    algorithm,
    time_ns,
    src,
    dst,
    forward,
    reverse,
    status,
    metrics,
    corridor_edges,
):
    directions = [
        (
            src,
            dst,
            "%d_to_%d" % (src, dst),
            forward,
            reverse,
            metrics["forward"],
            metrics["reverse"],
        ),
        (
            dst,
            src,
            "%d_to_%d" % (dst, src),
            reverse,
            forward,
            metrics["reverse"],
            metrics["forward"],
        ),
    ]
    rtt_rows = []
    path_rows = []
    for row_src, row_dst, direction, row_forward, row_reverse, fwd, rev in directions:
        valid = row_forward.success and row_reverse.success
        propagation_only = (
            fwd["prop_s"] + rev["prop_s"] if valid else float("nan")
        )
        queue_aware = (
            propagation_only
            + fwd["transmission_s"]
            + rev["transmission_s"]
            + fwd["queue"]["delay_s"]
            + rev["queue"]["delay_s"]
            if valid
            else float("nan")
        )
        rtt_rows.append(
            {
                "algorithm": algorithm,
                "time_ns": time_ns,
                "src": row_src,
                "dst": row_dst,
                "direction": direction,
                "forward_hop_count": max(len(row_forward.path) - 1, 0),
                "reverse_hop_count": max(len(row_reverse.path) - 1, 0),
                "forward_prop_delay_ms": fwd["prop_s"] * 1e3,
                "reverse_prop_delay_ms": rev["prop_s"] * 1e3,
                "propagation_only_rtt_ms": propagation_only * 1e3,
                "forward_transmission_delay_ms": fwd["transmission_s"] * 1e3,
                "reverse_transmission_delay_ms": rev["transmission_s"] * 1e3,
                "forward_queue_delay_ms": fwd["queue"]["delay_s"] * 1e3,
                "reverse_queue_delay_ms": rev["queue"]["delay_s"] * 1e3,
                "queue_aware_rtt_ms": queue_aware * 1e3,
                "queue_delay_source": _queue_source_text(
                    fwd["queue"], rev["queue"]
                ),
                "queue_samples_found_count": (
                    fwd["queue"]["found"] + rev["queue"]["found"]
                ),
                "queue_samples_missing_count": (
                    fwd["queue"]["missing"] + rev["queue"]["missing"]
                ),
                "missing_queue_hop_count": (
                    fwd["queue"]["missing"] + rev["queue"]["missing"]
                ),
                "queue_delay_missing_reason": _missing_reason_text(
                    fwd["queue"], rev["queue"]
                ),
                "path_replay_status": status,
            }
        )
        path_rows.append(
            {
                "algorithm": algorithm,
                "time_ns": time_ns,
                "src": row_src,
                "dst": row_dst,
                "direction": direction,
                "forward_path": _format_path(row_forward.path),
                "reverse_path": _format_path(row_reverse.path),
                "forward_links": _format_links(row_forward),
                "reverse_links": _format_links(row_reverse),
                "forward_hop_count": max(len(row_forward.path) - 1, 0),
                "reverse_hop_count": max(len(row_reverse.path) - 1, 0),
                "forward_contains_target_corridor_if_available": (
                    path_contains_corridor(row_forward.path, corridor_edges)
                ),
                "reverse_contains_target_corridor_if_available": (
                    path_contains_corridor(row_reverse.path, corridor_edges)
                ),
                "path_replay_status": status,
            }
        )
    return rtt_rows, path_rows


def analyze_algorithm(
    algorithm_run_dir,
    algorithm,
    src,
    dst,
    all_sample_times_ns,
    rtt_sample_times_ns,
    network,
    corridor_edges,
):
    config = _read_properties(
        os.path.join(algorithm_run_dir, "config_ns3.properties")
    )
    packet_size_bytes = int(
        round(
            _read_float_property(
                config,
                "queue_default_packet_size_bytes",
                os.environ.get(
                    "QUEUE_DEFAULT_PACKET_SIZE_BYTES",
                    DEFAULT_PACKET_SIZE_BYTES,
                ),
            )
        )
    )
    path_samples = replay_focus_paths(
        os.path.join(algorithm_run_dir, "dynamic_state"),
        all_sample_times_ns,
        src,
        dst,
        network,
    )
    target_keys = set()
    for sample in path_samples.values():
        target_keys.update(sample["forward"].interface_keys)
        target_keys.update(sample["reverse"].interface_keys)
    byte_index, packet_index = load_queue_indexes(
        os.path.join(algorithm_run_dir, "logs_ns3"),
        target_keys,
    )

    rtt_rows = []
    path_rows = []
    route_records = {}
    for time_ns in sorted(all_sample_times_ns):
        sample = path_samples[time_ns]
        metrics = {}
        for name in ["forward", "reverse"]:
            result = sample[name]
            if result.success:
                try:
                    prop_s = propagation_delay_s(result.path, time_ns, network)
                except ValueError:
                    prop_s = float("nan")
                    sample["status"] = sample["status"] + ";invalid_physical_hop"
                transmission_s = path_transmission_delay_s(
                    result.interface_keys,
                    config,
                    packet_size_bytes,
                )
                queue = path_queue_delay_s(
                    result.interface_keys,
                    time_ns,
                    config,
                    packet_size_bytes,
                    byte_index,
                    packet_index,
                )
            else:
                prop_s = float("nan")
                transmission_s = float("nan")
                queue = {
                    "delay_s": float("nan"),
                    "found": 0,
                    "missing": len(result.interface_keys),
                    "sources": {"missing_queue_data"},
                    "missing_keys": list(result.interface_keys),
                }
            metrics[name] = {
                "prop_s": prop_s,
                "transmission_s": transmission_s,
                "queue": queue,
            }
        rows, paths = make_direction_rows(
            algorithm,
            time_ns,
            src,
            dst,
            sample["forward"],
            sample["reverse"],
            sample["status"],
            metrics,
            corridor_edges,
        )
        route_records[time_ns] = {
            "sample": sample,
            "metrics": metrics,
            "canonical_rtt_row": rows[0],
        }
        if time_ns in rtt_sample_times_ns:
            rtt_rows.extend(rows)
            path_rows.extend(paths)
    return rtt_rows, path_rows, route_records, packet_size_bytes


def build_summary(rtt_df):
    rows = []
    if not len(rtt_df):
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    for (algorithm, direction), group in rtt_df.groupby(
        ["algorithm", "direction"],
        sort=False,
    ):
        valid = group[
            (group["path_replay_status"] == "success")
            & pd.to_numeric(
                group["propagation_only_rtt_ms"], errors="coerce"
            ).notna()
            & pd.to_numeric(
                group["queue_aware_rtt_ms"], errors="coerce"
            ).notna()
        ]
        prop = pd.to_numeric(valid["propagation_only_rtt_ms"])
        queue = pd.to_numeric(valid["queue_aware_rtt_ms"])
        rows.append(
            {
                "algorithm": algorithm,
                "direction": direction,
                "mean_propagation_only_rtt_ms": prop.mean(),
                "median_propagation_only_rtt_ms": prop.median(),
                "p95_propagation_only_rtt_ms": prop.quantile(0.95),
                "mean_queue_aware_rtt_ms": queue.mean(),
                "median_queue_aware_rtt_ms": queue.median(),
                "p95_queue_aware_rtt_ms": queue.quantile(0.95),
                "mean_forward_queue_delay_ms": pd.to_numeric(
                    valid["forward_queue_delay_ms"]
                ).mean(),
                "mean_reverse_queue_delay_ms": pd.to_numeric(
                    valid["reverse_queue_delay_ms"]
                ).mean(),
                "max_queue_aware_rtt_ms": queue.max(),
                "valid_sample_count": len(valid),
                "missing_sample_count": len(group) - len(valid),
            }
        )
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def build_components(rtt_df):
    rows = []
    if not len(rtt_df):
        return pd.DataFrame(columns=COMPONENT_COLUMNS)
    for (algorithm, direction), group in rtt_df.groupby(
        ["algorithm", "direction"],
        sort=False,
    ):
        for component, field in COMPONENT_FIELDS.items():
            values = pd.to_numeric(group[field], errors="coerce").dropna()
            rows.append(
                {
                    "algorithm": algorithm,
                    "direction": direction,
                    "component": component,
                    "mean_ms": values.mean(),
                    "median_ms": values.median(),
                    "p95_ms": values.quantile(0.95),
                    "max_ms": values.max(),
                    "sample_count": len(values),
                }
            )
    return pd.DataFrame(rows, columns=COMPONENT_COLUMNS)


def _algorithm_label(algorithm):
    return ALGORITHM_LABELS.get(
        algorithm,
        algorithm.replace("algorithm_", "").replace("_", " ").title(),
    )


def _save_figure(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_rtt_over_time(rtt_df, output_file, field, ylabel, title):
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for (algorithm, direction), group in rtt_df.groupby(
        ["algorithm", "direction"],
        sort=False,
    ):
        group = group.sort_values("time_ns")
        ax.plot(
            group["time_ns"] / 1e9,
            group[field],
            label="%s %s" % (_algorithm_label(algorithm), direction),
            linewidth=1.5,
        )
    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    _save_figure(fig, output_file)


def plot_summary(summary_df, output_file):
    grouped = (
        summary_df.groupby("algorithm", sort=False)[
            [
                "mean_propagation_only_rtt_ms",
                "mean_queue_aware_rtt_ms",
            ]
        ]
        .mean()
        .reset_index()
    )
    x = np.arange(len(grouped))
    width = 0.36
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(
        x - width / 2,
        grouped["mean_propagation_only_rtt_ms"],
        width,
        label="Propagation-only",
    )
    ax.bar(
        x + width / 2,
        grouped["mean_queue_aware_rtt_ms"],
        width,
        label="Queue-aware estimate",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(
        [_algorithm_label(value) for value in grouped["algorithm"]],
        rotation=15,
        ha="right",
    )
    ax.set_ylabel("Mean RTT (ms)")
    ax.set_title("Focus-flow estimated RTT by algorithm")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend()
    _save_figure(fig, output_file)


def plot_component_breakdown(components_df, output_file):
    averaged = (
        components_df.groupby(["algorithm", "component"], sort=False)["mean_ms"]
        .mean()
        .unstack(fill_value=0)
    )
    component_order = list(COMPONENT_FIELDS)
    x = np.arange(len(averaged))
    bottom = np.zeros(len(averaged))
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for component in component_order:
        values = (
            averaged[component].to_numpy()
            if component in averaged.columns
            else np.zeros(len(averaged))
        )
        ax.bar(x, values, bottom=bottom, label=component)
        bottom += values
    ax.set_xticks(x)
    ax.set_xticklabels(
        [_algorithm_label(value) for value in averaged.index],
        rotation=15,
        ha="right",
    )
    ax.set_ylabel("Mean component delay (ms)")
    ax.set_title("Focus-flow estimated RTT component breakdown")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    _save_figure(fig, output_file)


def plot_hop_counts(rtt_df, output_file):
    fig, ax = plt.subplots(figsize=(10, 5.5))
    canonical = rtt_df.drop_duplicates(["algorithm", "time_ns"])
    for algorithm, group in canonical.groupby("algorithm", sort=False):
        group = group.sort_values("time_ns")
        label = _algorithm_label(algorithm)
        ax.plot(
            group["time_ns"] / 1e9,
            group["forward_hop_count"],
            label=label + " forward",
        )
        ax.plot(
            group["time_ns"] / 1e9,
            group["reverse_hop_count"],
            linestyle="--",
            label=label + " reverse",
        )
    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Hop count")
    ax.set_title("Focus-flow forward and reverse hop count")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    _save_figure(fig, output_file)


def node_lat_lon(network, node_id, time_ns):
    if node_id < network.num_satellites:
        shadow = create_basic_ground_station_for_satellite_shadow(
            network.satellites[node_id],
            str(network.epoch),
            str(network.epoch + time_ns * u.ns),
        )
        return (
            float(shadow["latitude_degrees_str"]),
            float(shadow["longitude_degrees_str"]),
        )
    ground_station = network.ground_stations[node_id - network.num_satellites]
    return (
        float(ground_station["latitude_degrees_str"]),
        float(ground_station["longitude_degrees_str"]),
    )


def plot_connection(ax, from_lon, from_lat, to_lon, to_lat, **kwargs):
    if abs(to_lon - from_lon) <= 180:
        ax.plot([from_lon, to_lon], [from_lat, to_lat], **kwargs)
        return
    if from_lon < to_lon:
        from_lon += 360
    else:
        to_lon += 360
    longitudes = np.linspace(from_lon, to_lon, 50)
    latitudes = np.linspace(from_lat, to_lat, 50)
    normalized = ((longitudes + 180) % 360) - 180
    split_at = np.where(np.abs(np.diff(normalized)) > 180)[0] + 1
    for lon_part, lat_part in zip(
        np.split(normalized, split_at),
        np.split(latitudes, split_at),
    ):
        if len(lon_part) >= 2:
            ax.plot(lon_part, lat_part, **kwargs)


def draw_path(ax, network, path, time_ns, color, label, linestyle="-"):
    positions = {
        node: node_lat_lon(network, node, time_ns)
        for node in path
    }
    for index in range(1, len(path)):
        from_lat, from_lon = positions[path[index - 1]]
        to_lat, to_lon = positions[path[index]]
        plot_connection(
            ax,
            from_lon,
            from_lat,
            to_lon,
            to_lat,
            color=color,
            linewidth=1.8,
            linestyle=linestyle,
            label=label if index == 1 else None,
        )
    for node in path:
        lat, lon = positions[node]
        is_satellite = node < network.num_satellites
        ax.scatter(
            [lon],
            [lat],
            color=color,
            marker="^" if is_satellite else "o",
            s=25 if is_satellite else 42,
            zorder=3,
        )
        ax.text(lon + 1.2, lat + 0.6, str(node), fontsize=6, color=color)


def generate_route_plots(
    graphical_routes_dir,
    algorithm,
    route_records,
    route_times_ns,
    network,
):
    os.makedirs(graphical_routes_dir, exist_ok=True)
    written = []
    for time_ns in route_times_ns:
        if time_ns not in route_records:
            continue
        record = route_records[time_ns]
        sample = record["sample"]
        if not sample["forward"].success or not sample["reverse"].success:
            continue
        rtt_row = record["canonical_rtt_row"]
        views = [
            (
                "forward_path",
                [
                    (
                        sample["forward"].path,
                        "#c62828",
                        "Forward path",
                        "-",
                    )
                ],
            ),
            (
                "reverse_path",
                [
                    (
                        sample["reverse"].path,
                        "#1565c0",
                        "Reverse path",
                        "--",
                    )
                ],
            ),
            (
                "round_trip_path",
                [
                    (
                        sample["forward"].path,
                        "#c62828",
                        "Forward path",
                        "-",
                    ),
                    (
                        sample["reverse"].path,
                        "#1565c0",
                        "Reverse path",
                        "--",
                    ),
                ],
            ),
        ]
        for view_name, paths_to_draw in views:
            fig, ax = plt.subplots(figsize=(11, 5.5))
            ax.set_xlim(-180, 180)
            ax.set_ylim(-90, 90)
            ax.set_xlabel("Longitude (degrees)")
            ax.set_ylabel("Latitude (degrees)")
            ax.set_xticks(np.arange(-180, 181, 60))
            ax.set_yticks(np.arange(-90, 91, 30))
            ax.grid(True, alpha=0.25)
            for path, color, label, linestyle in paths_to_draw:
                draw_path(
                    ax,
                    network,
                    path,
                    time_ns,
                    color,
                    label,
                    linestyle=linestyle,
                )
            ax.legend(loc="lower left")
            ax.set_title(
                "%s focus %s at t=%.3gs\n"
                "propagation-only RTT=%.3f ms, queue-aware estimate=%.3f ms, "
                "hops=%d/%d"
                % (
                    _algorithm_label(algorithm),
                    view_name.replace("_", " "),
                    time_ns / 1e9,
                    rtt_row["propagation_only_rtt_ms"],
                    rtt_row["queue_aware_rtt_ms"],
                    rtt_row["forward_hop_count"],
                    rtt_row["reverse_hop_count"],
                )
            )
            time_tag = ("%g" % (time_ns / 1e9)).replace(".", "p")
            filename = "%s_focus_%s_t%ss.png" % (
                algorithm,
                view_name,
                time_tag,
            )
            output_file = os.path.join(graphical_routes_dir, filename)
            _save_figure(fig, output_file)
            written.append(output_file)
    return written


def write_diagnostics(
    path,
    focus_pair,
    focus_pair_source,
    rtt_df,
    packet_sizes,
    route_visualization_enabled,
):
    with open(path, "w") as f_out:
        f_out.write("UDP/PDR estimated RTT diagnostics\n")
        f_out.write("=================================\n")
        f_out.write(
            "focus_pair = %d -> %d\nfocus_pair_source = %s\n"
            % (focus_pair[0], focus_pair[1], focus_pair_source)
        )
        f_out.write("speed_of_light_m_per_s = %.1f\n" % SPEED_OF_LIGHT_M_PER_S)
        for algorithm, packet_size in packet_sizes.items():
            f_out.write(
                "packet_size_bytes[%s] = %d\n" % (algorithm, packet_size)
            )
        f_out.write(
            "queue_alignment = latest completed interval with "
            "interval_end_ns <= RTT sample time\n"
        )
        f_out.write(
            "missing_queue_policy = zero delay lower bound, explicitly marked "
            "in queue_samples_missing_count and queue_delay_missing_reason\n"
        )
        f_out.write(
            "queue_aware_rtt_is_packet_level_measured = false\n"
            "route_visualization_enabled = %s\n\n"
            % str(bool(route_visualization_enabled)).lower()
        )
        if not len(rtt_df):
            f_out.write("No RTT samples were generated.\n")
            return
        grouped = rtt_df.groupby("algorithm", sort=False).agg(
            sample_rows=("time_ns", "count"),
            missing_queue_hops=("queue_samples_missing_count", "sum"),
        )
        f_out.write("Queue data quality by algorithm\n")
        for algorithm, row in grouped.iterrows():
            f_out.write(
                "  %s: sample_rows=%d missing_queue_hops=%d\n"
                % (
                    algorithm,
                    int(row["sample_rows"]),
                    int(row["missing_queue_hops"]),
                )
            )
        failures = rtt_df[rtt_df["path_replay_status"] != "success"]
        f_out.write("\npath_replay_failure_rows = %d\n" % len(failures))


def analyze_run(run, algorithms, args):
    run_dir = os.path.join("runs", run["name"])
    comparison_dir = os.path.join(run_dir, "comparison_packet_delivery")
    ensure_standard_layout(comparison_dir)
    src, dst, focus_pair_source = discover_focus_pair(
        run_dir,
        algorithms,
        run.get("src_node_id"),
        run.get("dst_node_id"),
    )
    existing_algorithms = [
        algorithm
        for algorithm in algorithms
        if os.path.isdir(os.path.join(run_dir, algorithm))
    ]
    if not existing_algorithms:
        print("  > No algorithm run directories found under %s; skipping RTT" % run_dir)
        return

    network = load_network_context(
        os.path.join(run_dir, existing_algorithms[0])
    )
    explicit_rtt_times = parse_comma_separated_seconds(args.rtt_sample_times)
    rtt_sample_times_ns = build_sample_times_ns(
        run["simulation_end_time_s"],
        run["traffic_stop_time_s"],
        args.rtt_sample_interval_s,
        explicit_rtt_times,
    )
    route_times_s = (
        parse_comma_separated_seconds(args.route_plot_times)
        if args.enable_route_visualization
        else []
    )
    route_times_ns = sorted(
        {
            int(round(value * 1e9))
            for value in route_times_s
            if value <= float(run["simulation_end_time_s"])
        }
    )
    all_sample_times_ns = sorted(
        set(rtt_sample_times_ns).union(route_times_ns)
    )
    corridor_edges = load_target_corridor_edges(comparison_dir)

    all_rtt_rows = []
    all_path_rows = []
    packet_sizes = {}
    graphical_routes_dir = os.path.join(
        comparison_dir,
        "graphical_routes",
    )
    if args.enable_route_visualization:
        for filename in os.listdir(graphical_routes_dir):
            if not filename.endswith(".png"):
                continue
            if any(
                filename.startswith(algorithm + "_focus_")
                for algorithm in existing_algorithms
            ):
                os.remove(os.path.join(graphical_routes_dir, filename))
    for algorithm in existing_algorithms:
        algorithm_run_dir = os.path.join(run_dir, algorithm)
        print(
            "  > RTT %s: replaying %d sample times"
            % (algorithm, len(all_sample_times_ns))
        )
        rtt_rows, path_rows, route_records, packet_size = analyze_algorithm(
            algorithm_run_dir,
            algorithm,
            src,
            dst,
            all_sample_times_ns,
            set(rtt_sample_times_ns),
            network,
            corridor_edges,
        )
        all_rtt_rows.extend(rtt_rows)
        all_path_rows.extend(path_rows)
        packet_sizes[algorithm] = packet_size
        if args.enable_route_visualization:
            generate_route_plots(
                graphical_routes_dir,
                algorithm,
                route_records,
                route_times_ns,
                network,
            )

    rtt_df = pd.DataFrame(all_rtt_rows, columns=RTT_TIMESERIES_COLUMNS)
    path_df = pd.DataFrame(all_path_rows, columns=PATH_TIMESERIES_COLUMNS)
    summary_df = build_summary(rtt_df)
    components_df = build_components(rtt_df)

    rtt_path = output_path(
        comparison_dir,
        "udp_focus_rtt_timeseries.csv",
        args.output_layout,
    )
    path_path = output_path(
        comparison_dir,
        "udp_focus_path_timeseries.csv",
        args.output_layout,
    )
    summary_path = output_path(
        comparison_dir,
        "udp_rtt_summary_by_algorithm.csv",
        args.output_layout,
    )
    components_path = output_path(
        comparison_dir,
        "udp_rtt_components_by_algorithm.csv",
        args.output_layout,
    )
    diagnostics_path = output_path(
        comparison_dir,
        "udp_rtt_diagnostics.txt",
        args.output_layout,
    )
    for path in [
        rtt_path,
        path_path,
        summary_path,
        components_path,
        diagnostics_path,
    ]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    rtt_df.to_csv(rtt_path, index=False)
    path_df.to_csv(path_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    components_df.to_csv(components_path, index=False)
    write_diagnostics(
        diagnostics_path,
        (src, dst),
        focus_pair_source,
        rtt_df,
        packet_sizes,
        args.enable_route_visualization,
    )

    if len(rtt_df):
        plot_rtt_over_time(
            rtt_df,
            output_path(
                comparison_dir,
                "focus_rtt_over_time.png",
                args.output_layout,
            ),
            "propagation_only_rtt_ms",
            "Propagation-only RTT (ms)",
            "Focus-flow propagation-only RTT over time",
        )
        plot_rtt_over_time(
            rtt_df,
            output_path(
                comparison_dir,
                "focus_queue_aware_rtt_over_time.png",
                args.output_layout,
            ),
            "queue_aware_rtt_ms",
            "Queue-aware estimated RTT (ms)",
            "Focus-flow queue-aware estimated RTT over time",
        )
        plot_summary(
            summary_df,
            output_path(
                comparison_dir,
                "rtt_summary_by_algorithm.png",
                args.output_layout,
            ),
        )
        plot_component_breakdown(
            components_df,
            output_path(
                comparison_dir,
                "rtt_component_breakdown.png",
                args.output_layout,
            ),
        )
        plot_hop_counts(
            rtt_df,
            output_path(
                comparison_dir,
                "focus_forward_reverse_hop_count.png",
                args.output_layout,
            ),
        )
    if args.output_layout == "standard":
        write_result_guide(comparison_dir)
        write_output_manifest(comparison_dir)
    print("  > Wrote RTT outputs under %s" % comparison_dir)


def main():
    parser = build_arg_parser(
        "Generate UDP/PDR focus-flow estimated RTT and route outputs."
    )
    args = parser.parse_args()
    validate_focus_pair_arguments(parser, args)
    if not args.enable_rtt_analysis:
        print("RTT analysis disabled.")
        return
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
    seen = set()
    for run in runs:
        run = resolve_existing_run(run)
        if run["name"] in seen:
            continue
        seen.add(run["name"])
        analyze_run(run, algorithms, args)


if __name__ == "__main__":
    main()
