import argparse
import os
import subprocess
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ALGORITHMS = [
    "algorithm_free_one_only_over_isls",
    "algorithm_queue_aware_over_isls",
]


def _format_command(command):
    return " ".join(command)


def _run(command, dry_run):
    print("\n$ %s" % _format_command(command))
    if not dry_run:
        subprocess.check_call(command, cwd=SCRIPT_DIR)


def _common_args(args, load_level=None, background_flow_count=None):
    values = [
        "--traffic-mode",
        "core_isl_hotspot_specific",
        "--src-node-id",
        str(args.src_node_id),
        "--dst-node-id",
        str(args.dst_node_id),
        "--simulation-end-time-s",
        str(args.duration_s),
        "--traffic-stop-time-s",
        str(args.traffic_stop_s),
        "--per-flow-rate-reference-background-flow-count",
        str(args.per_flow_rate_reference_background_flow_count),
        "--isl-data-rate-megabit-per-s",
        str(args.isl_data_rate_megabit_per_s),
        "--gsl-data-rate-megabit-per-s",
        str(args.gsl_data_rate_megabit_per_s),
        "--algorithms",
    ] + list(args.algorithms)
    if load_level is not None:
        values += ["--load-level", str(load_level)]
    if background_flow_count is not None:
        values += ["--background-flow-count", str(background_flow_count)]
    return values


def main():
    parser = argparse.ArgumentParser(
        description="Run the short ISL-focused UDP/PDR calibration sweep."
    )
    parser.add_argument("--src-node-id", type=int, default=754)
    parser.add_argument("--dst-node-id", type=int, default=785)
    parser.add_argument(
        "--load-levels", nargs="+", type=float, default=[1.0, 1.2, 1.4]
    )
    parser.add_argument(
        "--background-flow-counts", nargs="+", type=int, default=[16, 24, 32]
    )
    parser.add_argument("--duration-s", type=float, default=10.0)
    parser.add_argument("--traffic-stop-s", type=float, default=None)
    parser.add_argument(
        "--per-flow-rate-reference-background-flow-count",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--isl-data-rate-megabit-per-s", type=float, default=10.0
    )
    parser.add_argument(
        "--gsl-data-rate-megabit-per-s", type=float, default=100.0
    )
    parser.add_argument(
        "--algorithms", nargs="+", default=DEFAULT_ALGORITHMS
    )
    parser.add_argument(
        "--generation-only",
        action="store_true",
        help="Generate run directories without starting NS-3 or analysis.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate selected run directories before execution.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    args = parser.parse_args()
    if args.traffic_stop_s is None:
        args.traffic_stop_s = args.duration_s - 2.0
    if args.duration_s <= 0:
        parser.error("--duration-s must be positive")
    if not 0 <= args.traffic_stop_s <= args.duration_s:
        parser.error("--traffic-stop-s must be between zero and --duration-s")

    python = sys.executable
    for background_flow_count in args.background_flow_counts:
        for load_level in args.load_levels:
            print(
                "\n=== ISL-focused calibration bg=%d load=%g ==="
                % (background_flow_count, load_level)
            )
            common = _common_args(
                args,
                load_level=load_level,
                background_flow_count=background_flow_count,
            )
            generate = [python, "step_1_generate_runs.py"] + common
            if args.force:
                generate.append("--force")
            _run(generate, args.dry_run)
            if args.generation_only:
                continue
            _run([python, "step_2_run.py"] + common, args.dry_run)
            _run(
                [python, "step_3_generate_plots.py"]
                + common
                + ["--no-rtt-analysis"],
                args.dry_run,
            )

    if not args.generation_only:
        aggregate = _common_args(args)
        aggregate += ["--load-level"] + [
            str(value) for value in args.load_levels
        ]
        aggregate += ["--background-flow-count"] + [
            str(value) for value in args.background_flow_counts
        ]
        _run(
            [python, "analyze_isl_focused_calibration.py"] + aggregate,
            args.dry_run,
        )


if __name__ == "__main__":
    main()
