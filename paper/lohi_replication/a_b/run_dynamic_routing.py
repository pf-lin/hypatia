import sys
import os
import subprocess
import pandas as pd
sys.path.append("../../../satgenpy")
import satgen
from satgen.dynamic_state.generate_dynamic_state import generate_dynamic_state_at
from satgen.isls import read_isls
from satgen.ground_stations import read_ground_stations_extended
from satgen.tles import read_tles
from satgen.interfaces import read_gsl_interfaces_info


def process_queue_statistics(logs_dir, output_file):
    """
    處理 NS-3 輸出的 queue tracking 檔案
    
    將 isl_queue_pkt.csv 轉換為適合路由算法使用的格式
    原格式: from,to,interval_start_ns,interval_end_ns,num_packets
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

    total_packets = result['packet_sum'].sum()
    active_links = len(result)
    
    print(f"  > Processed queue statistics:")
    print(f"    >> Total unique (from, to) pairs: {active_links}")
    print(f"    >> Total packets in this window: {total_packets}")
    print(f"    >> Average packets per active link: {total_packets / active_links if active_links > 0 else 0:.2f}")
    print(f"  > Saved to: {output_file}")


def run_ns3_simulation(run_dir, current_time_ns):
    """
    執行 NS-3 模擬
    """
    cmd = [
        "cd", "../../../ns3-sat-sim/simulator;",
        "./waf",
        f"--run=\"main_satnet --run_dir='../../paper/lohi_replication/a_b/{run_dir}'\"",
        "2>&1", "|", "tee",
        f"'../../paper/lohi_replication/a_b/{run_dir}/logs_ns3/console_{current_time_ns}.txt'"
    ]
    
    cmd_str = " ".join(cmd)
    print(f"Running: {cmd_str}")
    
    result = subprocess.run(cmd_str, shell=True, executable='/bin/bash')
    
    if result.returncode != 0:
        raise RuntimeError(f"NS-3 simulation failed with return code {result.returncode}")


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


def update_config_simulation_time(config_file, start_ns, end_ns):
    """
    更新配置檔案中的模擬時間範圍
    """
    with open(config_file, 'r') as f:
        lines = f.readlines()
    
    with open(config_file, 'w') as f:
        for line in lines:
            if line.startswith('simulation_end_time_ns='):
                f.write(f'simulation_end_time_ns={end_ns}\n')
            else:
                f.write(line)
    
    print(f"Updated config: simulation time [{start_ns}, {end_ns})")


def main():
    # 配置參數
    run_name = "oneweb_1200_isls_757_to_736_with_TcpNewReno_at_10_Mbps_dynamic"
    run_dir = f"runs/{run_name}"
    
    satellite_network_dir = os.path.join(
        "../../../paper/satellite_networks_state/gen_data",
        "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls"
    )
    
    dynamic_state_dir = os.path.join(run_dir, "dynamic_state")
    
    # 時間參數
    time_step_ns = 100 * 1000 * 1000  # 100 ms
    simulation_duration_ns = 200 * 1000 * 1000 * 1000  # 200 s
    
    # 路由權重參數
    alpha = 0.7  # 距離權重
    beta = 0.3   # 隊列權重
    
    # 創建目錄
    os.makedirs(dynamic_state_dir, exist_ok=True)
    os.makedirs(os.path.join(run_dir, "logs_ns3"), exist_ok=True)
    os.makedirs(os.path.join(run_dir, "queue_stats"), exist_ok=True)
    
    current_time_ns = 0
    iteration = 0

    # 生成 dynamic state
    prev_output = None
    
    while current_time_ns < simulation_duration_ns:
        print(f"\n{'='*60}")
        print(f"Iteration {iteration}: t = {current_time_ns / 1e9:.3f} s")
        print(f"{'='*60}\n")
        
        # 步驟 1: 生成當前時間點的 fstate
        queue_stats_file = None
        if iteration > 0:
            # 使用上一次模擬的 queue 統計數據
            queue_stats_file = os.path.join(
                run_dir, "queue_stats", f"queue_stats_{current_time_ns - time_step_ns}.csv"
            )
        
        print(f"Step 1: Generating fstate for t={current_time_ns}ns...")
        prev_output = generate_single_fstate(
            satellite_network_dir,
            dynamic_state_dir,
            current_time_ns,
            prev_output,
            queue_stats_file,
            alpha,
            beta
        )
        
        # 步驟 2: 更新 config_ns3.properties 中的時間範圍
        config_file = os.path.join(run_dir, "config_ns3.properties")
        next_time_ns = current_time_ns + time_step_ns
        
        update_config_simulation_time(config_file, current_time_ns, next_time_ns)
        
        # 步驟 3: 執行 NS-3 模擬
        print(f"\nStep 2: Running NS-3 simulation [{current_time_ns}, {next_time_ns})...")
        run_ns3_simulation(run_dir, current_time_ns)
        
        # 步驟 4: 處理 queue 統計數據
        print(f"\nStep 3: Processing queue statistics...")
        process_queue_statistics(
            os.path.join(run_dir, "logs_ns3"),
            os.path.join(run_dir, "queue_stats", f"queue_stats_{current_time_ns}.csv")
        )
        
        # 前進到下一個時間步
        current_time_ns = next_time_ns
        iteration += 1
        
        print(f"\nIteration {iteration - 1} completed successfully\n")
    
    print(f"\n{'='*60}")
    print("Dynamic routing simulation completed!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()