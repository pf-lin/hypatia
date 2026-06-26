import argparse
import csv
import glob
import json
import math
import os
import subprocess
import sys
from collections import Counter

from dynamic_run_list import (
    backpressure_fallback_policies,
    backpressure_loop_guard_modes,
    backpressure_queue_sources,
    default_backpressure_diagnostics,
    default_backpressure_diagnostics_sample_limit,
    default_backpressure_fallback,
    default_backpressure_loop_guard,
    default_backpressure_queue_source,
    get_udp_pdr_run_list,
    seconds_to_tag,
)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(SCRIPT_DIR, "runs")
DEFAULT_SIMULATION_END_TIME_S = 60.0
DEFAULT_DRAIN_TIME_S = 2.0
DEFAULT_TRAFFIC_STOP_TIME_S = (
    DEFAULT_SIMULATION_END_TIME_S - DEFAULT_DRAIN_TIME_S
)

ALGORITHMS = [
    "algorithm_free_one_only_over_isls",
    "algorithm_queue_aware_over_isls",
    "algorithm_lohi",
    "algorithm_lhtr",
]
BACKPRESSURE_QUEUE_SOURCE = default_backpressure_queue_source
BACKPRESSURE_FALLBACK = default_backpressure_fallback
BACKPRESSURE_LOOP_GUARD = default_backpressure_loop_guard
BACKPRESSURE_DIAGNOSTICS = default_backpressure_diagnostics
BACKPRESSURE_DIAGNOSTICS_SAMPLE_LIMIT = default_backpressure_diagnostics_sample_limit

SCENARIOS = [
    {
        "scenario_id": "H40",
        "load_level": 1.0,
        "background_flow_count": 24,
        "hotspot_reference_load_percent": 47.358630953,
        "global_offered_isl_load_percent": 1.841724537,
        "target_corridor_offered_load_percent": 75.333333335,
        "peak_reference_link_offered_load_percent": 133.333333336,
        "label": "Hotspot-Light",
        "observed_pressure_condition": "Localized congestion",
    },
    {
        "scenario_id": "H60",
        "load_level": 1.2,
        "background_flow_count": 32,
        "hotspot_reference_load_percent": 59.154411765,
        "global_offered_isl_load_percent": 2.793402778,
        "target_corridor_offered_load_percent": 108.8,
        "peak_reference_link_offered_load_percent": 220.0,
        "label": "Hotspot-Moderate",
        "observed_pressure_condition": "Localized congestion",
    },
    {
        "scenario_id": "H80",
        "load_level": 1.6,
        "background_flow_count": 32,
        "hotspot_reference_load_percent": 78.872549021,
        "global_offered_isl_load_percent": 3.724537037,
        "target_corridor_offered_load_percent": 145.066666668,
        "peak_reference_link_offered_load_percent": 293.333333337,
        "label": "Hotspot-High",
        "observed_pressure_condition": "Sustained congestion",
    },
    {
        "scenario_id": "H90",
        "load_level": 2.2,
        "background_flow_count": 48,
        "hotspot_reference_load_percent": 91.171171172,
        "global_offered_isl_load_percent": 7.027777778,
        "target_corridor_offered_load_percent": 243.466666669,
        "peak_reference_link_offered_load_percent": 623.333333339,
        "label": "Hotspot-Severe",
        "observed_pressure_condition": "Sustained congestion",
    },
    {
        "scenario_id": "H100+",
        "load_level": 2.8,
        "background_flow_count": 48,
        "hotspot_reference_load_percent": 116.036036037,
        "global_offered_isl_load_percent": 8.944444445,
        "target_corridor_offered_load_percent": 309.866666669,
        "peak_reference_link_offered_load_percent": 793.333333339,
        "label": "Hotspot-Overload",
        "observed_pressure_condition": "Overloaded",
    },
]

MANIFEST_FIELDS = [
    "scenario_set",
    "simulation_end_time_s",
    "traffic_stop_time_s",
    "duration_label",
    "scenario_id",
    "load_level",
    "background_flow_count",
    "hotspot_reference_load_percent",
    "global_offered_isl_load_percent",
    "label",
    "run_folder",
    "status",
    "step1_status",
    "step2_status",
    "step3_status",
    "notes",
]

SUMMARY_FIELDS = [
    "scenario_set",
    "simulation_end_time_s",
    "traffic_stop_time_s",
    "duration_label",
    "scenario_id",
    "load_level",
    "background_flow_count",
    "hotspot_reference_load_percent",
    "global_offered_isl_load_percent",
    "algorithm",
    "finished",
    "console_ok",
    "aggregate_pdr",
    "focus_pdr",
    "background_pdr",
    "lost_packets",
    "dominant_loss_attribution",
    "max_isl_queue",
    "max_gsl_queue",
    "queue_aware_rtt_mean_ms_if_available",
    "queue_aware_rtt_p95_ms_if_available",
    "lhtr_br_selected_count_if_available",
    "lhtr_sbr_selected_count_if_available",
    "lhtr_fallback_count_if_available",
    "lhtr_yellow_count_if_available",
    "lhtr_red_count_if_available",
    "lhtr_top_decision_reasons_if_available",
    "route_plots_exist",
    "notes",
]

LHTR_REQUIRED_FILES = [
    "lhtr_qor_tqor_samples.csv",
    "lhtr_traffic_light_color_summary.csv",
    "lhtr_br_sbr_decision_log.csv",
    "lhtr_br_sbr_summary.csv",
    "lhtr_decision_reason_summary.csv",
    "lhtr_fstate_decision_consistency.csv",
]

