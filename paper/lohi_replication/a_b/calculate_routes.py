import sys
import os
import argparse
import pandas as pd
import pickle
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
        return None
    
    # 讀取 CSV（無 header）
    df = pd.read_csv(isl_queue_file, header=None, 
                     names=['from', 'to', 'interval_start_ns', 'interval_end_ns', 'num_packets'])
    
    print(f"  > Read {len(df)} records from {isl_queue_file}")
    
    # 以 (from, to) 分組並加總封包數
    # 因為在單一 100ms 時間窗內，每個 (from, to) 可能有多筆記錄
    result = (
        df.groupby(['from', 'to'])['num_packets']
        .max()
        .reset_index(name='packet_max')
    )

    # 只保留 packet_max > 0 的記錄
    result = result[result['packet_max'] > 0]
    
    # 寫入輸出（供下一次路由計算使用）
    result.to_csv(output_file, index=False)
    
    print(f"  > Processed {len(result)} active links")
    print(f"  > Max queue size: {result['packet_max'].max() if len(result) > 0 else 0}")
    print(f"  > Saved to: {output_file}")

    return output_file


def save_prev_output(prev_output, output_dir, time_ns):
    """
    將當前的輸出保存為 pickle 檔案，供下次使用
    
    Args:
        prev_output: 包含 fstate 的字典
        output_dir: 輸出目錄
        time_ns: 當前時間戳（納秒）
    """
    if prev_output is None:
        return
    
    pickle_file = os.path.join(output_dir, f"prev_output_{time_ns}.pkl")
    
    try:
        with open(pickle_file, 'wb') as f:
            pickle.dump(prev_output, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"  > Saved prev_output to: {pickle_file}")
    except Exception as e:
        print(f"  > Warning: Failed to save prev_output: {e}")


def load_prev_output(output_dir, prev_time_ns):
    """
    從 pickle 檔案載入上一次的輸出
    
    Args:
        output_dir: 輸出目錄
        prev_time_ns: 上一個時間戳（納秒）
    
    Returns:
        prev_output 字典，如果不存在則返回 None
    """
    pickle_file = os.path.join(output_dir, f"prev_output_{prev_time_ns}.pkl")
    
    if not os.path.exists(pickle_file):
        print(f"  > No previous output found at: {pickle_file}")
        return None
    
    try:
        with open(pickle_file, 'rb') as f:
            prev_output = pickle.load(f)
        print(f"  > Loaded prev_output from: {pickle_file}")
        
        # 統計 fstate 大小
        if prev_output and 'fstate' in prev_output:
            fstate_size = len(prev_output['fstate'])
            print(f"    >> Previous fstate contains {fstate_size} entries")
        
        return prev_output
    except Exception as e:
        print(f"  > Warning: Failed to load prev_output: {e}")
        return None


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
    parser = argparse.ArgumentParser(description='Dynamic routing calculation')
    parser.add_argument('--run_dir', required=True, help='Run directory')
    parser.add_argument('--fstate_calculation_algorithm', required=True, help='Fstate calculation algorithm')
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
    fstate_calculation_algorithm = args.fstate_calculation_algorithm
    current_time_ns = args.current_time_ns
    time_step_ns = 100 * 1000 * 1000  # 100 ms
    prev_time_ns = current_time_ns - time_step_ns
    
    satellite_network_dir = os.path.join(
        "/home/pflin/research/hypatia-pf/paper/satellite_networks_state/gen_data",
        "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls"
    )
    
    dynamic_state_dir = os.path.join(run_dir, "dynamic_state")
    
    # 創建 prev_output 目錄（如果不存在）
    prev_output_dir = os.path.join(run_dir, "prev_output_cache")
    os.makedirs(prev_output_dir, exist_ok=True)

    # ===== 步驟 1: 處理 queue 統計 =====
    print("Step 1: Processing queue statistics...")
    queue_stats_file = os.path.join(
        run_dir, "queue_stats", f"queue_stats_{prev_time_ns}.csv"
    )
    queue_file = process_queue_statistics(
        os.path.join(run_dir, "logs_ns3"),
        queue_stats_file
    )
    
    # ===== 步驟 2: 載入上一次的 fstate（作為 prev_fstate）=====
    print(f"\nStep 2: Loading previous forwarding state...")
    prev_output = load_prev_output(prev_output_dir, prev_time_ns)
    
    if prev_output is None:
        print("  > This is the first iteration or prev_output not found")
        print("  > Will write complete forwarding state")
    else:
        print("  > Will write only changed forwarding entries")

    # Step 2.5 – restore LHTR internal state (only for algorithm_lhtr)
    if fstate_calculation_algorithm == "algorithm_lhtr":
        from satgen.dynamic_state.algorithm_lhtr import load_lhtr_state, save_lhtr_state
        lhtr_state_file = os.path.join(prev_output_dir, "lhtr_state_%d.pkl" % prev_time_ns)
        if not load_lhtr_state(lhtr_state_file):
            print("  > [LHTR] Will initialize fresh state (first snapshot or fallback)")
    
    # ===== 步驟 3: 生成新的 fstate =====
    print(f"\nStep 3: Generating fstate for t={current_time_ns}ns...")
    
    output = generate_single_fstate(
        satellite_network_dir,
        dynamic_state_dir,
        current_time_ns,
        fstate_calculation_algorithm,
        prev_output,  # 傳入上一次的輸出
        queue_file,
        args.alpha,
        args.beta
    )
    
    # ===== 步驟 4: 保存當前的 output 供下次使用 =====
    print(f"Step 4: Saving current output for next iteration...")
    save_prev_output(output, prev_output_dir, current_time_ns)

    # Step 4.5 – persist LHTR internal state (only for algorithm_lhtr)
    if fstate_calculation_algorithm == "algorithm_lhtr":
        lhtr_state_cur = os.path.join(prev_output_dir, "lhtr_state_%d.pkl" % current_time_ns)
        save_lhtr_state(lhtr_state_cur)
        old_lhtr_state = os.path.join(prev_output_dir, "lhtr_state_%d.pkl" % (prev_time_ns - time_step_ns))
        if prev_time_ns > 0 and os.path.exists(old_lhtr_state):
            os.remove(old_lhtr_state)
            print("  > [LHTR] Cleaned up: %s" % old_lhtr_state)
    
    # ===== 步驟 5: 清理舊的 pickle 檔案（可選，節省空間）=====
    # 只保留最近兩次的 pickle 檔案
    if prev_time_ns > 0:
        old_pickle_file = os.path.join(prev_output_dir, f"prev_output_{prev_time_ns - time_step_ns}.pkl")
        if os.path.exists(old_pickle_file):
            try:
                os.remove(old_pickle_file)
                print(f"  > Cleaned up old pickle file: {old_pickle_file}")
            except Exception as e:
                print(f"  > Warning: Failed to remove old pickle file: {e}")
    
    print(f"\nRoute calculation completed successfully!")
    print(f"New fstate file: {dynamic_state_dir}/fstate_{current_time_ns}.txt")
    
    # 統計寫入的條目數（從檔案大小估計）
    fstate_file = os.path.join(dynamic_state_dir, f"fstate_{current_time_ns}.txt")
    if os.path.exists(fstate_file):
        with open(fstate_file, 'r') as f:
            num_entries = sum(1 for _ in f)
        print(f"  > Written {num_entries} forwarding entries")
        
        if prev_output is not None:
            print(f"  > (Only changed entries were written)")
    
    print()


if __name__ == "__main__":
    main()