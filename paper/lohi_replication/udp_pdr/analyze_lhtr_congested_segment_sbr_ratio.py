#!/usr/bin/env python3

import argparse
import math
import os
from collections import defaultdict
from dataclasses import dataclass, field
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
    / "lhtr_congested_segment_sbr_ratio"
)

SCENARIO_ORDER = ["H40", "H60", "H80", "H90", "H100+"]

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
    "top_fraction",
    "candidate_segment_count",
    "top_segment_count",
    "top_segments",
    "segment_congestion_metric",
    "global_br_selected",
    "global_sbr_selected",
    "global_fallback",
    "global_no_route",
    "global_sbr_ratio",
    "global_sbr_ratio_no_fallback",
    "sample_global_total",
    "sample_global_br_selected",
    "sample_global_sbr_selected",
    "sample_global_fallback",
    "sample_global_no_route",
    "sample_global_sbr_ratio",
    "sample_global_sbr_ratio_no_fallback",
    "target_corridor_decision_count",
    "target_corridor_br_selected",
    "target_corridor_sbr_selected",
    "target_corridor_fallback",
    "target_corridor_no_route",
    "target_corridor_sbr_ratio",
    "target_corridor_sbr_ratio_no_fallback",
    "top25_segment_decision_count",
    "top25_segment_br_selected",
    "top25_segment_sbr_selected",
    "top25_segment_fallback",
    "top25_segment_no_route",
    "top25_segment_sbr_ratio",
    "top25_segment_sbr_ratio_no_fallback",
    "selected_path_top25_decision_count",
    "selected_path_top25_br_selected",
    "selected_path_top25_sbr_selected",
    "selected_path_top25_fallback",
    "selected_path_top25_no_route",
    "selected_path_top25_sbr_ratio",
    "selected_path_top25_sbr_ratio_no_fallback",
    "br_or_selected_path_top25_decision_count",
    "br_or_selected_path_top25_br_selected",
    "br_or_selected_path_top25_sbr_selected",
    "br_or_selected_path_top25_fallback",
    "br_or_selected_path_top25_no_route",
    "br_or_selected_path_top25_sbr_ratio",
    "br_or_selected_path_top25_sbr_ratio_no_fallback",
    "sbr_decision_share_on_top25_segments",
    "decision_share_on_top25_segments",
    "sbr_decision_share_on_target_corridor",
    "decision_share_on_target_corridor",
    "sbr_decision_share_on_selected_path_top25",
    "decision_share_on_selected_path_top25",
    "decision_sample_scope",
]

SEGMENT_DETAIL_COLUMNS = [
    "scenario_id",
    "scenario_duration_id",
    "hotspot_label",
    "segment",
    "edge_from",
    "edge_to",
    "is_top25_segment",
    "top_segment_rank",
    "selected_flow_count",
    "estimated_offered_rate_mbps",
    "isl_capacity_mbps",
    "scheduled_load_ratio",
    "edge_rank_by_load",
    "mean_utilization",
    "p95_utilization",
    "max_utilization",
    "utilization_sample_count",
    "yellow_count",
    "red_count",
    "yellow_plus_red_count",
    "br_path_decision_count",
    "br_path_br_selected",
    "br_path_sbr_selected",
    "br_path_fallback",
    "br_path_no_route",
    "br_path_sbr_ratio",
    "br_path_sbr_ratio_no_fallback",
    "sbr_share_of_sample_global_sbr",
    "decision_share_of_sample_global_decisions",
]


@dataclass
class DecisionCounts:
    total: int = 0
    br: int = 0
    sbr: int = 0
    fallback: int = 0
    no_route: int = 0

    def add(self, route_class):
        self.total += 1
        if route_class == "sbr":
            self.sbr += 1
        elif route_class == "br":
            self.br += 1
        elif route_class == "no_route":
            self.no_route += 1
        else:
            self.fallback += 1

    def sbr_ratio(self):
        return safe_divide(self.sbr, self.total)

    def sbr_ratio_no_fallback(self):
        return safe_divide(self.sbr, self.br + self.sbr)


@dataclass
class DecisionScanResult:
    sample_global: DecisionCounts = field(default_factory=DecisionCounts)
    target_corridor: DecisionCounts = field(default_factory=DecisionCounts)
    top25_segment: DecisionCounts = field(default_factory=DecisionCounts)
    selected_path_top25: DecisionCounts = field(default_factory=DecisionCounts)
    br_or_selected_path_top25: DecisionCounts = field(default_factory=DecisionCounts)
    per_top_segment: dict = field(default_factory=lambda: defaultdict(DecisionCounts))
    samples: list = field(default_factory=list)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Measure LHTR SBR selection ratios on congested corridor segments "
            "instead of congested time windows."
        )
    )
    parser.add_argument(
        "--scenario",
        help="Optional scenario filter, e.g. H80.",
    )
    parser.add_argument(
        "--duration-s",
        type=float,
        help="Optional simulation duration filter, e.g. 200.",
    )
    parser.add_argument(
        "--top-fraction",
        type=float,
        default=0.25,
        help="Fraction of target-corridor segments selected as congested. Default: 0.25.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output analysis directory.",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=200000,
        help="Decision-log rows read per chunk. Default: 200000.",
    )
    args = parser.parse_args()
    if not 0 < args.top_fraction <= 1:
        parser.error("--top-fraction must satisfy 0 < value <= 1")
    if args.duration_s is not None and args.duration_s <= 0:
        parser.error("--duration-s must be positive")
    if args.chunksize <= 0:
        parser.error("--chunksize must be positive")
    return args


def safe_divide(numerator, denominator):
    if denominator is None or denominator == 0:
        return math.nan
    return float(numerator) / float(denominator)


