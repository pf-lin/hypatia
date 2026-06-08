from .fstate_calculation import *
import os
from .queue_delay_cost import (
    DEFAULT_ISL_LINK_CAPACITY_BPS,
    QUEUE_COST_MODE,
    calculate_link_queue_cost,
    describe_queue_cost,
    load_queue_statistics_csv,
    propagation_delay_seconds,
)


def load_queue_statistics(queue_stats_file, num_satellites, enable_verbose_logs):
    """
    從 NS-3 輸出的 queue 統計檔案讀取數據
    
    Returns:
        dict: {(sat_from, sat_to): queue_length_packets}
    """
    if not queue_stats_file or not os.path.exists(queue_stats_file):
        print(f"  > Warning: Queue statistics file not found: {queue_stats_file}")
        return {}

    queue_stats = load_queue_statistics_csv(queue_stats_file, num_satellites)
    queue_delays = queue_stats.queue_packets
    
    # 統計雙向連接
    unique_links = set()
    directional_flows_with_traffic = 0
    for (a, b), packets in queue_delays.items():
        link = tuple(sorted([a, b]))  # 將 (0,1) 和 (1,0) 統一為 (0,1)
        unique_links.add(link)
        if packets > 0:
            directional_flows_with_traffic += 1
    
    if enable_verbose_logs:
        print("  > Queue statistics loaded:")
        print(f"    >> Total directional flows: {len(queue_delays)}")
        print(f"    >> Directional flows with traffic: {directional_flows_with_traffic}")
        print(f"    >> Unique physical ISL links: {len(unique_links)}")
    
    return queue_delays


def calculate_link_weight(
        distance_m,
        queue_delay,
        alpha=0.7,
        beta=0.3,
        queue_bytes=None,
        link_capacity_bps=None):
    """
    計算鏈路權重；delay 模式回傳 seconds。
    
    Args:
        distance_m: 物理距離 (公尺)
        queue_delay: 隊列延遲指標 (封包數或時間)
        alpha: 距離權重係數
        beta: 隊列延遲權重係數
    
    Returns:
        float: delay seconds，或 legacy_penalty 模式的虛擬距離
    """
    return calculate_link_queue_cost(
        distance_m,
        queue_packets=queue_delay,
        queue_bytes=queue_bytes,
        link_capacity_bps=link_capacity_bps,
        alpha_dist=alpha,
        alpha_queue=beta,
    )


def _convert_gsl_candidates_to_cost(ground_station_satellites_in_range):
    """Convert GSL distance to propagation seconds without changing baseline code."""
    if QUEUE_COST_MODE != "delay":
        return ground_station_satellites_in_range

    def convert_candidates(candidates):
        return [
            (propagation_delay_seconds(candidate[0]), candidate[1])
            for candidate in candidates
        ]

    if isinstance(ground_station_satellites_in_range, dict):
        return {
            gid: convert_candidates(candidates)
            for gid, candidates in ground_station_satellites_in_range.items()
        }
    return [
        convert_candidates(candidates)
        for candidates in ground_station_satellites_in_range
    ]


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
        beta=0.3,
        isl_link_capacity_bps=None,
):
    """
    QUEUE-AWARE FREE-ONE ONLY OVER INTER-SATELLITE LINKS ALGORITHM
    
    基於隊列狀態的動態路由算法
    """
    
    if enable_verbose_logs:
        print("\nALGORITHM: QUEUE-AWARE FREE ONE ONLY OVER ISLS")
        if QUEUE_COST_MODE == "legacy_penalty":
            print(f"  > Legacy alpha (distance weight): {alpha}")
            print(f"  > Legacy beta (queue weight): {beta}")

    # 載入隊列統計數據
    queue_packets = {}
    queue_bytes = {}
    queue_delay_source = "queue_packets_fallback"
    if queue_stats_file and time_since_epoch_ns > 0:
        queue_stats = load_queue_statistics_csv(queue_stats_file, len(satellites))
        queue_packets = queue_stats.queue_packets
        queue_bytes = queue_stats.queue_bytes
        queue_delay_source = queue_stats.delay_source

    link_capacity_bps = (
        DEFAULT_ISL_LINK_CAPACITY_BPS
        if isl_link_capacity_bps is None
        else float(isl_link_capacity_bps)
    )
    if enable_verbose_logs:
        print("  > " + describe_queue_cost(queue_delay_source, link_capacity_bps))
    
    # 更新圖的權重
    updated_graph = sat_net_graph_only_satellites_with_isls.copy()
    
    # 統計有多少條鏈路被更新
    links_updated = 0
    links_with_queue_data = 0
    
    for (a, b) in updated_graph.edges():
        original_distance = updated_graph.edges[(a, b)]["weight"]
        
        # 獲取兩個方向的隊列延遲
        # 注意：NetworkX 無向圖的邊是標準化的（a < b），但 queue 數據可能是任一方向
        queue_delay_a_to_b = queue_packets.get((a, b), 0)
        queue_delay_b_to_a = queue_packets.get((b, a), 0)
        
        # 使用兩個方向的最大值（保守策略，避開擁塞）
        queue_delay = max(queue_delay_a_to_b, queue_delay_b_to_a)
        queue_bytes_for_link = None
        if queue_bytes:
            queue_bytes_for_link = max(
                queue_bytes.get((a, b), 0),
                queue_bytes.get((b, a), 0),
            )
        
        # 或者使用平均值（較溫和的策略）
        # queue_delay = (queue_delay_a_to_b + queue_delay_b_to_a) / 2.0
        
        # 計算新權重
        new_weight = calculate_link_weight(
            original_distance, 
            queue_delay, 
            alpha, 
            beta,
            queue_bytes=queue_bytes_for_link,
            link_capacity_bps=link_capacity_bps,
        )
        
        updated_graph.edges[(a, b)]["weight"] = new_weight
        links_updated += 1
        
        if queue_delay_a_to_b > 0 or queue_delay_b_to_a > 0:
            links_with_queue_data += 1
            
            if enable_verbose_logs:
                direction_info = ""
                if queue_delay_a_to_b > 0 and queue_delay_b_to_a > 0:
                    direction_info = (f"queue({a:3d}->{b:3d})={queue_delay_a_to_b:3d}, "
                                    f"queue({b:3d}->{a:3d})={queue_delay_b_to_a:3d}, "
                                    f"max={queue_delay:3d}")
                elif queue_delay_a_to_b > 0:
                    direction_info = f"queue({a:3d}->{b:3d})={queue_delay_a_to_b:3d}"
                else:
                    direction_info = f"queue({b:3d}->{a:3d})={queue_delay_b_to_a:3d}"
                
                print(f"      >>> Link {a:3d}-{b:3d}: distance={original_distance:7.0f}m, "
                      f"{direction_info}, new_weight={new_weight:.9f}")
    
    if enable_verbose_logs:
        print(f"    >> Total links updated: {links_updated}")
        print(f"    >> Links with queue data: {links_with_queue_data}")
        print(f"    >> Links without queue data: {links_updated - links_with_queue_data}")
    
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
    gsl_candidates_with_cost = _convert_gsl_candidates_to_cost(
        ground_station_satellites_in_range
    )
    fstate = calculate_fstate_shortest_path_without_gs_relaying(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        len(satellites),
        len(ground_stations),
        updated_graph,  # 使用更新權重的圖
        num_isls_per_sat,
        gid_to_sat_gsl_if_idx,
        gsl_candidates_with_cost,
        sat_neighbor_to_if,
        prev_fstate,
        enable_verbose_logs
    )

    if enable_verbose_logs:
        print("")

    return {
        "fstate": fstate
    }
