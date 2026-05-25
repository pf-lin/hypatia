import argparse
import os
import pickle
import sys

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-udp-pdr")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

import pandas as pd

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.append(os.path.join(REPO_ROOT, "satgenpy"))

from satgen.dynamic_state.generate_dynamic_state import generate_dynamic_state_at
from satgen.ground_stations import read_ground_stations_extended
from satgen.interfaces import read_gsl_interfaces_info
from satgen.isls import read_isls
from satgen.tles import read_tles


def read_properties(path):
    props = {}
    with open(path) as f_in:
        for raw_line in f_in:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip().strip('"')
    return props


def resolve_satellite_network_dir(run_dir):
    props = read_properties(os.path.join(run_dir, "config_ns3.properties"))
    rel_path = props["satellite_network_dir"]
    return os.path.abspath(os.path.join(run_dir, rel_path))


def read_dynamic_interval_ns(run_dir):
    props = read_properties(os.path.join(run_dir, "config_ns3.properties"))
    return int(props["dynamic_state_update_interval_ns"])


def process_queue_statistics(logs_dir, output_file):
    isl_queue_file = os.path.join(logs_dir, "isl_queue_pkt.csv")
    if not os.path.exists(isl_queue_file):
        print("Warning: %s not found" % isl_queue_file)
        return None

    df = pd.read_csv(
        isl_queue_file,
        header=None,
        names=["from", "to", "interval_start_ns", "interval_end_ns", "num_packets"],
    )
    print("  > Read %d records from %s" % (len(df), isl_queue_file))

    if len(df) == 0:
        result = pd.DataFrame(columns=["from", "to", "packet_max"])
    else:
        result = (
            df.groupby(["from", "to"])["num_packets"]
            .max()
            .reset_index(name="packet_max")
        )
        result = result[result["packet_max"] > 0]

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    result.to_csv(output_file, index=False)

    print("  > Processed %d active links" % len(result))
    print("  > Max queue size: %d" % (result["packet_max"].max() if len(result) > 0 else 0))
    print("  > Saved to: %s" % output_file)
    return output_file


def save_prev_output(prev_output, output_dir, time_ns):
    if prev_output is None:
        return
    pkl = os.path.join(output_dir, "prev_output_%d.pkl" % time_ns)
    with open(pkl, "wb") as f_out:
        pickle.dump(prev_output, f_out, protocol=pickle.HIGHEST_PROTOCOL)
    print("  > Saved prev_output -> %s" % pkl)


def load_prev_output(output_dir, prev_time_ns):
    pkl = os.path.join(output_dir, "prev_output_%d.pkl" % prev_time_ns)
    if not os.path.exists(pkl):
        print("  > No previous output found at: %s" % pkl)
        return None
    with open(pkl, "rb") as f_in:
        prev_output = pickle.load(f_in)
    print("  > Loaded prev_output from: %s" % pkl)
    if prev_output and "fstate" in prev_output:
        print("    >> Previous fstate contains %d entries" % len(prev_output["fstate"]))
    return prev_output


def get_algorithm_state_handlers(dynamic_state_algorithm):
    if dynamic_state_algorithm == "algorithm_lhtr":
        from satgen.dynamic_state.algorithm_lhtr import load_lhtr_state, save_lhtr_state

        return "LHTR", "lhtr_state", load_lhtr_state, save_lhtr_state

    if dynamic_state_algorithm == "algorithm_lohi":
        from satgen.dynamic_state.algorithm_lohi import load_lohi_state, save_lohi_state

        return "LoHi", "lohi_state", load_lohi_state, save_lohi_state

    return None


def restore_algorithm_state(dynamic_state_algorithm, output_dir, prev_time_ns):
    handlers = get_algorithm_state_handlers(dynamic_state_algorithm)
    if handlers is None:
        return

    label, prefix, load_state, _ = handlers
    state_file = os.path.join(output_dir, "%s_%d.pkl" % (prefix, prev_time_ns))
    if not load_state(state_file):
        print("  > [%s] Will initialize fresh state" % label)


def persist_algorithm_state(dynamic_state_algorithm, output_dir, current_time_ns, prev_time_ns, time_step_ns):
    handlers = get_algorithm_state_handlers(dynamic_state_algorithm)
    if handlers is None:
        return

    label, prefix, _, save_state = handlers
    state_cur = os.path.join(output_dir, "%s_%d.pkl" % (prefix, current_time_ns))
    if not save_state(state_cur):
        return

    old_state = os.path.join(output_dir, "%s_%d.pkl" % (prefix, prev_time_ns - time_step_ns))
    if prev_time_ns > 0 and os.path.exists(old_state):
        os.remove(old_state)
        print("  > [%s] Cleaned up: %s" % (label, old_state))