def weighted_quantile(values, weights, quantile):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    values = values[mask]
    weights = weights[mask]
    if len(values) == 0:
        return 0.0
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    cumulative = np.cumsum(weights)
    cutoff = quantile * weights.sum()
    index = int(np.searchsorted(cumulative, cutoff, side="left"))
    index = min(index, len(values) - 1)
    return float(values[index])


def read_csv_if_exists(path, **kwargs):
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def scenario_sort_key(row):
    scenario = str(row["scenario_id"])
    try:
        scenario_index = SCENARIO_ORDER.index(scenario)
    except ValueError:
        scenario_index = len(SCENARIO_ORDER)
    return (float(row["duration_s"]), scenario_index, scenario)


def load_manifest():
    rows = []
    manifest_60 = RUNS_DIR / "hotspot_5level_60s_formal_manifest.csv"
    if manifest_60.is_file():
        frame = pd.read_csv(manifest_60)
        for _, row in frame.iterrows():
            if str(row.get("status", "")).lower() != "complete":
                continue
            rows.append(
                {
                    "scenario_id": row["scenario_id"],
                    "duration_s": 60.0,
                    "traffic_stop_s": 58.0,
                    "duration_label": "60s",
                    "load_level": row.get("load_level", math.nan),
                    "background_flow_count": row.get(
                        "background_flow_count", math.nan
                    ),
                    "hotspot_reference_load_percent": row.get(
                        "hotspot_reference_load_percent", math.nan
                    ),
                    "global_offered_isl_load_percent": row.get(
                        "global_offered_isl_load_percent", math.nan
                    ),
                    "hotspot_label": row.get("label", ""),
                    "run_folder": row["run_folder"],
                }
            )

    manifest_200 = RUNS_DIR / "hotspot_5level_200s_formal_manifest.csv"
    if manifest_200.is_file():
        frame = pd.read_csv(manifest_200)
        for _, row in frame.iterrows():
            if str(row.get("status", "")).lower() != "complete":
                continue
            duration_s = float(row.get("simulation_end_time_s", 200.0))
            traffic_stop_s = float(row.get("traffic_stop_time_s", duration_s))
            rows.append(
                {
                    "scenario_id": row["scenario_id"],
                    "duration_s": duration_s,
                    "traffic_stop_s": traffic_stop_s,
                    "duration_label": row.get("duration_label", "%gs" % duration_s),
                    "load_level": row.get("load_level", math.nan),
                    "background_flow_count": row.get(
                        "background_flow_count", math.nan
                    ),
                    "hotspot_reference_load_percent": row.get(
                        "hotspot_reference_load_percent", math.nan
                    ),
                    "global_offered_isl_load_percent": row.get(
                        "global_offered_isl_load_percent", math.nan
                    ),
                    "hotspot_label": row.get("label", ""),
                    "run_folder": row["run_folder"],
                }
            )

    rows.sort(key=scenario_sort_key)
    return rows


def filter_runs(runs, scenario, duration_s):
    selected = []
    for row in runs:
        if scenario and str(row["scenario_id"]) != scenario:
            continue
        if duration_s is not None and abs(float(row["duration_s"]) - duration_s) > 1e-9:
            continue
        selected.append(row)
    return selected


def run_dir_from_manifest(row):
    return (SCRIPT_DIR / str(row["run_folder"])).resolve()


def scenario_duration_id(row):
    return "%s_%s" % (row["scenario_id"], row["duration_label"])


def segment_key(edge_from, edge_to):
    return "%d->%d" % (int(edge_from), int(edge_to))


def parse_path_edges(path):
    if not isinstance(path, str) or "->" not in path:
        return set()
    nodes = path.split("->")
    if len(nodes) < 2:
        return set()
    edges = set()
    for left, right in zip(nodes, nodes[1:]):
        left = left.strip()
        right = right.strip()
        if left and right:
            edges.add("%s->%s" % (left, right))
    return edges


def classify_route(selected_route_type, decision_reason):
    route = str(selected_route_type or "").strip().upper()
    reason = str(decision_reason or "").strip().lower()
    if route == "SBR":
        return "sbr"
    if route == "BR":
        return "br"
    if "no_route" in reason or route == "NO_ROUTE":
        return "no_route"
    return "fallback"