BACKPRESSURE_REQUIRED_FILES = [
    "backpressure_decision_log.csv",
    "backpressure_summary.csv",
    "backpressure_queue_source_summary.csv",
    "backpressure_fallback_summary.csv",
    "backpressure_path_stretch_summary.csv",
    "backpressure_loop_check.csv",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run duration-aware UDP/PDR hotspot formal scenarios."
    )
    parser.add_argument(
        "--simulation-end-time-s",
        type=float,
        default=DEFAULT_SIMULATION_END_TIME_S,
        help="Simulation duration in seconds. Default: 60.",
    )
    parser.add_argument(
        "--traffic-stop-time-s",
        type=float,
        default=None,
        help=(
            "Stop generating traffic at this time. Default: "
            "simulation_end_time_s - 2."
        ),
    )
    parser.add_argument(
        "--rtt-sample-interval-s",
        type=float,
        default=None,
        help=(
            "RTT sample interval. Default: 0.1 s for runs up to 60 s, "
            "otherwise 1 s."
        ),
    )
    parser.add_argument(
        "--route-plot-times",
        default=None,
        help=(
            "Comma-separated route plot times. Default: every 30 s through "
            "traffic stop, capped at 10 times."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands only; do not create or overwrite outputs.",
    )
    parser.add_argument(
        "--generation-only",
        action="store_true",
        help="Run step 1 only.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate existing timing-isolated formal run folders.",
    )
    parser.add_argument(
        "--skip-step2",
        action="store_true",
        help="Skip NS-3 and use any existing simulation outputs.",
    )
    parser.add_argument(
        "--skip-step3",
        action="store_true",
        help="Skip packet-delivery, RTT, and route analysis.",
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        help="Scenario IDs to run. Default: H40 H60 H80 H90 H100+.",
    )
    parser.add_argument(
        "--algorithms",
        nargs="+",
        default=list(ALGORITHMS),
        help="Routing algorithms to run. Default: %s" % " ".join(ALGORITHMS),
    )
    parser.add_argument(
        "--backpressure-queue-source",
        choices=backpressure_queue_sources,
        default=default_backpressure_queue_source,
        help="Queue source for algorithm_backpressure_over_isls.",
    )
    parser.add_argument(
        "--backpressure-fallback",
        choices=backpressure_fallback_policies,
        default=default_backpressure_fallback,
        help="Fallback policy for algorithm_backpressure_over_isls.",
    )
    parser.add_argument(
        "--backpressure-loop-guard",
        choices=backpressure_loop_guard_modes,
        default=default_backpressure_loop_guard,
        help="Restricted-route / loop-suppression mode for algorithm_backpressure_over_isls.",
    )
    diagnostics_group = parser.add_mutually_exclusive_group()
    diagnostics_group.add_argument(
        "--backpressure-diagnostics",
        dest="backpressure_diagnostics",
        action="store_true",
        help="Write Backpressure diagnostics.",
    )
    diagnostics_group.add_argument(
        "--no-backpressure-diagnostics",
        dest="backpressure_diagnostics",
        action="store_false",
        help="Skip Backpressure diagnostics.",
    )
    parser.set_defaults(backpressure_diagnostics=default_backpressure_diagnostics)
    parser.add_argument(
        "--backpressure-diagnostics-sample-limit",
        type=int,
        default=default_backpressure_diagnostics_sample_limit,
        help="Maximum Backpressure decision-log rows per routing snapshot.",
    )
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Read existing outputs and rebuild the manifest/summary/status only.",
    )
    args = parser.parse_args()
    if args.traffic_stop_time_s is None:
        args.traffic_stop_time_s = (
            args.simulation_end_time_s - DEFAULT_DRAIN_TIME_S
        )
    if args.simulation_end_time_s <= 0:
        parser.error("--simulation-end-time-s must be positive")
    if not 0 <= args.traffic_stop_time_s <= args.simulation_end_time_s:
        parser.error(
            "--traffic-stop-time-s must satisfy 0 <= stop <= simulation end; "
            "the implicit default requires simulation end >= 2"
        )
    if args.rtt_sample_interval_s is not None and args.rtt_sample_interval_s <= 0:
        parser.error("--rtt-sample-interval-s must be positive")
    if not args.algorithms:
        parser.error("--algorithms must contain at least one algorithm")
    if args.backpressure_diagnostics_sample_limit < 0:
        parser.error("--backpressure-diagnostics-sample-limit must be non-negative")
    if args.route_plot_times is not None:
        try:
            parse_route_plot_times(
                args.route_plot_times,
                args.traffic_stop_time_s,
            )
        except ValueError as exc:
            parser.error(str(exc))
    if args.generation_only and (args.skip_step2 or args.skip_step3):
        parser.error("--generation-only cannot be combined with skip flags")
    if args.aggregate_only and (
        args.dry_run
        or args.generation_only
        or args.force
        or args.skip_step2
        or args.skip_step3
    ):
        parser.error("--aggregate-only cannot be combined with execution flags")
    return args


def format_seconds(value):
    return seconds_to_tag(value).replace("p", ".")


def duration_label(simulation_end_time_s, traffic_stop_time_s):
    simulation_tag = "%ss" % seconds_to_tag(simulation_end_time_s)
    expected_stop = simulation_end_time_s - DEFAULT_DRAIN_TIME_S
    if math.isclose(traffic_stop_time_s, expected_stop, abs_tol=1e-9):
        return simulation_tag
    return "%s_stop%ss" % (
        simulation_tag,
        seconds_to_tag(traffic_stop_time_s),
    )


def output_paths(simulation_end_time_s, traffic_stop_time_s):
    label = duration_label(simulation_end_time_s, traffic_stop_time_s)
    prefix = "hotspot_5level_%s" % label
    report_dir = os.path.join(
        SCRIPT_DIR,
        "analysis_reports",
        prefix + "_formal",
    )
    return {
        "duration_label": label,
        "report_dir": report_dir,
        "manifest_path": os.path.join(
            RUNS_DIR,
            prefix + "_formal_manifest.csv",
        ),
        "summary_path": os.path.join(
            report_dir,
            prefix + "_formal_summary.csv",
        ),
        "status_path": os.path.join(
            report_dir,
            prefix + "_formal_status.md",
        ),
    }