def generate_single_fstate(
    satellite_network_dir,
    dynamic_state_dir,
    time_ns,
    dynamic_state_algorithm,
    prev_output,
    queue_stats_file=None,
    alpha=0.7,
    beta=0.3,
    time_step_ns=None,
):
    ground_stations = read_ground_stations_extended(
        os.path.join(satellite_network_dir, "ground_stations.txt")
    )
    tles = read_tles(os.path.join(satellite_network_dir, "tles.txt"))
    satellites = tles["satellites"]
    epoch = tles["epoch"]
    list_isls = read_isls(os.path.join(satellite_network_dir, "isls.txt"), len(satellites))
    list_gsl_interfaces_info = read_gsl_interfaces_info(
        os.path.join(satellite_network_dir, "gsl_interfaces_info.txt"),
        len(satellites),
        len(ground_stations),
    )
    with open(os.path.join(satellite_network_dir, "description.txt")) as f_in:
        lines = f_in.readlines()
        max_gsl_length_m = float(lines[0].split("=")[1].strip())
        max_isl_length_m = float(lines[1].split("=")[1].strip())

    return generate_dynamic_state_at(
        dynamic_state_dir,
        epoch,
        time_ns,
        satellites,
        ground_stations,
        list_isls,
        list_gsl_interfaces_info,
        max_gsl_length_m,
        max_isl_length_m,
        dynamic_state_algorithm,
        prev_output,
        True,
        None,
        None,
        queue_stats_file,
        alpha,
        beta,
        time_step_ns,
    )


def main():
    parser = argparse.ArgumentParser(description="Dynamic route calculation for UDP/PDR experiment")
    parser.add_argument("--run_dir", required=True)
    parser.add_argument("--fstate_calculation_algorithm", required=True)
    parser.add_argument("--current_time_ns", type=int, required=True)
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--alpha", type=float, default=0.7)
    parser.add_argument("--beta", type=float, default=0.3)
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("Python Route Calculation - UDP/PDR - Iteration %d" % args.iteration)
    print("Time: %d ns (%.3f s)" % (args.current_time_ns, args.current_time_ns / 1e9))
    print("=" * 60 + "\n")

    run_dir = os.path.abspath(args.run_dir)
    algorithm = args.fstate_calculation_algorithm
    current_time_ns = args.current_time_ns
    time_step_ns = read_dynamic_interval_ns(run_dir)
    prev_time_ns = current_time_ns - time_step_ns

    dynamic_state_dir = os.path.join(run_dir, "dynamic_state")
    prev_output_dir = os.path.join(run_dir, "prev_output_cache")
    os.makedirs(prev_output_dir, exist_ok=True)

    print("Step 1: Processing queue statistics...")
    queue_stats_file = os.path.join(
        run_dir,
        "queue_stats",
        "queue_stats_%d.csv" % prev_time_ns,
    )
    queue_file = process_queue_statistics(os.path.join(run_dir, "logs_ns3"), queue_stats_file)

    print("\nStep 2: Loading previous forwarding state...")
    prev_output = load_prev_output(prev_output_dir, prev_time_ns)

    print("\nStep 2.5: Restoring algorithm state if needed...")
    restore_algorithm_state(algorithm, prev_output_dir, prev_time_ns)

    print("\nStep 3: Generating fstate for t=%d ns..." % current_time_ns)
    output = generate_single_fstate(
        resolve_satellite_network_dir(run_dir),
        dynamic_state_dir,
        current_time_ns,
        algorithm,
        prev_output,
        queue_file,
        args.alpha,
        args.beta,
        time_step_ns,
    )

    print("Step 4: Saving current output for next iteration...")
    save_prev_output(output, prev_output_dir, current_time_ns)
    persist_algorithm_state(algorithm, prev_output_dir, current_time_ns, prev_time_ns, time_step_ns)

    old_pkl = os.path.join(prev_output_dir, "prev_output_%d.pkl" % (prev_time_ns - time_step_ns))
    if prev_time_ns > 0 and os.path.exists(old_pkl):
        os.remove(old_pkl)
        print("  > Cleaned up: %s" % old_pkl)

    fstate_file = os.path.join(dynamic_state_dir, "fstate_%d.txt" % current_time_ns)
    if os.path.exists(fstate_file):
        with open(fstate_file) as f_in:
            num_entries = sum(1 for _ in f_in)
        print("\nRoute calculation completed - %d forwarding entries written." % num_entries)
    print()


if __name__ == "__main__":
    main()
