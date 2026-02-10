import sys
import os
import subprocess
import pickle
sys.path.append("/home/pflin/research/hypatia-pf/satgenpy")
from satgen.dynamic_state.generate_dynamic_state import generate_dynamic_state_at
from satgen.isls import read_isls
from satgen.ground_stations import read_ground_stations_extended
from satgen.tles import read_tles
from satgen.interfaces import read_gsl_interfaces_info


def run_ns3_simulation(run_dir):
    """
    執行 NS-3 模擬
    """
    cmd = [
        "cd", "../../../ns3-sat-sim/simulator;",
        "./waf",
        f"--run=\"main_satnet --run_dir='../../paper/lohi_replication/a_b/{run_dir}'\"",
        "2>&1", "|", "tee",
        f"'../../paper/lohi_replication/a_b/{run_dir}/logs_ns3/console.txt'"
    ]
    
    cmd_str = " ".join(cmd)
    print(f"\nRunning: {cmd_str}\n")
    
    result = subprocess.run(cmd_str, shell=True, executable='/bin/bash')
    
    if result.returncode != 0:
        raise RuntimeError(f"NS-3 simulation failed with return code {result.returncode}")


def generate_single_fstate(
        satellite_network_dir,
        dynamic_state_dir,
        time_ns,
        dynamic_state_algorithm,
        prev_output,
        queue_stats_file=None,
        alpha=0.7,
        beta=0.3
):
    """
    生成單一時間點的 forwarding state
    """
    # 讀取衛星網路數據
    ground_stations = read_ground_stations_extended(
        os.path.join(satellite_network_dir, "ground_stations.txt")
    )
    tles = read_tles(os.path.join(satellite_network_dir, "tles.txt"))
    satellites = tles["satellites"]
    epoch = tles["epoch"]
    list_isls = read_isls(
        os.path.join(satellite_network_dir, "isls.txt"),
        len(satellites)
    )
    list_gsl_interfaces_info = read_gsl_interfaces_info(
        os.path.join(satellite_network_dir, "gsl_interfaces_info.txt"),
        len(satellites),
        len(ground_stations)
    )
    
    # 讀取描述檔案以獲取最大距離
    with open(os.path.join(satellite_network_dir, "description.txt"), 'r') as f:
        lines = f.readlines()
        max_gsl_length_m = float(lines[0].split('=')[1].strip())
        max_isl_length_m = float(lines[1].split('=')[1].strip())
    
    output = generate_dynamic_state_at(
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
        True,  # enable_verbose_logs
        None,  # num_orbits
        None,  # num_sats_per_orbit
        queue_stats_file,
        alpha,
        beta
    )
    
    return output


def main():
    # 配置參數
    # fstate_calculation_algorithm = "algorithm_queue_aware_over_isls"
    fstate_calculation_algorithm = "algorithm_tlr"
    run_name = f"oneweb_1200_isls_757_to_736_with_TcpNewReno_at_10_Mbps_dynamic"
    run_dir = f"runs/{run_name}/{fstate_calculation_algorithm}"
    
    satellite_network_dir = os.path.join(
        "/home/pflin/research/hypatia-pf/paper/satellite_networks_state/gen_data",
        "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls"
    )
    
    dynamic_state_dir = os.path.join(run_dir, "dynamic_state")
    
    # 創建目錄
    os.makedirs(dynamic_state_dir, exist_ok=True)
    os.makedirs(os.path.join(run_dir, "logs_ns3"), exist_ok=True)
    os.makedirs(os.path.join(run_dir, "queue_stats"), exist_ok=True)

    # 新增：創建 prev_output_cache 目錄
    prev_output_dir = os.path.join(run_dir, "prev_output_cache")
    os.makedirs(prev_output_dir, exist_ok=True)
    
    current_time_ns = 0
    prev_output = None
    queue_stats_file = None
    
    print(f"\nGenerating forwarding states (fstate_0.txt) ...")
    prev_output = generate_single_fstate(
        satellite_network_dir,
        dynamic_state_dir,
        current_time_ns,
        fstate_calculation_algorithm,
        prev_output,
        queue_stats_file
    )

    # 新增：保存初始的 prev_output
    if prev_output:
        pickle_file = os.path.join(prev_output_dir, f"prev_output_0.pkl")
        with open(pickle_file, 'wb') as f:
            pickle.dump(prev_output, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"Saved initial prev_output to: {pickle_file}\n")
    
    print("Starting dynamic routing and NS-3 simulation loop...") 
    run_ns3_simulation(run_dir)


if __name__ == "__main__":
    main()