def default_rtt_sample_interval_s(simulation_end_time_s):
    return 0.1 if simulation_end_time_s <= 60 else 1.0


def parse_route_plot_times(value, traffic_stop_time_s):
    times = []
    for item in str(value).split(","):
        item = item.strip()
        if not item:
            continue
        time_s = float(item)
        if time_s < 0 or time_s > traffic_stop_time_s:
            raise ValueError(
                "route plot times must be between 0 and traffic stop (%s)"
                % format_seconds(traffic_stop_time_s)
            )
        if not any(math.isclose(time_s, existing) for existing in times):
            times.append(time_s)
    if not times:
        raise ValueError("--route-plot-times must contain at least one time")
    return sorted(times)


def default_route_plot_times(traffic_stop_time_s, interval_s=30.0, limit=10):
    times = [0.0]
    next_time = interval_s
    while next_time < traffic_stop_time_s:
        times.append(next_time)
        next_time += interval_s
    if not math.isclose(times[-1], traffic_stop_time_s):
        times.append(float(traffic_stop_time_s))
    if len(times) <= limit:
        return times
    return [
        float(traffic_stop_time_s) * index / (limit - 1)
        for index in range(limit)
    ]


def route_plot_times_text(times):
    return ",".join(format_seconds(value) for value in times)


def scenario_set_text(scenarios):
    selected_ids = {scenario["scenario_id"] for scenario in scenarios}
    return ",".join(
        scenario["scenario_id"]
        for scenario in SCENARIOS
        if scenario["scenario_id"] in selected_ids
    )


def selected_scenarios(values):
    if not values:
        return list(SCENARIOS)
    requested = []
    for value in values:
        requested.extend(item.strip() for item in value.split(",") if item.strip())
    by_id = {scenario["scenario_id"].upper(): scenario for scenario in SCENARIOS}
    result = []
    for scenario_id in requested:
        key = scenario_id.upper()
        if key not in by_id:
            raise ValueError(
                "Unknown scenario %s; choose from %s"
                % (scenario_id, ", ".join(s["scenario_id"] for s in SCENARIOS))
            )
        if by_id[key] not in result:
            result.append(by_id[key])
    return result


def common_args(
    scenario,
    simulation_end_time_s=DEFAULT_SIMULATION_END_TIME_S,
    traffic_stop_time_s=DEFAULT_TRAFFIC_STOP_TIME_S,
):
    args = [
        "--traffic-mode",
        "core_isl_hotspot_specific",
        "--src-node-id",
        "754",
        "--dst-node-id",
        "785",
        "--load-level",
        str(scenario["load_level"]),
        "--simulation-end-time-s",
        format_seconds(simulation_end_time_s),
        "--traffic-stop-time-s",
        format_seconds(traffic_stop_time_s),
        "--background-flow-count",
        str(scenario["background_flow_count"]),
        "--per-flow-rate-reference-background-flow-count",
        "4",
        "--isl-data-rate-megabit-per-s",
        "10",
        "--gsl-data-rate-megabit-per-s",
        "100",
        "--lohi-management-mode",
        "control_plane_only",
        "--algorithms",
    ] + ALGORITHMS
    args.extend(
        [
            "--backpressure-queue-source",
            BACKPRESSURE_QUEUE_SOURCE,
            "--backpressure-fallback",
            BACKPRESSURE_FALLBACK,
            "--backpressure-loop-guard",
            BACKPRESSURE_LOOP_GUARD,
            "--backpressure-diagnostics-sample-limit",
            str(BACKPRESSURE_DIAGNOSTICS_SAMPLE_LIMIT),
        ]
    )
    args.append(
        "--backpressure-diagnostics"
        if BACKPRESSURE_DIAGNOSTICS
        else "--no-backpressure-diagnostics"
    )
    return args


def run_name_for_scenario(
    scenario,
    simulation_end_time_s=DEFAULT_SIMULATION_END_TIME_S,
    traffic_stop_time_s=DEFAULT_TRAFFIC_STOP_TIME_S,
):
    runs = get_udp_pdr_run_list(
        selected_mode="core_isl_hotspot_specific",
        load_levels=[scenario["load_level"]],
        algorithms=[ALGORITHMS[0]],
        simulation_end_time_s_override=simulation_end_time_s,
        traffic_stop_time_s_override=traffic_stop_time_s,
        background_flow_count_override=[scenario["background_flow_count"]],
        per_flow_rate_reference_background_flow_count_override=4,
        src_node_id_override=754,
        dst_node_id_override=785,
        lohi_management_mode_override="control_plane_only",
        isl_data_rate_megabit_per_s_override=10,
        gsl_data_rate_megabit_per_s_override=100,
        backpressure_queue_source_override=BACKPRESSURE_QUEUE_SOURCE,
        backpressure_fallback_override=BACKPRESSURE_FALLBACK,
        backpressure_loop_guard_override=BACKPRESSURE_LOOP_GUARD,
        backpressure_diagnostics_override=BACKPRESSURE_DIAGNOSTICS,
        backpressure_diagnostics_sample_limit_override=(
            BACKPRESSURE_DIAGNOSTICS_SAMPLE_LIMIT
        ),
    )
    return runs[0]["name"]


def planned_commands(
    scenario,
    force,
    simulation_end_time_s=DEFAULT_SIMULATION_END_TIME_S,
    traffic_stop_time_s=DEFAULT_TRAFFIC_STOP_TIME_S,
    rtt_sample_interval_s=None,
    route_plot_times=None,
):
    args = common_args(
        scenario,
        simulation_end_time_s,
        traffic_stop_time_s,
    )
    if rtt_sample_interval_s is None:
        rtt_sample_interval_s = default_rtt_sample_interval_s(
            simulation_end_time_s
        )
    if route_plot_times is None:
        route_plot_times = default_route_plot_times(traffic_stop_time_s)
    step1 = [sys.executable, "step_1_generate_runs.py"] + args
    if force:
        step1.append("--force")
    step2 = [sys.executable, "step_2_run.py"] + args
    step3 = (
        [sys.executable, "step_3_generate_plots.py"]
        + args
        + [
            "--enable-rtt-analysis",
            "--rtt-sample-interval-s",
            format_seconds(rtt_sample_interval_s),
            "--enable-route-visualization",
            "--route-plot-times",
            route_plot_times_text(route_plot_times),
        ]
    )
    return step1, step2, step3