def load_target_corridor_segments(run_dir):
    path = run_dir / "isl_corridor_load_summary.csv"
    frame = read_csv_if_exists(path)
    required = {"edge_from", "edge_to", "on_target_focus_corridor"}
    if frame.empty or not required.issubset(frame.columns):
        raise FileNotFoundError(
            "Required target-corridor segment data is missing or incomplete: %s"
            % path
        )
    mask = (
        frame["on_target_focus_corridor"]
        .astype(str)
        .str.lower()
        .isin(["true", "1", "yes"])
    )
    frame = frame[mask].copy()
    frame["segment"] = [
        segment_key(row["edge_from"], row["edge_to"])
        for _, row in frame.iterrows()
    ]
    frame = frame.drop_duplicates("segment").copy()
    numeric_columns = [
        "edge_from",
        "edge_to",
        "selected_flow_count",
        "estimated_offered_rate_mbps",
        "isl_capacity_mbps",
        "load_ratio",
        "edge_rank_by_load",
    ]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def load_segment_utilization(run_dir, candidate_segments, traffic_stop_s):
    path = run_dir / "algorithm_lhtr" / "logs_ns3" / "isl_utilization.csv"
    columns = ["from", "to", "interval_start_ns", "interval_end_ns", "utilization"]
    result = {
        segment: {
            "mean_utilization": 0.0,
            "p95_utilization": 0.0,
            "max_utilization": 0.0,
            "utilization_sample_count": 0,
        }
        for segment in candidate_segments
    }
    if not path.is_file() or path.stat().st_size == 0:
        return result

    traffic_stop_ns = float(traffic_stop_s) * 1e9
    frame = pd.read_csv(path, header=None, names=columns)
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna()
    frame["interval_start_ns"] = frame["interval_start_ns"].clip(lower=0)
    frame["interval_end_ns"] = frame["interval_end_ns"].clip(upper=traffic_stop_ns)
    frame["duration_ns"] = frame["interval_end_ns"] - frame["interval_start_ns"]
    frame = frame[frame["duration_ns"] > 0].copy()
    if frame.empty:
        return result

    frame["segment"] = [
        segment_key(row["from"], row["to"])
        for _, row in frame.iterrows()
    ]
    frame = frame[frame["segment"].isin(candidate_segments)].copy()
    if frame.empty:
        return result

    for segment, group in frame.groupby("segment"):
        durations = group["duration_ns"].to_numpy(dtype=float)
        values = group["utilization"].to_numpy(dtype=float)
        present_duration = durations.sum()
        expected_duration = traffic_stop_ns
        if present_duration < expected_duration:
            durations = np.append(durations, expected_duration - present_duration)
            values = np.append(values, 0.0)
        result[segment] = {
            "mean_utilization": (
                float(np.average(values, weights=durations))
                if durations.sum() > 0
                else 0.0
            ),
            "p95_utilization": weighted_quantile(values, durations, 0.95),
            "max_utilization": float(np.max(values)) if len(values) else 0.0,
            "utilization_sample_count": int(len(group)),
        }
    return result


def load_segment_color_counts(run_dir, candidate_segments, chunksize=500000):
    path = (
        run_dir
        / "algorithm_lhtr"
        / "lhtr_diagnostics"
        / "lhtr_qor_tqor_samples.csv"
    )
    counts = {
        segment: {"yellow_count": 0, "red_count": 0, "yellow_plus_red_count": 0}
        for segment in candidate_segments
    }
    if not path.is_file() or path.stat().st_size == 0:
        return counts

    usecols = ["link_key", "final_color"]
    reader = pd.read_csv(
        path,
        usecols=usecols,
        dtype=str,
        chunksize=chunksize,
        keep_default_na=False,
    )
    candidate_link_keys = {"ISL:%s" % segment for segment in candidate_segments}
    for chunk in reader:
        chunk = chunk[chunk["link_key"].isin(candidate_link_keys)]
        if chunk.empty:
            continue
        chunk["segment"] = chunk["link_key"].str.replace("ISL:", "", regex=False)
        color = chunk["final_color"].astype(str).str.upper()
        chunk = chunk.assign(_color=color)
        grouped = chunk.groupby(["segment", "_color"]).size()
        for (segment, final_color), value in grouped.items():
            if segment not in counts:
                continue
            if final_color == "YELLOW":
                counts[segment]["yellow_count"] += int(value)
                counts[segment]["yellow_plus_red_count"] += int(value)
            elif final_color == "RED":
                counts[segment]["red_count"] += int(value)
                counts[segment]["yellow_plus_red_count"] += int(value)
    return counts


def choose_top_segments(candidate_frame, util_metrics, color_counts, top_fraction):
    rows = []
    for _, row in candidate_frame.iterrows():
        segment = row["segment"]
        util = util_metrics.get(segment, {})
        colors = color_counts.get(segment, {})
        rows.append(
            {
                "segment": segment,
                "edge_from": int(row["edge_from"]),
                "edge_to": int(row["edge_to"]),
                "selected_flow_count": row.get("selected_flow_count", math.nan),
                "estimated_offered_rate_mbps": row.get(
                    "estimated_offered_rate_mbps", math.nan
                ),
                "isl_capacity_mbps": row.get("isl_capacity_mbps", math.nan),
                "scheduled_load_ratio": row.get("load_ratio", math.nan),
                "edge_rank_by_load": row.get("edge_rank_by_load", math.nan),
                "mean_utilization": util.get("mean_utilization", 0.0),
                "p95_utilization": util.get("p95_utilization", 0.0),
                "max_utilization": util.get("max_utilization", 0.0),
                "utilization_sample_count": util.get("utilization_sample_count", 0),
                "yellow_count": colors.get("yellow_count", 0),
                "red_count": colors.get("red_count", 0),
                "yellow_plus_red_count": colors.get("yellow_plus_red_count", 0),
            }
        )
    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, set()
    detail = detail.sort_values(
        by=[
            "p95_utilization",
            "mean_utilization",
            "max_utilization",
            "scheduled_load_ratio",
            "red_count",
            "yellow_plus_red_count",
            "segment",
        ],
        ascending=[False, False, False, False, False, False, True],
    ).reset_index(drop=True)
    top_count = max(1, int(math.ceil(len(detail) * top_fraction)))
    detail["is_top25_segment"] = False
    detail["top_segment_rank"] = ""
    detail.loc[: top_count - 1, "is_top25_segment"] = True
    detail.loc[: top_count - 1, "top_segment_rank"] = np.arange(1, top_count + 1)
    top_segments = set(detail.head(top_count)["segment"].tolist())
    return detail, top_segments


