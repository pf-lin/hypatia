import sys
import os
import argparse
import pandas as pd
sys.path.append("/home/pflin/research/hypatia-pf/satgenpy")
from satgen.dynamic_state.generate_dynamic_state import generate_dynamic_state_at
from satgen.isls import read_isls
from satgen.ground_stations import read_ground_stations_extended
from satgen.tles import read_tles
from satgen.interfaces import read_gsl_interfaces_info


def process_queue_statistics(logs_dir, output_file):
    """
    處理 NS-3 輸出的 queue tracking 檔案
    """
    isl_queue_file = os.path.join(logs_dir, "isl_queue_pkt.csv")
    
    if not os.path.exists(isl_queue_file):
        print(f"Warning: {isl_queue_file} not found")
        return
    
    # 讀取 CSV（無 header）
    df = pd.read_csv(isl_queue_file, header=None, 
                     names=['from', 'to', 'interval_start_ns', 'interval_end_ns', 'num_packets'])
    
    print(f"  > Read {len(df)} records from {isl_queue_file}")
    
    # 以 (from, to) 分組並加總封包數
    # 因為在單一 100ms 時間窗內，每個 (from, to) 可能有多筆記錄
    result = (
        df.groupby(['from', 'to'])['num_packets']
        .sum()
        .reset_index(name='packet_sum')
    )

    # 只保留 packet_sum > 0 的記錄
    result = result[result['packet_sum'] > 0]
    
    # 寫入輸出（供下一次路由計算使用）
    result.to_csv(output_file, index=False)
    
    print(f"  > Processed {len(result)} active links")
    print(f"  > Saved to: {output_file}")


def generate_single_fstate(
        satellite_network_dir,
        dynamic_state_dir,
        time_ns,
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
        "algorithm_queue_aware_over_isls",
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
    parser = argparse.ArgumentParser(description='Dynamic routing calculation')
    parser.add_argument('--run_dir', required=True, help='Run directory')
    parser.add_argument('--current_time_ns', type=int, required=True, help='Current simulation time in ns')
    parser.add_argument('--iteration', type=int, required=True, help='Iteration number')
    parser.add_argument('--alpha', type=float, default=0.7, help='Distance weight')
    parser.add_argument('--beta', type=float, default=0.3, help='Queue weight')
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"Python Route Calculation - Iteration {args.iteration}")
    print(f"Time: {args.current_time_ns} ns ({args.current_time_ns / 1e9:.3f} s)")
    print(f"{'='*60}\n")

    run_dir = args.run_dir
    current_time_ns = args.current_time_ns
    time_step_ns = 100 * 1000 * 1000  # 100 ms
    
    satellite_network_dir = os.path.join(
        "/home/pflin/research/hypatia-pf/paper/satellite_networks_state/gen_data",
        "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls"
    )
    
    dynamic_state_dir = os.path.join(run_dir, "dynamic_state")

    # 步驟 1: 處理 queue 統計
    print("Step 1: Processing queue statistics...")
    queue_stats_file = os.path.join(
        run_dir, "queue_stats", f"queue_stats_{current_time_ns - time_step_ns}.csv"
    )
    process_queue_statistics(
        os.path.join(run_dir, "logs_ns3"),
        queue_stats_file
    )
    
    # 步驟 2: 生成新的 fstate
    print(f"\nStep 2: Generating fstate for t={current_time_ns}ns...")
    
    # 讀取前一個輸出（如果有的話）
    prev_output = None
    
    output = generate_single_fstate(
        satellite_network_dir,
        dynamic_state_dir,
        current_time_ns,
        prev_output,
        queue_stats_file,
        args.alpha,
        args.beta
    )
    
    print(f"Route calculation completed successfully")
    print(f"New fstate file: {dynamic_state_dir}/fstate_{current_time_ns}.txt\n")


if __name__ == "__main__":
    main()