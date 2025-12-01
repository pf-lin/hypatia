from .fstate_calculation import *
import csv
import os


def load_queue_statistics(queue_stats_file, num_satellites):
    """
    從 NS-3 輸出的 queue 統計檔案讀取數據
    
    Returns:
        dict: {(sat_from, sat_to): avg_queue_delay_ns}
    """
    queue_delays = {}
    
    if not os.path.exists(queue_stats_file):
        print(f"  > Warning: Queue statistics file not found: {queue_stats_file}")
        return queue_delays
    
    with open(queue_stats_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sat_from = int(row['from'])
            sat_to = int(row['to'])
            
            # 只處理衛星之間的 ISL
            if sat_from < num_satellites and sat_to < num_satellites:
                # 計算平均隊列延遲 (可以用封包數或位元組數)
                packet_sum = int(row['packet_sum'])
                
                # 簡化計算: packet_sum 越大代表越擁塞
                # 實際可以更精確地計算排隊延遲
                queue_delays[(sat_from, sat_to)] = packet_sum
    
    print("  > Loaded queue statistics:")
    print(f"    >> Total links with queue data: {len(queue_delays)}")
    for (link, q_delay) in queue_delays.items():
        print(f"      >> Link {link[0]:3d}-{link[1]:3d}: queue_delay = {q_delay}")
    return queue_delays


def calculate_link_weight(distance_m, queue_delay, alpha=0.7, beta=0.3):
    """
    計算鏈路權重,結合距離和隊列延遲
    
    Args:
        distance_m: 物理距離 (公尺)
        queue_delay: 隊列延遲指標 (封包數或時間)
        alpha: 距離權重係數
        beta: 隊列延遲權重係數
    
    Returns:
        float: 綜合權重
    """
    # 正規化 Queue (0.0 ~ 1.0)
    normalized_queue = min(queue_delay / 100.0, 1.0)
    
    # 定義一個與距離同量級的懲罰係數
    # 例如：如果隊列滿了，相當於這條路徑「憑空多出了」2000 km
    MAX_PENALTY_KM = 2000000.0 
    
    queue_penalty_m = normalized_queue * MAX_PENALTY_KM * (beta / alpha) 
    # 註：這裡的係數設計可以根據您對 alpha/beta 的定義調整
    
    # 最終權重直接是「虛擬距離」
    final_virtual_distance = distance_m + queue_penalty_m
    
    return final_virtual_distance


def algorithm_queue_aware_over_isls(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        satellites,
        ground_stations,
        sat_net_graph_only_satellites_with_isls,
        ground_station_satellites_in_range,
        num_isls_per_sat,
        sat_neighbor_to_if,
        list_gsl_interfaces_info,
        prev_output,
        enable_verbose_logs,
        queue_stats_file=None,
        alpha=0.7,
        beta=0.3
):
    """
    QUEUE-AWARE FREE-ONE ONLY OVER INTER-SATELLITE LINKS ALGORITHM
    
    基於隊列狀態的動態路由算法
    """
    
    if enable_verbose_logs:
        print("\nALGORITHM: QUEUE-AWARE FREE ONE ONLY OVER ISLS")
        print(f"  > Alpha (distance weight): {alpha}")
        print(f"  > Beta (queue weight): {beta}")

    # 載入隊列統計數據
    queue_delays = {}
    if queue_stats_file and time_since_epoch_ns > 0:
        queue_delays = load_queue_statistics(queue_stats_file, len(satellites))
        if enable_verbose_logs:
            print(f"  > Loaded queue statistics for {len(queue_delays)} links")
    
    # 更新圖的權重
    updated_graph = sat_net_graph_only_satellites_with_isls.copy()
    
    for (a, b) in updated_graph.edges():
        original_distance = updated_graph.edges[(a, b)]["weight"]
        queue_delay = queue_delays.get((a, b), 0)
        
        # 計算新權重
        new_weight = calculate_link_weight(
            original_distance, 
            queue_delay, 
            alpha, 
            beta
        )
        
        updated_graph.edges[(a, b)]["weight"] = new_weight
        
        if enable_verbose_logs and queue_delay > 0:
            print(f"  > Link {a:3d}-{b:3d}: distance = {original_distance:7.0f} m, "
                  f"queue ={queue_delay:3d}, new_weight = {new_weight:7.0f}")
    
    # GSL interface bandwidth 狀態
    output_filename = output_dynamic_state_dir + "/gsl_if_bandwidth_" + str(time_since_epoch_ns) + ".txt"
    if enable_verbose_logs:
        print("  > Writing interface bandwidth state to: " + output_filename)
    with open(output_filename, "w+") as f_out:
        if time_since_epoch_ns == 0:
            for node_id in range(len(satellites)):
                f_out.write("%d,%d,%f\n"
                            % (node_id, num_isls_per_sat[node_id],
                               list_gsl_interfaces_info[node_id]["aggregate_max_bandwidth"]))
            for node_id in range(len(satellites), len(satellites) + len(ground_stations)):
                f_out.write("%d,%d,%f\n"
                            % (node_id, 0, list_gsl_interfaces_info[node_id]["aggregate_max_bandwidth"]))

    # Forwarding state
    prev_fstate = None
    if prev_output is not None:
        prev_fstate = prev_output["fstate"]

    gid_to_sat_gsl_if_idx = [0] * len(ground_stations)

    # 使用更新權重的圖計算 forwarding state
    fstate = calculate_fstate_shortest_path_without_gs_relaying(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        len(satellites),
        len(ground_stations),
        updated_graph,  # 使用更新權重的圖
        num_isls_per_sat,
        gid_to_sat_gsl_if_idx,
        ground_station_satellites_in_range,
        sat_neighbor_to_if,
        prev_fstate,
        enable_verbose_logs
    )

    if enable_verbose_logs:
        print("")

    return {
        "fstate": fstate
    }