def read_global_lhtr_counts(run_dir):
    path = (
        run_dir
        / "algorithm_lhtr"
        / "lhtr_diagnostics"
        / "lhtr_br_sbr_summary.csv"
    )
    frame = read_csv_if_exists(path)
    if frame.empty:
        return {
            "br": 0,
            "sbr": 0,
            "fallback": 0,
            "no_route": 0,
            "sbr_ratio": math.nan,
            "sbr_ratio_no_fallback": math.nan,
        }
    columns = [
        "br_selected_count",
        "sbr_selected_count",
        "fallback_count",
        "no_route_count",
    ]
    for column in columns:
        if column not in frame.columns:
            frame[column] = 0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    br = int(frame["br_selected_count"].sum())
    sbr = int(frame["sbr_selected_count"].sum())
    fallback = int(frame["fallback_count"].sum())
    no_route = int(frame["no_route_count"].sum())
    total = br + sbr + fallback + no_route
    return {
        "br": br,
        "sbr": sbr,
        "fallback": fallback,
        "no_route": no_route,
        "sbr_ratio": safe_divide(sbr, total),
        "sbr_ratio_no_fallback": safe_divide(sbr, br + sbr),
    }


def scan_decision_log(
    run_dir,
    target_segments,
    top_segments,
    chunksize,
    collect_samples=False,
    max_samples=250,
):
    path = (
        run_dir
        / "algorithm_lhtr"
        / "lhtr_diagnostics"
        / "lhtr_br_sbr_decision_log.csv"
    )
    result = DecisionScanResult()
    if not path.is_file() or path.stat().st_size == 0:
        return result

    usecols = [
        "time_ns",
        "src",
        "dst",
        "current_node",
        "selected_route_type",
        "br_max_color",
        "sbr_max_color",
        "decision_reason",
        "br_path",
        "sbr_path",
        "selected_path",
    ]
    reader = pd.read_csv(
        path,
        usecols=usecols,
        dtype=str,
        chunksize=chunksize,
        keep_default_na=False,
    )

    row_offset = 0
    Row = None
    for chunk in reader:
        if Row is None:
            Row = chunk.itertuples(index=False, name="DecisionRow")
        else:
            Row = chunk.itertuples(index=False, name="DecisionRow")
        for local_index, row in enumerate(Row):
            route_class = classify_route(
                row.selected_route_type, row.decision_reason
            )
            result.sample_global.add(route_class)
            br_edges = parse_path_edges(row.br_path)
            selected_edges = parse_path_edges(row.selected_path)

            br_target_matches = br_edges.intersection(target_segments)
            br_top_matches = br_edges.intersection(top_segments)
            selected_top_matches = selected_edges.intersection(top_segments)

            if br_target_matches:
                result.target_corridor.add(route_class)
            if br_top_matches:
                result.top25_segment.add(route_class)
                for segment in br_top_matches:
                    result.per_top_segment[segment].add(route_class)
                if collect_samples and len(result.samples) < max_samples:
                    result.samples.append(
                        {
                            "sample_index": row_offset + int(local_index),
                            "time_ns": row.time_ns,
                            "src": row.src,
                            "dst": row.dst,
                            "current_node": row.current_node,
                            "selected_route_type": row.selected_route_type,
                            "decision_reason": row.decision_reason,
                            "br_max_color": row.br_max_color,
                            "sbr_max_color": row.sbr_max_color,
                            "matched_top_segments": ";".join(
                                sorted(br_top_matches)
                            ),
                            "br_path": row.br_path,
                            "sbr_path": row.sbr_path,
                            "selected_path": row.selected_path,
                        }
                    )
            if selected_top_matches:
                result.selected_path_top25.add(route_class)
            if br_top_matches or selected_top_matches:
                result.br_or_selected_path_top25.add(route_class)
        row_offset += len(chunk)

    return result


def counts_to_summary(prefix, counts):
    return {
        "%s_decision_count" % prefix: counts.total,
        "%s_br_selected" % prefix: counts.br,
        "%s_sbr_selected" % prefix: counts.sbr,
        "%s_fallback" % prefix: counts.fallback,
        "%s_no_route" % prefix: counts.no_route,
        "%s_sbr_ratio" % prefix: counts.sbr_ratio(),
        "%s_sbr_ratio_no_fallback" % prefix: counts.sbr_ratio_no_fallback(),
    }


def build_summary_row(row, global_counts, segment_detail, scan_result, top_fraction):
    sample = scan_result.sample_global
    top_segments = segment_detail[segment_detail["is_top25_segment"]][
        "segment"
    ].tolist()
    summary = {
        "result_scope": "br_path_intersects_congested_segment",
        "scenario_id": row["scenario_id"],
        "scenario_duration_id": scenario_duration_id(row),
        "hotspot_label": row["hotspot_label"],
        "duration_s": row["duration_s"],
        "traffic_stop_s": row["traffic_stop_s"],
        "load_level": row["load_level"],
        "background_flow_count": row["background_flow_count"],
        "hotspot_reference_load_percent": row["hotspot_reference_load_percent"],
        "global_offered_isl_load_percent": row["global_offered_isl_load_percent"],
        "run_folder": row["run_folder"],
        "top_fraction": top_fraction,
        "candidate_segment_count": int(len(segment_detail)),
        "top_segment_count": int(len(top_segments)),
        "top_segments": ";".join(top_segments),
        "segment_congestion_metric": "p95_lhtr_measured_utilization",
        "global_br_selected": global_counts["br"],
        "global_sbr_selected": global_counts["sbr"],
        "global_fallback": global_counts["fallback"],
        "global_no_route": global_counts["no_route"],
        "global_sbr_ratio": global_counts["sbr_ratio"],
        "global_sbr_ratio_no_fallback": global_counts["sbr_ratio_no_fallback"],
        "sample_global_total": sample.total,
        "sample_global_br_selected": sample.br,
        "sample_global_sbr_selected": sample.sbr,
        "sample_global_fallback": sample.fallback,
        "sample_global_no_route": sample.no_route,
        "sample_global_sbr_ratio": sample.sbr_ratio(),
        "sample_global_sbr_ratio_no_fallback": sample.sbr_ratio_no_fallback(),
        "sbr_decision_share_on_top25_segments": safe_divide(
            scan_result.top25_segment.sbr, sample.sbr
        ),
        "decision_share_on_top25_segments": safe_divide(
            scan_result.top25_segment.total, sample.total
        ),
        "sbr_decision_share_on_target_corridor": safe_divide(
            scan_result.target_corridor.sbr, sample.sbr
        ),
        "decision_share_on_target_corridor": safe_divide(
            scan_result.target_corridor.total, sample.total
        ),
        "sbr_decision_share_on_selected_path_top25": safe_divide(
            scan_result.selected_path_top25.sbr, sample.sbr
        ),
        "decision_share_on_selected_path_top25": safe_divide(
            scan_result.selected_path_top25.total, sample.total
        ),
        "decision_sample_scope": (
            "lhtr_br_sbr_decision_log diagnostic samples; formal global "
            "ratio uses lhtr_br_sbr_summary"
        ),
    }
    summary.update(counts_to_summary("target_corridor", scan_result.target_corridor))
    summary.update(counts_to_summary("top25_segment", scan_result.top25_segment))
    summary.update(
        counts_to_summary("selected_path_top25", scan_result.selected_path_top25)
    )
    summary.update(
        counts_to_summary(
            "br_or_selected_path_top25",
            scan_result.br_or_selected_path_top25,
        )
    )
    return {column: summary.get(column, "") for column in SUMMARY_COLUMNS}