def format_command(command, env=None):
    prefix = ""
    if env:
        prefix = " ".join("%s=%s" % item for item in sorted(env.items())) + " "
    return prefix + " ".join(command)


def run_command(command, log_path, extra_env=None):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    print("\n$ %s" % format_command(command, extra_env))
    with open(log_path, "w") as log:
        process = subprocess.Popen(
            command,
            cwd=SCRIPT_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in process.stdout:
            print(line, end="")
            log.write(line)
        return process.wait()


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, newline="") as f_in:
            return list(csv.DictReader(f_in))
    except (OSError, csv.Error):
        return []


def formal_metadata(
    scenario,
    simulation_end_time_s=DEFAULT_SIMULATION_END_TIME_S,
    traffic_stop_time_s=DEFAULT_TRAFFIC_STOP_TIME_S,
    scenarios=None,
    rtt_sample_interval_s=None,
    route_plot_times=None,
):
    if scenarios is None:
        scenarios = [scenario]
    if rtt_sample_interval_s is None:
        rtt_sample_interval_s = default_rtt_sample_interval_s(
            simulation_end_time_s
        )
    if route_plot_times is None:
        route_plot_times = default_route_plot_times(traffic_stop_time_s)
    return {
        "scenario_set": scenario_set_text(scenarios),
        "scenario_id": scenario["scenario_id"],
        "hotspot_reference_load_percent": scenario[
            "hotspot_reference_load_percent"
        ],
        "global_offered_isl_load_percent": scenario[
            "global_offered_isl_load_percent"
        ],
        "target_corridor_offered_load_percent": scenario[
            "target_corridor_offered_load_percent"
        ],
        "peak_reference_link_offered_load_percent": scenario[
            "peak_reference_link_offered_load_percent"
        ],
        "hotspot_traffic_load_label": scenario["label"],
        "observed_pressure_condition_from_10s_calibration": scenario[
            "observed_pressure_condition"
        ],
        "duration_label": duration_label(
            simulation_end_time_s,
            traffic_stop_time_s,
        ),
        "simulation_end_time_s": simulation_end_time_s,
        "traffic_stop_time_s": traffic_stop_time_s,
        "formal_duration_s": simulation_end_time_s,
        "formal_traffic_stop_s": traffic_stop_time_s,
        "rtt_sample_interval_s": rtt_sample_interval_s,
        "route_plot_count": len(route_plot_times),
        "route_plot_times_s": route_plot_times,
        "lohi_management_mode": "control_plane_only",
        "lhtr_diagnostics_enabled": True,
        "rtt_analysis_enabled": True,
        "route_visualization_enabled": True,
    }


def augment_run_metadata(
    scenario,
    run_dir,
    simulation_end_time_s=DEFAULT_SIMULATION_END_TIME_S,
    traffic_stop_time_s=DEFAULT_TRAFFIC_STOP_TIME_S,
    scenarios=None,
    rtt_sample_interval_s=None,
    route_plot_times=None,
):
    metadata = formal_metadata(
        scenario,
        simulation_end_time_s,
        traffic_stop_time_s,
        scenarios,
        rtt_sample_interval_s,
        route_plot_times,
    )
    with open(os.path.join(run_dir, "formal_scenario.json"), "w") as f_out:
        json.dump(metadata, f_out, indent=2, sort_keys=True)
        f_out.write("\n")
    for algorithm in ALGORITHMS:
        path = os.path.join(run_dir, algorithm, "run_metadata.json")
        if not os.path.exists(path):
            continue
        with open(path) as f_in:
            payload = json.load(f_in)
        payload.update(metadata)
        payload["formal_experiment"] = dict(metadata)
        with open(path, "w") as f_out:
            json.dump(payload, f_out, indent=2, sort_keys=True)
            f_out.write("\n")


def manifest_row(
    scenario,
    simulation_end_time_s=DEFAULT_SIMULATION_END_TIME_S,
    traffic_stop_time_s=DEFAULT_TRAFFIC_STOP_TIME_S,
    scenarios=None,
):
    if scenarios is None:
        scenarios = [scenario]
    run_name = run_name_for_scenario(
        scenario,
        simulation_end_time_s,
        traffic_stop_time_s,
    )
    return {
        "scenario_set": scenario_set_text(scenarios),
        "simulation_end_time_s": simulation_end_time_s,
        "traffic_stop_time_s": traffic_stop_time_s,
        "duration_label": duration_label(
            simulation_end_time_s,
            traffic_stop_time_s,
        ),
        "scenario_id": scenario["scenario_id"],
        "load_level": scenario["load_level"],
        "background_flow_count": scenario["background_flow_count"],
        "hotspot_reference_load_percent": scenario[
            "hotspot_reference_load_percent"
        ],
        "global_offered_isl_load_percent": scenario[
            "global_offered_isl_load_percent"
        ],
        "label": scenario["label"],
        "run_folder": os.path.join("runs", run_name),
        "status": "planned",
        "step1_status": "pending",
        "step2_status": "pending",
        "step3_status": "pending",
        "notes": "",
    }


