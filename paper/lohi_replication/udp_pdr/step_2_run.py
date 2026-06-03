import os
import pickle
import subprocess
import sys

sys.path.append(os.path.join(os.path.dirname(__file__)))
from dynamic_run_list import build_arg_parser, describe_selection, get_udp_pdr_run_list
from calculate_routes import (
    generate_single_fstate,
    persist_algorithm_state,
    resolve_satellite_network_dir,
    save_prev_output,
)


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
NS3_SIMULATOR_DIR = os.path.join(REPO_ROOT, "ns3-sat-sim", "simulator")


def run_ns3_simulation(run_dir_relative):
    run_dir_abs = os.path.abspath(run_dir_relative)
    logs_dir = os.path.join(run_dir_abs, "logs_ns3")
    os.makedirs(logs_dir, exist_ok=True)
    console_path = os.path.join(logs_dir, "console.txt")

    ns3_python = os.environ.get("NS3_PYTHON", "python3.10")
    run_dir_from_ns3 = os.path.relpath(run_dir_abs, NS3_SIMULATOR_DIR)
    waf_arg = "--run=main_satnet --run_dir='%s'" % run_dir_from_ns3
    cmd = [ns3_python, "./waf", waf_arg]

    print("\nRunning from %s:" % NS3_SIMULATOR_DIR)
    print("  %s" % " ".join(cmd))
    with open(console_path, "w") as console:
        process = subprocess.Popen(
            cmd,
            cwd=NS3_SIMULATOR_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in process.stdout:
            print(line, end="")
            console.write(line)
        return_code = process.wait()

    if return_code != 0:
        raise RuntimeError("NS-3 simulation failed for %s (return code %d)" % (run_dir_relative, return_code))


def generate_initial_fstate(run, run_dir):
    satellite_network_dir = resolve_satellite_network_dir(run_dir)
    dynamic_state_dir = os.path.join(run_dir, "dynamic_state")
    prev_output_dir = os.path.join(run_dir, "prev_output_cache")
    os.makedirs(dynamic_state_dir, exist_ok=True)
    os.makedirs(prev_output_dir, exist_ok=True)

    print("\n[Step 1] Generating initial fstate (t=0)...")
    prev_output = generate_single_fstate(
        satellite_network_dir,
        dynamic_state_dir,
        0,
        run["dynamic_state_algorithm"],
        None,
        time_step_ns=run["dynamic_state_update_interval_ns"],
    )

    if prev_output:
        save_prev_output(prev_output, prev_output_dir, 0)
    persist_algorithm_state(
        run["dynamic_state_algorithm"],
        prev_output_dir,
        0,
        0,
        run["dynamic_state_update_interval_ns"],
    )


def validate_run_dir(run_dir):
    required = [
        "config_ns3.properties",
        "udp_burst_schedule.csv",
    ]
    for filename in required:
        path = os.path.join(run_dir, filename)
        if not os.path.exists(path):
            raise RuntimeError(
                "Required run file not found: %s. Generate runs first with step_1_generate_runs.py."
                % path
            )


def main():
    parser = build_arg_parser("Run UDP/PDR dynamic closed-loop NS-3 simulations.")
    args = parser.parse_args()
    selected_mode, modes, load_levels, algorithms = describe_selection(args)
    print("Traffic mode selection: %s (%s)" % (selected_mode, ", ".join(modes)))
    print("Load levels: %s" % ", ".join("%.3f" % x for x in load_levels))
    print("Algorithms: %s" % ", ".join(algorithms))

    for run in get_udp_pdr_run_list(
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
    ):
        run_dir = os.path.join("runs", run["name"], run["dynamic_state_algorithm"])
        validate_run_dir(run_dir)

        print("\n" + "=" * 70)
        print("Run: %s" % run_dir)
        print(
            "Timing: simulation_end=%.6fs, traffic_stop=%.6fs, drain=%.6fs"
            % (
                run["simulation_end_time_s"],
                run["traffic_stop_time_s"],
                run["drain_time_s"],
            )
        )
        print("=" * 70)
        generate_initial_fstate(run, run_dir)

        print("\n[Step 2] Starting dynamic NS-3 simulation...")
        run_ns3_simulation(run_dir)

    print("\nAll runs finished.")


if __name__ == "__main__":
    main()