def attach_segment_decision_counts(segment_detail, row, scan_result):
    sample = scan_result.sample_global
    records = []
    for _, detail in segment_detail.iterrows():
        segment = detail["segment"]
        counts = scan_result.per_top_segment.get(segment, DecisionCounts())
        record = detail.to_dict()
        record.update(
            {
                "scenario_id": row["scenario_id"],
                "scenario_duration_id": scenario_duration_id(row),
                "hotspot_label": row["hotspot_label"],
                "br_path_decision_count": counts.total,
                "br_path_br_selected": counts.br,
                "br_path_sbr_selected": counts.sbr,
                "br_path_fallback": counts.fallback,
                "br_path_no_route": counts.no_route,
                "br_path_sbr_ratio": counts.sbr_ratio(),
                "br_path_sbr_ratio_no_fallback": counts.sbr_ratio_no_fallback(),
                "sbr_share_of_sample_global_sbr": safe_divide(
                    counts.sbr, sample.sbr
                ),
                "decision_share_of_sample_global_decisions": safe_divide(
                    counts.total, sample.total
                ),
            }
        )
        records.append(record)
    frame = pd.DataFrame(records)
    return frame[[column for column in SEGMENT_DETAIL_COLUMNS if column in frame.columns]]


def pct(value):
    if value is None or not np.isfinite(value):
        return "NA"
    return "%.3f%%" % (100.0 * float(value))


def save_summary_table(rows, output_dir):
    table_dir = output_dir / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    path = table_dir / "lhtr_congested_segment_sbr_ratio_summary.csv"
    frame.to_csv(path, index=False)
    return frame, path


def save_h80_tables(summary_frame, segment_frames, samples, output_dir):
    table_dir = output_dir / "tables"
    h80 = None
    for frame in segment_frames:
        mask = (
            (frame["scenario_id"].astype(str) == "H80")
            & (frame["scenario_duration_id"].astype(str) == "H80_200s")
        )
        if mask.any():
            h80 = frame[mask].copy()
            break
    if h80 is None or h80.empty:
        mask = (
            (summary_frame["scenario_id"].astype(str) == "H80")
            & (summary_frame["duration_s"].astype(float) == 200.0)
        )
        if mask.any():
            target_id = summary_frame[mask].iloc[0]["scenario_duration_id"]
            for frame in segment_frames:
                local = frame[
                    frame["scenario_duration_id"].astype(str) == str(target_id)
                ].copy()
                if not local.empty:
                    h80 = local
                    break
    if h80 is not None and not h80.empty:
        top_h80 = h80[h80["is_top25_segment"].astype(bool)].copy()
        top_h80.to_csv(
            table_dir / "h80_200s_top_congested_segments.csv",
            index=False,
        )
    if samples:
        pd.DataFrame(samples).to_csv(
            table_dir / "h80_200s_congested_segment_decision_samples.csv",
            index=False,
        )


def plot_across_levels(summary_frame, figures_dir):
    frame = summary_frame.copy()
    if frame.empty:
        return
    frame["_duration"] = pd.to_numeric(frame["duration_s"], errors="coerce")
    frame = frame[frame["_duration"] == 60.0].copy()
    if frame.empty:
        return
    frame["_sort_scenario"] = frame["scenario_id"].map(
        {scenario: index for index, scenario in enumerate(SCENARIO_ORDER)}
    ).fillna(99)
    frame = frame.sort_values(["_sort_scenario"])
    labels = frame["scenario_id"].astype(str).tolist()
    series = [
        ("Formal global", "global_sbr_ratio"),
        ("Sample global", "sample_global_sbr_ratio"),
        ("Target corridor", "target_corridor_sbr_ratio"),
        ("Top BR segments", "top25_segment_sbr_ratio"),
        ("Selected-path top", "selected_path_top25_sbr_ratio"),
        ("BR or selected top", "br_or_selected_path_top25_sbr_ratio"),
    ]
    x = np.arange(len(labels))
    plt.figure(figsize=(9.8, 5.4))
    for label, column in series:
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        plt.plot(x, values * 100.0, marker="o", linewidth=2, label=label)
    plt.xticks(x, labels, rotation=30, ha="right")
    plt.ylabel("SBR selection ratio (%)")
    plt.xlabel("Hotspot scenario")
    plt.title("LHTR SBR ratio by denominator across hotspot levels")
    plt.grid(axis="y", alpha=0.25)
    plt.legend(loc="upper left", ncol=2)
    plt.tight_layout()
    plt.savefig(figures_dir / "lhtr_sbr_ratio_by_denominator_across_levels.png", dpi=180)
    plt.close()