def float_value(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def bool_text(value):
    return "true" if value else "false"


def background_pdr(per_flow_rows, algorithm):
    rows = [
        row
        for row in per_flow_rows
        if row.get("algorithm") == algorithm
        and row.get("flow_class") == "background"
    ]
    sent = sum(float_value(row.get("sent_packets")) or 0 for row in rows)
    received = sum(float_value(row.get("received_packets")) or 0 for row in rows)
    return received / sent if sent else None


def dominant_loss(loss_rows, algorithm):
    row = next(
        (item for item in loss_rows if item.get("algorithm") == algorithm),
        None,
    )
    if row is None:
        return ""
    fields = [
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
    values = [(field, float_value(row.get(field)) or 0) for field in fields]
    field, value = max(values, key=lambda item: item[1])
    return "%s:%g" % (field, value)


def max_by_algorithm(rows, algorithm, field):
    values = [
        float_value(row.get(field))
        for row in rows
        if row.get("algorithm") == algorithm
    ]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def sum_lhtr_field(rows, field):
    return sum(float_value(row.get(field)) or 0 for row in rows)


def top_lhtr_reasons(rows, limit=5):
    counts = Counter()
    for row in rows:
        count = float_value(row.get("count"))
        if count is not None:
            counts[row.get("decision_reason", "")] += count
    return ";".join(
        "%s:%g" % (reason, count)
        for reason, count in counts.most_common(limit)
        if reason
    )


def build_summary(
    scenarios,
    simulation_end_time_s=DEFAULT_SIMULATION_END_TIME_S,
    traffic_stop_time_s=DEFAULT_TRAFFIC_STOP_TIME_S,
    route_plot_times=None,
):
    if route_plot_times is None:
        route_plot_times = default_route_plot_times(traffic_stop_time_s)
    selected_set = scenario_set_text(scenarios)
    selected_duration_label = duration_label(
        simulation_end_time_s,
        traffic_stop_time_s,
    )
    rows = []
    for scenario in scenarios:
        run_name = run_name_for_scenario(
            scenario,
            simulation_end_time_s,
            traffic_stop_time_s,
        )
        run_dir = os.path.join(RUNS_DIR, run_name)
        comparison = os.path.join(run_dir, "comparison_packet_delivery")
        core = os.path.join(comparison, "core")
        diagnostics = os.path.join(comparison, "diagnostics")
        summary_rows = read_csv(os.path.join(core, "summary_by_algorithm.csv"))
        per_flow_rows = read_csv(os.path.join(core, "per_flow_delivery.csv"))
        loss_rows = read_csv(
            os.path.join(core, "loss_attribution_breakdown_v3.csv")
        )
        isl_rows = read_csv(
            os.path.join(diagnostics, "max_queue_occupancy_by_algorithm.csv")
        )
        gsl_rows = read_csv(os.path.join(diagnostics, "gsl_queue_summary.csv"))
        rtt_rows = read_csv(
            os.path.join(core, "udp_rtt_summary_by_algorithm.csv")
        )
        lhtr_br_rows = read_csv(
            os.path.join(diagnostics, "lhtr_br_sbr_summary.csv")
        )
        lhtr_reason_rows = read_csv(
            os.path.join(diagnostics, "lhtr_decision_reason_summary.csv")
        )

        for algorithm in ALGORITHMS:
            notes = []
            algorithm_dir = os.path.join(run_dir, algorithm)
            console_path = os.path.join(algorithm_dir, "logs_ns3", "console.txt")
            finished_path = os.path.join(algorithm_dir, "logs_ns3", "finished.txt")
            console_ok = False
            if os.path.exists(console_path):
                try:
                    with open(console_path, errors="replace") as f_in:
                        console_ok = "BASIC SIMULATION END" in f_in.read()
                except OSError:
                    pass
            finished = os.path.exists(finished_path) and console_ok
            summary = next(
                (
                    item
                    for item in summary_rows
                    if item.get("algorithm") == algorithm
                ),
                {},
            )
            rtt = next(
                (
                    item
                    for item in rtt_rows
                    if item.get("algorithm") == algorithm
                    and item.get("direction") == "754_to_785"
                ),
                {},
            )
            route_plots = glob.glob(
                os.path.join(
                    comparison,
                    "graphical_routes",
                    algorithm + "_focus_*.png",
                )
            )
            if not summary:
                notes.append("missing packet-delivery summary")
            if not rtt:
                notes.append("missing RTT summary")
            expected_route_plots = len(route_plot_times) * 3
            if len(route_plots) < expected_route_plots:
                notes.append("missing route plots")
            if algorithm == "algorithm_lhtr":
                source_dir = os.path.join(algorithm_dir, "lhtr_diagnostics")
                missing = [
                    filename
                    for filename in LHTR_REQUIRED_FILES
                    if not os.path.exists(os.path.join(source_dir, filename))
                ]
                if missing:
                    notes.append("incomplete LHTR diagnostics: " + ",".join(missing))
            if algorithm == "algorithm_lohi":
                lohi_dir = os.path.join(
                    algorithm_dir,
                    "lohi_manager_diagnostics",
                )
                if not os.path.isdir(lohi_dir):
                    notes.append("missing LoHi manager diagnostics")
            if algorithm == "algorithm_backpressure_over_isls":
                source_dir = os.path.join(
                    algorithm_dir,
                    "backpressure_diagnostics",
                )
                missing = [
                    filename
                    for filename in BACKPRESSURE_REQUIRED_FILES
                    if not os.path.exists(os.path.join(source_dir, filename))
                ]
                if missing:
                    notes.append(
                        "incomplete Backpressure diagnostics: "
                        + ",".join(missing)
                    )
            background_value = background_pdr(per_flow_rows, algorithm)

            rows.append(
                {
                    "scenario_set": selected_set,
                    "simulation_end_time_s": simulation_end_time_s,
                    "traffic_stop_time_s": traffic_stop_time_s,
                    "duration_label": selected_duration_label,
                    "scenario_id": scenario["scenario_id"],
                    "load_level": scenario["load_level"],
                    "background_flow_count": scenario["background_flow_count"],
                    "hotspot_reference_load_percent": scenario[
                        "hotspot_reference_load_percent"
                    ],
                    "global_offered_isl_load_percent": scenario[
                        "global_offered_isl_load_percent"
                    ],
                    "algorithm": algorithm,
                    "finished": bool_text(finished),
                    "console_ok": bool_text(console_ok),
                    "aggregate_pdr": summary.get("aggregate_pdr", ""),
                    "focus_pdr": summary.get("focus_flow_pdr", ""),
                    "background_pdr": (
                        background_value if background_value is not None else ""
                    ),
                    "lost_packets": summary.get("total_lost_packets", ""),
                    "dominant_loss_attribution": dominant_loss(
                        loss_rows,
                        algorithm,
                    ),
                    "max_isl_queue": max_by_algorithm(
                        isl_rows,
                        algorithm,
                        "packet_max",
                    ),
                    "max_gsl_queue": max_by_algorithm(
                        gsl_rows,
                        algorithm,
                        "max_gsl_queue_pkt",
                    ),
                    "queue_aware_rtt_mean_ms_if_available": rtt.get(
                        "mean_queue_aware_rtt_ms",
                        "",
                    ),
                    "queue_aware_rtt_p95_ms_if_available": rtt.get(
                        "p95_queue_aware_rtt_ms",
                        "",
                    ),
                    "lhtr_br_selected_count_if_available": (
                        sum_lhtr_field(lhtr_br_rows, "br_selected_count")
                        if algorithm == "algorithm_lhtr"
                        else ""
                    ),
                    "lhtr_sbr_selected_count_if_available": (
                        sum_lhtr_field(lhtr_br_rows, "sbr_selected_count")
                        if algorithm == "algorithm_lhtr"
                        else ""
                    ),
                    "lhtr_fallback_count_if_available": (
                        sum_lhtr_field(lhtr_br_rows, "fallback_count")
                        if algorithm == "algorithm_lhtr"
                        else ""
                    ),
                    "lhtr_yellow_count_if_available": (
                        sum_lhtr_field(lhtr_br_rows, "yellow_count")
                        if algorithm == "algorithm_lhtr"
                        else ""
                    ),
                    "lhtr_red_count_if_available": (
                        sum_lhtr_field(lhtr_br_rows, "red_count")
                        if algorithm == "algorithm_lhtr"
                        else ""
                    ),
                    "lhtr_top_decision_reasons_if_available": (
                        top_lhtr_reasons(lhtr_reason_rows)
                        if algorithm == "algorithm_lhtr"
                        else ""
                    ),
                    "route_plots_exist": bool_text(
                        len(route_plots) >= expected_route_plots
                    ),
                    "notes": "; ".join(notes),
                }
            )
    return rows


def write_status(
    manifest_rows,
    summary_rows,
    status_path,
    simulation_end_time_s,
    traffic_stop_time_s,
    rtt_sample_interval_s,
    route_plot_times,
):
    complete = sum(
        1
        for row in summary_rows
        if row["finished"] == "true" and not row["notes"]
    )
    with open(status_path, "w") as f_out:
        f_out.write(
            "# Hotspot Formal Status (%s)\n\n"
            % duration_label(simulation_end_time_s, traffic_stop_time_s)
        )
        f_out.write(
            "Fixed configuration: `src754 <-> dst785`, ISL 10 Mbps, "
            "GSL 100 Mbps, simulation %s s, traffic stop %s s, "
            "LoHi `control_plane_only`, LHTR diagnostics enabled, "
            "RTT interval %s s, route times `%s`.\n\n"
            % (
                format_seconds(simulation_end_time_s),
                format_seconds(traffic_stop_time_s),
                format_seconds(rtt_sample_interval_s),
                route_plot_times_text(route_plot_times),
            )
        )
        f_out.write("## Scenario Status\n\n")
        f_out.write("| Scenario | Run folder | Step 1 | Step 2 | Step 3 | Status |\n")
        f_out.write("| --- | --- | --- | --- | --- | --- |\n")
        for row in manifest_rows:
            f_out.write(
                "| {scenario_id} | `{run_folder}` | {step1_status} | "
                "{step2_status} | {step3_status} | {status} |\n".format(**row)
            )
        f_out.write("\n## Completion\n\n")
        f_out.write(
            "- Complete algorithm rows without warnings: %d/%d\n"
            % (complete, len(summary_rows))
        )
        warnings = [
            "%s/%s: %s"
            % (row["scenario_id"], row["algorithm"], row["notes"])
            for row in summary_rows
            if row["notes"]
        ]
        if warnings:
            f_out.write("- Warnings:\n")
            for warning in warnings:
                f_out.write("  - %s\n" % warning)
        else:
            f_out.write("- Warnings: none\n")


def rebuild_existing_reports(
    scenarios,
    simulation_end_time_s,
    traffic_stop_time_s,
    paths,
    rtt_sample_interval_s,
    route_plot_times,
):
    manifest_rows = [
        manifest_row(
            scenario,
            simulation_end_time_s,
            traffic_stop_time_s,
            scenarios,
        )
        for scenario in scenarios
    ]
    summary_rows = build_summary(
        scenarios,
        simulation_end_time_s,
        traffic_stop_time_s,
        route_plot_times,
    )
    by_scenario = {}
    for summary_row in summary_rows:
        by_scenario.setdefault(summary_row["scenario_id"], []).append(summary_row)
    for row in manifest_rows:
        scenario_rows = by_scenario.get(row["scenario_id"], [])
        run_dir = os.path.join(SCRIPT_DIR, row["run_folder"])
        generated = all(
            os.path.exists(
                os.path.join(run_dir, algorithm, "run_metadata.json")
            )
            for algorithm in ALGORITHMS
        )
        finished = bool(scenario_rows) and all(
            item["finished"] == "true" for item in scenario_rows
        )
        warnings = [
            "%s: %s" % (item["algorithm"], item["notes"])
            for item in scenario_rows
            if item["notes"]
        ]
        row["step1_status"] = "ok" if generated else "missing"
        row["step2_status"] = "ok" if finished else "incomplete"
        row["step3_status"] = (
            "ok" if finished and not warnings else "incomplete"
        )
        if finished and not warnings:
            row["status"] = "complete"
        elif generated and not finished:
            row["status"] = "generated_or_partial"
        else:
            row["status"] = "incomplete_warning"
        row["notes"] = " | ".join(warnings)
    write_csv(paths["manifest_path"], manifest_rows, MANIFEST_FIELDS)
    write_csv(paths["summary_path"], summary_rows, SUMMARY_FIELDS)
    write_status(
        manifest_rows,
        summary_rows,
        paths["status_path"],
        simulation_end_time_s,
        traffic_stop_time_s,
        rtt_sample_interval_s,
        route_plot_times,
    )
    return manifest_rows, summary_rows


def scenarios_from_manifest_rows(rows):
    scenario_ids = {row.get("scenario_id") for row in rows}
    return [
        scenario
        for scenario in SCENARIOS
        if scenario["scenario_id"] in scenario_ids
    ]


def merge_manifest_rows(
    existing_rows,
    planned_rows,
    simulation_end_time_s,
    traffic_stop_time_s,
):
    by_id = {
        row.get("scenario_id"): row
        for row in existing_rows
        if row.get("scenario_id")
    }
    by_id.update({row["scenario_id"]: row for row in planned_rows})
    merged_scenarios = [
        scenario
        for scenario in SCENARIOS
        if scenario["scenario_id"] in by_id
    ]
    selected_set = scenario_set_text(merged_scenarios)
    merged = []
    for scenario in merged_scenarios:
        row = by_id[scenario["scenario_id"]]
        row["scenario_set"] = selected_set
        row["simulation_end_time_s"] = simulation_end_time_s
        row["traffic_stop_time_s"] = traffic_stop_time_s
        row["duration_label"] = duration_label(
            simulation_end_time_s,
            traffic_stop_time_s,
        )
        merged.append(row)
    return merged


def main():
    args = parse_args()
    global ALGORITHMS
    global BACKPRESSURE_QUEUE_SOURCE
    global BACKPRESSURE_FALLBACK
    global BACKPRESSURE_LOOP_GUARD
    global BACKPRESSURE_DIAGNOSTICS
    global BACKPRESSURE_DIAGNOSTICS_SAMPLE_LIMIT
    ALGORITHMS = list(args.algorithms)
    BACKPRESSURE_QUEUE_SOURCE = args.backpressure_queue_source
    BACKPRESSURE_FALLBACK = args.backpressure_fallback
    BACKPRESSURE_LOOP_GUARD = args.backpressure_loop_guard
    BACKPRESSURE_DIAGNOSTICS = args.backpressure_diagnostics
    BACKPRESSURE_DIAGNOSTICS_SAMPLE_LIMIT = (
        args.backpressure_diagnostics_sample_limit
    )
    simulation_end_time_s = args.simulation_end_time_s
    traffic_stop_time_s = args.traffic_stop_time_s
    paths = output_paths(simulation_end_time_s, traffic_stop_time_s)
    rtt_sample_interval_s = (
        args.rtt_sample_interval_s
        if args.rtt_sample_interval_s is not None
        else default_rtt_sample_interval_s(simulation_end_time_s)
    )
    route_plot_times = (
        parse_route_plot_times(args.route_plot_times, traffic_stop_time_s)
        if args.route_plot_times is not None
        else default_route_plot_times(traffic_stop_time_s)
    )
    try:
        scenarios = selected_scenarios(args.scenarios)
    except ValueError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 2

    if args.aggregate_only:
        existing_rows = read_csv(paths["manifest_path"])
        report_scenarios = scenarios_from_manifest_rows(existing_rows)
        selected_ids = {scenario["scenario_id"] for scenario in scenarios}
        known_ids = {scenario["scenario_id"] for scenario in report_scenarios}
        report_scenarios.extend(
            scenario
            for scenario in scenarios
            if scenario["scenario_id"] in selected_ids
            and scenario["scenario_id"] not in known_ids
        )
        report_scenarios = [
            scenario
            for scenario in SCENARIOS
            if scenario in report_scenarios
        ]
        os.makedirs(paths["report_dir"], exist_ok=True)
        os.makedirs(RUNS_DIR, exist_ok=True)
        rebuild_existing_reports(
            report_scenarios,
            simulation_end_time_s,
            traffic_stop_time_s,
            paths,
            rtt_sample_interval_s,
            route_plot_times,
        )
        print("Manifest: %s" % paths["manifest_path"])
        print("Summary: %s" % paths["summary_path"])
        print("Status: %s" % paths["status_path"])
        return 0

    planned_rows = [
        manifest_row(
            scenario,
            simulation_end_time_s,
            traffic_stop_time_s,
            scenarios,
        )
        for scenario in scenarios
    ]
    manifest_rows = merge_manifest_rows(
        read_csv(paths["manifest_path"]),
        planned_rows,
        simulation_end_time_s,
        traffic_stop_time_s,
    )
    by_scenario = {row["scenario_id"]: row for row in manifest_rows}

    print(
        "Selected formal scenarios: simulation=%s s, traffic_stop=%s s, "
        "RTT interval=%s s, route times=%s"
        % (
            format_seconds(simulation_end_time_s),
            format_seconds(traffic_stop_time_s),
            format_seconds(rtt_sample_interval_s),
            route_plot_times_text(route_plot_times),
        )
    )
    for scenario in scenarios:
        print(
            "  %s load=%g bg=%d hotspot=%.3f%% global=%.3f%% label=%s"
            % (
                scenario["scenario_id"],
                scenario["load_level"],
                scenario["background_flow_count"],
                scenario["hotspot_reference_load_percent"],
                scenario["global_offered_isl_load_percent"],
                scenario["label"],
            )
        )
        print(
            "    run folder: runs/%s"
            % run_name_for_scenario(
                scenario,
                simulation_end_time_s,
                traffic_stop_time_s,
            )
        )
        step1, step2, step3 = planned_commands(
            scenario,
            args.force,
            simulation_end_time_s,
            traffic_stop_time_s,
            rtt_sample_interval_s,
            route_plot_times,
        )
        print("    step 1: %s" % format_command(step1))
        print(
            "    step 2: %s"
            % format_command(
                step2,
                {
                    "LHTR_ENABLE_DIAGNOSTICS": "1",
                    "LHTR_DIAGNOSTICS_DIR": "lhtr_diagnostics",
                },
            )
        )
        print("    step 3: %s" % format_command(step3))

    if args.dry_run:
        print("\nDry run complete; no files were created or modified.")
        return 0

    existing = [
        row["run_folder"]
        for row in planned_rows
        if os.path.isdir(os.path.join(SCRIPT_DIR, row["run_folder"]))
    ]
    if existing and not args.force:
        print(
            "\nRefusing to overwrite existing formal run folders without --force:",
            file=sys.stderr,
        )
        for path in existing:
            print("  %s" % path, file=sys.stderr)
        return 2
    if existing:
        print("\n--force will regenerate these timing-isolated folders:")
        for path in existing:
            print("  %s" % path)

    os.makedirs(paths["report_dir"], exist_ok=True)
    os.makedirs(RUNS_DIR, exist_ok=True)
    write_csv(paths["manifest_path"], manifest_rows, MANIFEST_FIELDS)

    any_failure = False
    for scenario in scenarios:
        scenario_id = scenario["scenario_id"]
        row = by_scenario[scenario_id]
        run_dir = os.path.join(
            RUNS_DIR,
            run_name_for_scenario(
                scenario,
                simulation_end_time_s,
                traffic_stop_time_s,
            ),
        )
        step1, step2, step3 = planned_commands(
            scenario,
            args.force,
            simulation_end_time_s,
            traffic_stop_time_s,
            rtt_sample_interval_s,
            route_plot_times,
        )
        log_dir = os.path.join(
            paths["report_dir"],
            "logs",
            scenario_id.replace("+", "plus"),
        )

        rc = run_command(step1, os.path.join(log_dir, "step1.log"))
        row["step1_status"] = "ok" if rc == 0 else "failed"
        if rc != 0:
            row["status"] = "failed"
            row["notes"] = "step 1 failed"
            row["step2_status"] = "not_run"
            row["step3_status"] = "not_run"
            any_failure = True
            write_csv(paths["manifest_path"], manifest_rows, MANIFEST_FIELDS)
            continue
        report_scenarios = scenarios_from_manifest_rows(manifest_rows)
        augment_run_metadata(
            scenario,
            run_dir,
            simulation_end_time_s,
            traffic_stop_time_s,
            report_scenarios,
            rtt_sample_interval_s,
            route_plot_times,
        )

        if args.generation_only:
            row["status"] = "generated"
            row["step2_status"] = "not_requested"
            row["step3_status"] = "not_requested"
            write_csv(paths["manifest_path"], manifest_rows, MANIFEST_FIELDS)
            continue

        if args.skip_step2:
            row["step2_status"] = "skipped"
        else:
            rc = run_command(
                step2,
                os.path.join(log_dir, "step2.log"),
                {
                    "LHTR_ENABLE_DIAGNOSTICS": "1",
                    "LHTR_DIAGNOSTICS_DIR": "lhtr_diagnostics",
                },
            )
            row["step2_status"] = "ok" if rc == 0 else "failed"
            if rc != 0:
                row["status"] = "failed"
                row["notes"] = "step 2 failed"
                row["step3_status"] = "not_run"
                any_failure = True
                write_csv(paths["manifest_path"], manifest_rows, MANIFEST_FIELDS)
                continue

        if args.skip_step3:
            row["step3_status"] = "skipped"
            row["status"] = "simulation_complete"
        else:
            rc = run_command(step3, os.path.join(log_dir, "step3.log"))
            row["step3_status"] = "ok" if rc == 0 else "failed"
            row["status"] = "complete" if rc == 0 else "incomplete"
            if rc != 0:
                row["notes"] = "step 3 failed"
                any_failure = True
        write_csv(paths["manifest_path"], manifest_rows, MANIFEST_FIELDS)

    report_scenarios = scenarios_from_manifest_rows(manifest_rows)
    selected_set = scenario_set_text(report_scenarios)
    for row in manifest_rows:
        row["scenario_set"] = selected_set
    summary_rows = build_summary(
        report_scenarios,
        simulation_end_time_s,
        traffic_stop_time_s,
        route_plot_times,
    )
    warnings_by_scenario = {}
    for summary_row in summary_rows:
        if summary_row["notes"]:
            warnings_by_scenario.setdefault(
                summary_row["scenario_id"],
                [],
            ).append(
                "%s: %s"
                % (summary_row["algorithm"], summary_row["notes"])
            )
    for scenario_id, warnings in warnings_by_scenario.items():
        row = by_scenario[scenario_id]
        if row["status"] == "complete":
            row["status"] = "incomplete_warning"
        if row["status"] not in {"generated", "failed"}:
            row["notes"] = " | ".join(warnings)
    write_csv(paths["manifest_path"], manifest_rows, MANIFEST_FIELDS)
    write_csv(paths["summary_path"], summary_rows, SUMMARY_FIELDS)
    write_status(
        manifest_rows,
        summary_rows,
        paths["status_path"],
        simulation_end_time_s,
        traffic_stop_time_s,
        rtt_sample_interval_s,
        route_plot_times,
    )
    print("\nManifest: %s" % paths["manifest_path"])
    print("Summary: %s" % paths["summary_path"])
    print("Status: %s" % paths["status_path"])
    return 1 if any_failure else 0


if __name__ == "__main__":
    sys.exit(main())
