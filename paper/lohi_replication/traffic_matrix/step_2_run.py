# Generates the initial fstate_0.txt for each run and then launches the
# dynamic closed-loop NS-3 simulation (mirrors lohi_replication/a_b/run_dynamic_routing.py
# but iterates over all traffic-matrix runs).

import os
import sys
import pickle

sys.path.append(os.path.join(os.path.dirname(__file__)))
from dynamic_run_list import get_tm_dynamic_run_list

sys.path.append("/home/pflin/research/hypatia-pf/satgenpy")
from satgen.dynamic_state.generate_dynamic_state import generate_dynamic_state_at
from satgen.isls import read_isls
from satgen.ground_stations import read_ground_stations_extended
from satgen.tles import read_tles
from satgen.interfaces import read_gsl_interfaces_info

import subprocess


# ---------------------------------------------------------------------------
# Helpers (identical to lohi_replication/a_b/run_dynamic_routing.py)
# ---------------------------------------------------------------------------

SATELLITE_NETWORK_BASE = (
    "/home/pflin/research/hypatia-pf/paper/satellite_networks_state/gen_data"
)
CALCULATE_ROUTES_SCRIPT = (
    "/home/pflin/research/hypatia-pf/paper/lohi_replication/traffic_matrix/calculate_routes.py"
)


def generate_single_fstate(satellite_network_dir, dynamic_state_dir, time_ns,
                            dynamic_state_algorithm, prev_output,
                            queue_stats_file=None, alpha=0.7, beta=0.3, time_step_ns=None):
    ground_stations = read_ground_stations_extended(
        os.path.join(satellite_network_dir, "ground_stations.txt"))
    tles = read_tles(os.path.join(satellite_network_dir, "tles.txt"))
    satellites = tles["satellites"]
    epoch = tles["epoch"]
    list_isls = read_isls(
        os.path.join(satellite_network_dir, "isls.txt"), len(satellites))
    list_gsl_interfaces_info = read_gsl_interfaces_info(
        os.path.join(satellite_network_dir, "gsl_interfaces_info.txt"),
        len(satellites), len(ground_stations))
    with open(os.path.join(satellite_network_dir, "description.txt")) as f:
        lines = f.readlines()
        max_gsl_length_m = float(lines[0].split("=")[1].strip())
        max_isl_length_m = float(lines[1].split("=")[1].strip())

    return generate_dynamic_state_at(
        dynamic_state_dir, epoch, time_ns, satellites, ground_stations,
        list_isls, list_gsl_interfaces_info, max_gsl_length_m, max_isl_length_m,
        dynamic_state_algorithm, prev_output, True, None, None,
        queue_stats_file, alpha, beta, time_step_ns)


def run_ns3_simulation(run_dir_relative):
    """Execute the NS-3 main_satnet binary for the given run directory."""
    cmd = (
        "cd ../../../ns3-sat-sim/simulator; "
        "python3.10 ./waf --run=\"main_satnet "
        "--run_dir='../../paper/lohi_replication/traffic_matrix/%s'\" "
        "2>&1 | tee '../../paper/lohi_replication/traffic_matrix/%s/logs_ns3/console.txt'"
        % (run_dir_relative, run_dir_relative)
    )
    print("\nRunning: %s\n" % cmd)
    result = subprocess.run(cmd, shell=True, executable="/bin/bash")
    if result.returncode != 0:
        raise RuntimeError("NS-3 simulation failed (return code %d)" % result.returncode)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

for run in get_tm_dynamic_run_list():
    run_name = run["name"]
    algorithm = run["dynamic_state_algorithm"]
    run_dir = "runs/%s/%s" % (run_name, algorithm)

    satellite_network_dir = os.path.join(SATELLITE_NETWORK_BASE, run["satellite_network"])
    dynamic_state_dir = os.path.join(run_dir, "dynamic_state")
    prev_output_dir = os.path.join(run_dir, "prev_output_cache")

    print("\n" + "=" * 60)
    print("Run: %s" % run_dir)
    print("=" * 60)

    # ------------------------------------------------------------------
    # Step 1: Generate fstate_0.txt  (t = 0)
    # ------------------------------------------------------------------
    print("\n[Step 1] Generating initial fstate (t=0)...")
    time_step_ns = 100 * 1000 * 1000  # 100 ms
    prev_output = generate_single_fstate(
        satellite_network_dir, dynamic_state_dir,
        0, algorithm, None, time_step_ns=time_step_ns)

    # Persist so calculate_routes.py can load it as prev_output at t=100ms
    if prev_output:
        pkl = os.path.join(prev_output_dir, "prev_output_0.pkl")
        with open(pkl, "wb") as f:
            pickle.dump(prev_output, f, protocol=pickle.HIGHEST_PROTOCOL)
        print("  > Saved initial prev_output → %s" % pkl)

    # ------------------------------------------------------------------
    # Step 2: Launch dynamic closed-loop NS-3 simulation
    # ------------------------------------------------------------------
    print("\n[Step 2] Starting dynamic NS-3 simulation...")
    run_ns3_simulation(run_dir)

print("\nAll runs finished.")