def plot_global_vs_target_corridor_60s(summary_frame, figures_dir):
    frame = summary_frame.copy()
    if frame.empty:
        return
    frame["_duration"] = pd.to_numeric(frame["duration_s"], errors="coerce")
    frame = frame[frame["_duration"] == 60.0].copy()
    if frame.empty:
        return
    frame["_sort_scenario"] = frame["scenario_id"].map(
        {scenario: index for index, scenario in enumerate(SCENARIO_ORDER)}
    ).fillna(99)
    frame = frame.sort_values(["_sort_scenario"])
    labels = frame["scenario_id"].astype(str).tolist()
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(8.4, 4.9))
    ax.plot(
        x,
        100.0 * pd.to_numeric(frame["global_sbr_ratio"], errors="coerce"),
        marker="o",
        linewidth=2.2,
        color="#4D4D4D",
        label="Global",
    )
    ax.plot(
        x,
        100.0 * pd.to_numeric(frame["target_corridor_sbr_ratio"], errors="coerce"),
        marker="s",
        linewidth=2.2,
        color="#0072B2",
        label="Target Corridor",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("SBR selection ratio (%)")
    ax.set_xlabel("Hotspot scenario")
    ax.set_title("LHTR Global vs Target Corridor SBR Ratio")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(
        figures_dir / "lhtr_global_vs_target_corridor_sbr_ratio_60s_hotspot_levels.png",
        dpi=180,
    )
    plt.close(fig)


def plot_h80_denominators(summary_frame, figures_dir):
    frame = summary_frame[
        (summary_frame["scenario_id"].astype(str) == "H80")
        & (pd.to_numeric(summary_frame["duration_s"], errors="coerce") == 200.0)
    ]
    if frame.empty:
        return
    row = frame.iloc[0]
    labels = [
        "Formal global",
        "Sample global",
        "Target corridor",
        "Top BR segments",
        "Selected-path top",
        "BR or selected top",
    ]
    columns = [
        "global_sbr_ratio",
        "sample_global_sbr_ratio",
        "target_corridor_sbr_ratio",
        "top25_segment_sbr_ratio",
        "selected_path_top25_sbr_ratio",
        "br_or_selected_path_top25_sbr_ratio",
    ]
    values = [float(row[column]) * 100.0 for column in columns]
    colors = ["#4C78A8", "#72B7B2", "#F58518", "#E45756", "#54A24B", "#B279A2"]
    plt.figure(figsize=(10, 5.5))
    bars = plt.bar(labels, values, color=colors)
    plt.ylabel("SBR selection ratio (%)")
    plt.title("H80 200s SBR ratio by denominator")
    plt.xticks(rotation=20, ha="right")
    plt.grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, values):
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            "%.2f%%" % value,
            ha="center",
            va="bottom",
            fontsize=9,
        )
    plt.tight_layout()
    plt.savefig(figures_dir / "h80_200s_sbr_ratio_by_denominator.png", dpi=180)
    plt.close()


def plot_h80_segments(segment_frames, figures_dir):
    h80 = None
    for frame in segment_frames:
        mask = (
            (frame["scenario_id"].astype(str) == "H80")
            & (frame["scenario_duration_id"].astype(str) == "H80_200s")
            & (frame["is_top25_segment"].astype(bool))
        )
        if mask.any():
            h80 = frame[mask].copy()
            break
    if h80 is None or h80.empty:
        return
    h80["top_segment_rank"] = pd.to_numeric(h80["top_segment_rank"], errors="coerce")
    h80 = h80.sort_values("top_segment_rank")
    labels = h80["segment"].astype(str).tolist()
    sbr_ratio = pd.to_numeric(h80["br_path_sbr_ratio"], errors="coerce").fillna(0)
    p95 = pd.to_numeric(h80["p95_utilization"], errors="coerce").fillna(0)
    y = np.arange(len(labels))
    plt.figure(figsize=(10, max(5, 0.35 * len(labels) + 2)))
    plt.barh(y, sbr_ratio * 100.0, color="#E45756", label="SBR ratio")
    plt.plot(p95 * 100.0, y, color="#4C78A8", marker="o", label="p95 utilization")
    plt.yticks(y, labels)
    plt.xlabel("Percent (%)")
    plt.title("H80 200s top congested segment SBR ratio")
    plt.grid(axis="x", alpha=0.25)
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(figures_dir / "h80_200s_top_congested_segments_sbr_ratio.png", dpi=180)
    plt.close()


def plot_h80_concentration(summary_frame, figures_dir):
    frame = summary_frame[
        (summary_frame["scenario_id"].astype(str) == "H80")
        & (pd.to_numeric(summary_frame["duration_s"], errors="coerce") == 200.0)
    ]
    if frame.empty:
        return
    row = frame.iloc[0]
    labels = ["Target corridor", "Top BR segments", "Selected-path top"]
    decision_columns = [
        "decision_share_on_target_corridor",
        "decision_share_on_top25_segments",
        "decision_share_on_selected_path_top25",
    ]
    sbr_columns = [
        "sbr_decision_share_on_target_corridor",
        "sbr_decision_share_on_top25_segments",
        "sbr_decision_share_on_selected_path_top25",
    ]
    decision_values = [float(row[column]) * 100.0 for column in decision_columns]
    sbr_values = [float(row[column]) * 100.0 for column in sbr_columns]
    x = np.arange(len(labels))
    width = 0.36
    plt.figure(figsize=(9, 5.2))
    plt.bar(x - width / 2, decision_values, width, label="Decision share", color="#4C78A8")
    plt.bar(x + width / 2, sbr_values, width, label="SBR share", color="#F58518")
    plt.ylabel("Share of sampled decisions (%)")
    plt.title("H80 200s SBR decision concentration on segments")
    plt.xticks(x, labels, rotation=15, ha="right")
    plt.grid(axis="y", alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(
        figures_dir / "h80_200s_sbr_decision_concentration_on_segments.png",
        dpi=180,
    )
    plt.close()


def make_plots(summary_frame, segment_frames, output_dir):
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    plot_across_levels(summary_frame, figures_dir)
    plot_global_vs_target_corridor_60s(summary_frame, figures_dir)
    plot_h80_denominators(summary_frame, figures_dir)
    plot_h80_segments(segment_frames, figures_dir)
    plot_h80_concentration(summary_frame, figures_dir)


def write_report(summary_frame, output_dir):
    report_path = output_dir / "analysis_report_zh.md"
    h80 = summary_frame[
        (summary_frame["scenario_id"].astype(str) == "H80")
        & (pd.to_numeric(summary_frame["duration_s"], errors="coerce") == 200.0)
    ]
    h80_row = h80.iloc[0] if not h80.empty else None

    lines = [
        "# LHTR 壅塞 corridor segment SBR ratio 分析",
        "",
        "## 1. 任務範圍",
        "",
        "本次分析改用 corridor segment 作為分母：先找出 target corridor 上最壅塞的 directed ISL segments，再統計 BR path 會經過這些 segments 的 LHTR 決策裡，最後選 SBR 的比例。",
        "",
        "本分析沒有重新執行 ns-3，也沒有修改 LHTR routing algorithm；所有結果都來自既有 formal run 輸出。",
        "",
        "## 2. 壅塞 segment 定義",
        "",
        "- Candidate segments：`isl_corridor_load_summary.csv` 中 `on_target_focus_corridor=true` 的 directed ISL edges。",
        "- 壅塞分數：`algorithm_lhtr/logs_ns3/isl_utilization.csv` 在 traffic window 內的 weighted p95 utilization。",
        "- Top segments：依 p95 utilization 由高到低取 `--top-fraction`，預設為 top 25%。",
        "- 平手排序：mean utilization、max utilization、排程估計 load ratio、red/yellow sample count。",
        "",
        "## 3. 決策分母定義",
        "",
        "- Formal global ratio：來自 `lhtr_br_sbr_summary.csv` 的全部 LHTR decision counter。",
        "- Sample global ratio：來自 `lhtr_br_sbr_decision_log.csv` 的診斷樣本。",
        "- Target corridor ratio：BR path intersect 任一 target corridor segment 的診斷樣本。",
        "- Top25 segment ratio：BR path intersect 任一 top congested segment 的診斷樣本，這是本次主分母。",
        "- Selected-path top25 ratio：selected path intersect top congested segment 的輔助分母。",
        "- BR-or-selected top25 ratio：BR path 或 selected path 任一者 intersect top congested segment 的輔助分母。",
        "",
        "## 4. 主要結果",
        "",
    ]

    if h80_row is not None:
        lines.extend(
            [
                "H80 200s 的核心數字如下：",
                "",
                "| 分母 | SBR ratio | 決策數 |",
                "|---|---:|---:|",
                "| Formal global | %s | %s |"
                % (
                    pct(float(h80_row["global_sbr_ratio"])),
                    int(h80_row["global_br_selected"])
                    + int(h80_row["global_sbr_selected"])
                    + int(h80_row["global_fallback"])
                    + int(h80_row["global_no_route"]),
                ),
                "| Sample global | %s | %s |"
                % (
                    pct(float(h80_row["sample_global_sbr_ratio"])),
                    int(h80_row["sample_global_total"]),
                ),
                "| Target corridor by BR path | %s | %s |"
                % (
                    pct(float(h80_row["target_corridor_sbr_ratio"])),
                    int(h80_row["target_corridor_decision_count"]),
                ),
                "| Top25 congested segments by BR path | %s | %s |"
                % (
                    pct(float(h80_row["top25_segment_sbr_ratio"])),
                    int(h80_row["top25_segment_decision_count"]),
                ),
                "| Selected path intersects top25 | %s | %s |"
                % (
                    pct(float(h80_row["selected_path_top25_sbr_ratio"])),
                    int(h80_row["selected_path_top25_decision_count"]),
                ),
                "| BR or selected path intersects top25 | %s | %s |"
                % (
                    pct(float(h80_row["br_or_selected_path_top25_sbr_ratio"])),
                    int(h80_row["br_or_selected_path_top25_decision_count"]),
                ),
                "",
                "H80 200s 的 top segment 數量為 %s / %s；top segments 為 `%s`。"
                % (
                    int(h80_row["top_segment_count"]),
                    int(h80_row["candidate_segment_count"]),
                    h80_row["top_segments"],
                ),
                "",
            ]
        )
    else:
        lines.extend(["未在本次篩選中找到 H80 200s row。", ""])

    if not summary_frame.empty:
        cross = summary_frame.copy()
        cross["_duration"] = pd.to_numeric(cross["duration_s"], errors="coerce")
        cross = cross[cross["_duration"] == 60.0].copy()
        cross["_scenario_order"] = cross["scenario_id"].map(
            {scenario: index for index, scenario in enumerate(SCENARIO_ORDER)}
        ).fillna(99)
        cross = cross.sort_values(["_scenario_order"])
        lines.extend(
            [
                "跨負載摘要如下；這裡只列 60s 的五個 Hotspot scenario，H80 200s 不放進跨負載趨勢圖。",
                "",
                "| Scenario | Global | Target Corridor |",
                "|---|---:|---:|",
            ]
        )
        for _, item in cross.iterrows():
            lines.append(
                "| %s | %s | %s |"
                % (
                    item["scenario_id"],
                    pct(float(item["global_sbr_ratio"])),
                    pct(float(item["target_corridor_sbr_ratio"])),
                )
            )
        lines.append("")

    lines.extend(
        [
            "## 5. 為什麼 segment 分母仍可能不高",
            "",
            "若 top25 segment ratio 仍然偏低，代表 LHTR 的 SBR 選擇並不只是由「BR path 是否穿過最壅塞 corridor segment」決定。從 log 欄位來看，常見限制包括：BR/SBR 兩條候選路徑的 traffic-light 顏色同時是 GREEN、SBR stretch 或 score 沒有優勢、或當下沒有 admissible SBR candidate。",
            "",
            "換句話說，這個分析縮小了分母，但仍然保留 LHTR 原始決策邏輯；它不能把「路徑碰到壅塞 segment」自動解讀成「必然要選 SBR」。",
            "",
            "## 6. `SBR share on top segments` 與 `SBR ratio` 的差異",
            "",
            "- `SBR ratio` 是條件機率：在某個分母內，有多少比例的決策選了 SBR。例如 top25 segment ratio = top25 segment 相關決策中的 SBR / top25 segment 相關決策總數。",
            "- `SBR share on top segments` 是集中度：所有 SBR 決策中，有多少比例落在 top25 segments 相關分母內。",
            "",
            "因此 share 高不代表該分母內 SBR ratio 高；它只表示 SBR 決策是否集中在那些 segments 上。",
            "",
            "## 7. 100ms window 與 segment 分析的關係",
            "",
            "100ms window 會讓時間定位更細，但它仍然是時間分母；本分析改成 path/segment 分母，回答的是另一個問題：決策的 BR path 是否真的穿過壅塞 corridor。若要比較 1s 與 100ms，建議把它作為輔助圖，而不是取代 segment 分母。",
            "",
            "## 8. 產出檔案",
            "",
            "- `tables/lhtr_congested_segment_sbr_ratio_summary.csv`",
            "- `tables/h80_200s_top_congested_segments.csv`",
            "- `tables/h80_200s_congested_segment_decision_samples.csv`",
            "- `figures/lhtr_sbr_ratio_by_denominator_across_levels.png`",
            "- `figures/lhtr_global_vs_target_corridor_sbr_ratio_60s_hotspot_levels.png`",
            "- `figures/h80_200s_sbr_ratio_by_denominator.png`",
            "- `figures/h80_200s_top_congested_segments_sbr_ratio.png`",
            "- `figures/h80_200s_sbr_decision_concentration_on_segments.png`",
            "",
            "## 9. 注意事項",
            "",
            "`lhtr_br_sbr_decision_log.csv` 是 diagnostic sample log；因此 segment-specific ratio 是 sample-based。報告同時列出 formal global ratio 與 sample global ratio，避免把不同來源的分母誤讀為同一個母體。",
            "",
        ]
    )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main():
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "tables").mkdir(parents=True, exist_ok=True)
    (output_dir / "figures").mkdir(parents=True, exist_ok=True)

    runs = filter_runs(load_manifest(), args.scenario, args.duration_s)
    if not runs:
        raise SystemExit("No complete formal runs matched the requested filters.")

    summary_rows = []
    segment_frames = []
    h80_samples = []

    for row in runs:
        run_dir = run_dir_from_manifest(row)
        print(
            "Analyzing %s (%ss): %s"
            % (row["scenario_id"], row["duration_s"], run_dir)
        )
        candidate_frame = load_target_corridor_segments(run_dir)
        candidate_segments = set(candidate_frame["segment"].tolist())
        util_metrics = load_segment_utilization(
            run_dir, candidate_segments, row["traffic_stop_s"]
        )
        color_counts = load_segment_color_counts(
            run_dir, candidate_segments, chunksize=max(args.chunksize, 200000)
        )
        segment_detail, top_segments = choose_top_segments(
            candidate_frame, util_metrics, color_counts, args.top_fraction
        )
        global_counts = read_global_lhtr_counts(run_dir)
        collect_samples = (
            str(row["scenario_id"]) == "H80" and abs(float(row["duration_s"]) - 200.0) < 1e-9
        )
        scan_result = scan_decision_log(
            run_dir,
            candidate_segments,
            top_segments,
            args.chunksize,
            collect_samples=collect_samples,
        )
        summary_rows.append(
            build_summary_row(
                row, global_counts, segment_detail, scan_result, args.top_fraction
            )
        )
        segment_frames.append(
            attach_segment_decision_counts(segment_detail, row, scan_result)
        )
        if collect_samples:
            h80_samples = scan_result.samples

    summary_frame, summary_path = save_summary_table(summary_rows, output_dir)
    if segment_frames:
        all_segments = pd.concat(segment_frames, ignore_index=True)
        all_segments.to_csv(
            output_dir / "tables" / "all_target_corridor_segments.csv",
            index=False,
        )
    save_h80_tables(summary_frame, segment_frames, h80_samples, output_dir)
    make_plots(summary_frame, segment_frames, output_dir)
    report_path = write_report(summary_frame, output_dir)

    print("Wrote summary: %s" % summary_path)
    print("Wrote report: %s" % report_path)


if __name__ == "__main__":
    main()
