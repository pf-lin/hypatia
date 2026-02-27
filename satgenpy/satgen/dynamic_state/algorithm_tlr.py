"""
TLR (Traffic-Light-Based Intelligent Routing) Algorithm - Fast Implementation
Optimized using Reverse Dijkstra Strategy for 100ms update intervals.
"""

import csv
import os
import networkx as nx
from collections import defaultdict

# ========== 1. Constants & Configuration ==========

class TLRConfig:
    """TLR Algorithm Configuration"""
    def __init__(self):
        # Buffer configuration
        self.buffer_size = 100  # packets
        
        # QOR (Queue Occupancy Rate) thresholds for individual links
        self.qor_t1 = 0.6  # Green -> Yellow
        self.qor_t2 = 0.8  # Yellow -> Red
        
        # TQOR (Total Queue Occupancy Rate) thresholds for satellite nodes
        self.tqor_t_gy = 1/3  # Green -> Yellow
        self.tqor_t_yr = 2/3  # Yellow -> Red


# ========== 2. Traffic Light Color Definitions ==========

class TrafficColor:
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


# ========== 3. Load Queue Statistics & Calculate States ==========

def load_queue_and_calculate_states(queue_stats_file, num_satellites, config, enable_verbose_logs):
    """
    Load queue statistics and calculate traffic light states.
    Same logic as before, calculating QOR and TQOR.
    """
    # Initialize data structures with default values
    link_queue_len = {}
    link_qor = {}
    link_color = {}
    node_outgoing_queue_sum = defaultdict(int)
    node_tqor = {}
    node_color = {}
    
    # Initialize states for all potential links (will be populated on demand or default to Green)
    
    # === Step 1: Load queue statistics ===
    if queue_stats_file and os.path.exists(queue_stats_file):
        with open(queue_stats_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sat_from = int(row['from'])
                sat_to = int(row['to'])
                
                # Only care about Satellite-to-Satellite or Satellite-to-GS queues
                # (Assuming GS-to-Sat queues don't affect routing DECISIONS on satellites)
                queue_len = int(row['packet_sum'])
                link_queue_len[(sat_from, sat_to)] = queue_len
    
    # === Step 2: Calculate QOR for each link (Current Hop State) ===
    # Only for links that have traffic data. Others are 0/Green.
    for (sat_from, sat_to), q_len in link_queue_len.items():
        qor = q_len / config.buffer_size
        link_qor[(sat_from, sat_to)] = qor
        
        if qor < config.qor_t1:
            link_color[(sat_from, sat_to)] = TrafficColor.GREEN
        elif qor < config.qor_t2:
            link_color[(sat_from, sat_to)] = TrafficColor.YELLOW
        else:
            link_color[(sat_from, sat_to)] = TrafficColor.RED
        
        if sat_from < num_satellites:
            node_outgoing_queue_sum[sat_from] += q_len
    
    # === Step 3: Calculate TQOR for each node (Next Hop State) ===
    # Note: We can't know exact total buffer without topology, 
    # but we approximate based on active links or assume 4 ISLs.
    # Here we use a safe assumption: if we have data, we calc; else Green.
    
    for sat_id in range(num_satellites):
        # Approximate: Assume average 4 neighbors for TQOR calc if not fully known
        # Or simply use the sum we found.
        q_sum = node_outgoing_queue_sum.get(sat_id, 0)
        
        # Simplified TQOR: q_sum / (4 * buffer_size)
        # In a real implementation, we should pass exact degree. 
        # Here we assume max 4 ISLs per sat.
        total_buffer = config.buffer_size * 4 
        
        tqor = q_sum / total_buffer
        node_tqor[sat_id] = tqor
        
        if tqor < config.tqor_t_gy:
            node_color[sat_id] = TrafficColor.GREEN
        elif tqor < config.tqor_t_yr:
            node_color[sat_id] = TrafficColor.YELLOW
        else:
            node_color[sat_id] = TrafficColor.RED
            
    # === Step 4: Final Link Color Helper ===
    # We return a helper function or dict to lookup final color
    final_link_color_map = {}
    
    # Pre-calculate for known links
    for (u, v) in link_queue_len.keys():
        c_hop = link_color.get((u, v), TrafficColor.GREEN)
        n_hop = node_color.get(v, TrafficColor.GREEN)
        final_link_color_map[(u, v)] = combine_traffic_colors(c_hop, n_hop)
        
    return {
        'link_qor': link_qor,
        'final_link_color_map': final_link_color_map,
        'node_color': node_color
    }

def combine_traffic_colors(c_color, n_color):
    """Table I logic"""
    if c_color == TrafficColor.RED or n_color == TrafficColor.RED:
        return TrafficColor.RED
    elif c_color == TrafficColor.YELLOW or n_color == TrafficColor.YELLOW:
        return TrafficColor.YELLOW
    return TrafficColor.GREEN

def get_final_color(u, v, traffic_states):
    """Safe lookup for final color"""
    # If explicitly calculated, return it
    if (u, v) in traffic_states['final_link_color_map']:
        return traffic_states['final_link_color_map'][(u, v)]
    
    # Otherwise, default logic (Green + Next Hop Status)
    # This handles links that currently have 0 queue
    n_color = traffic_states['node_color'].get(v, TrafficColor.GREEN)
    return combine_traffic_colors(TrafficColor.GREEN, n_color)


# ========== 4. Fast Next Hop Calculation (Reverse Dijkstra) ==========

def calculate_next_hops_optimized_complete(graph, num_satellites, ground_stations, enable_verbose_logs):
    """
    Correct implementation including GS sources.
    Calculate next hops with loop prevention
    """
    if enable_verbose_logs:
        print("  > Running Reverse Dijkstra for all destinations...")
        
    next_hops = {}
    destinations = [num_satellites + gs['gid'] for gs in ground_stations]
    
    for dst_node in destinations:
        try:
            # Dijkstra from DST to everywhere
            lengths, paths = nx.single_source_dijkstra(graph, source=dst_node, weight='weight')
        except nx.NetworkXNoPath:
            continue

        # For EVERY node (Sat or GS) that might send to this DST
        # We iterate graph nodes to be generic
        for src_node in graph.nodes():
            if src_node == dst_node: continue
            if src_node not in lengths: continue
            
            # Optimization: Only calculate for Satellites and GSs
            # (Skip if you have other node types)
            
            neighbors = list(graph.neighbors(src_node))
            candidates = []

            # ========== 關鍵修改：找出最短路徑上的前一跳 ==========
            # paths[src_node] = [dst_node, ..., prev_node, src_node]
            # 我們要的是 src_node 往 dst_node 的下一跳，也就是倒數第二個節點
            shortest_path = paths[src_node]
            br_next_hop = shortest_path[-2] if len(shortest_path) > 1 else None
            
            for nbr in neighbors:
                if nbr in lengths:
                    w = graph[src_node][nbr].get('weight', 1.0)
                    dist = lengths[nbr]
                    total_cost = w + dist
                    candidates.append((total_cost, nbr))
            
            if not candidates:
                next_hops[(src_node, dst_node)] = {'br': None, 'sbr': None}
                continue
            
            # Sort: Lowest cost first
            candidates.sort(key=lambda x: x[0])
            
            # BR: Always use the shortest path next hop
            br = br_next_hop if br_next_hop else candidates[0][1]
            
            # ========== SBR 選擇邏輯（防環路）==========
            sbr = None
            sbr_cost = float('inf')
            
            for cost, nbr in candidates:
                # 1. 排除 BR
                if nbr == br:
                    continue
                
                # 2. ========== 修正：檢查 nbr 的 BR 是否指向 src_node ==========
                # 如果 nbr 在最短路徑上的下一跳是 src_node，則會形成環路
                if nbr in paths:
                    nbr_path = paths[nbr]
                    # nbr_path = [dst_node, ..., nbr_next_hop, nbr]
                    # nbr 的下一跳是 nbr_path[-2]
                    if len(nbr_path) > 1:
                        nbr_next_hop = nbr_path[-2]
                        if nbr_next_hop == src_node:
                            # nbr 的 BR 指向 src_node → 會形成環路
                            # if enable_verbose_logs:
                            #     print(f"    >> Skipping SBR {src_node}->{nbr} (would create loop: {nbr}->{src_node})")
                            continue
                
                # 3. 接受這個 SBR（如果成本合理）
                if cost < sbr_cost and cost < lengths[src_node] * 1.5:
                    sbr = nbr
                    sbr_cost = cost
            
            next_hops[(src_node, dst_node)] = {'br': br, 'sbr': sbr}
                
    return next_hops


# ========== 5. Make Routing Decision (Table II) ==========

def make_routing_decision(src, dst, hops_info, traffic_states):
    """
    Apply Table II logic to decide between BR and SBR next hop.
    """
    br_hop = hops_info['br']
    sbr_hop = hops_info['sbr']
    
    # 1. If no BR, drop (return -1)
    if br_hop is None:
        return -1
        
    # 2. Get Colors
    br_color = get_final_color(src, br_hop, traffic_states)
    
    # If no SBR, we must use BR (unless BR is Red, but we stick to BR for simplicity or drop)
    if sbr_hop is None:
        return br_hop
        
    sbr_color = get_final_color(src, sbr_hop, traffic_states)
    
    # 3. Table II Logic
    if br_color == TrafficColor.GREEN:
        return br_hop
        
    elif br_color == TrafficColor.YELLOW:
        if sbr_color in [TrafficColor.GREEN, TrafficColor.YELLOW]:
            return sbr_hop # Offload
        else:
            return br_hop # SBR is Red, stick to BR
            
    else: # br_color == RED
        if sbr_color in [TrafficColor.GREEN, TrafficColor.YELLOW]:
            return sbr_hop
        else:
            # Both RED: Choose the one with lower QOR (Queue Occupancy)
            qor_br = traffic_states['link_qor'].get((src, br_hop), 0.0)
            qor_sbr = traffic_states['link_qor'].get((src, sbr_hop), 0.0)
            
            if qor_sbr < qor_br:
                return sbr_hop
            else:
                return br_hop


# ========== 6. Main TLR Algorithm Entry Point ==========

def algorithm_tlr(
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
        tlr_config=None
):
    
    if enable_verbose_logs:
        print("\n" + "="*60)
        print(f"TLR Algorithm (Optimized) at t={time_since_epoch_ns} ns")
        print("="*60)

    if tlr_config is None:
        tlr_config = TLRConfig()

    num_satellites = len(satellites)
    num_ground_stations = len(ground_stations)

    # ========== FIX 1: Handle None prev_output ==========
    if prev_output is None:
        prev_output = {"fstate": {}}

    # 1. Load Traffic States (Red/Yellow/Green)
    traffic_states = load_queue_and_calculate_states(
        queue_stats_file, num_satellites, tlr_config, enable_verbose_logs
    )

    # 2. Build Full Graph (Satellites + GSLs)
    # Note: We use the graph with weights = propagation delay (distance)
    full_graph = sat_net_graph_only_satellites_with_isls.copy()
    
    for gid, gs_sats_in_range in enumerate(ground_station_satellites_in_range):
        gs_node = num_satellites + gid
        full_graph.add_node(gs_node)
        for (dist_m, sat_id) in gs_sats_in_range:
            full_graph.add_edge(sat_id, gs_node, weight=dist_m)

    # 3. Calculate BR and SBR Next Hops (FAST)
    # Using One-to-All Dijkstra from destinations
    next_hops_map = calculate_next_hops_optimized_complete(
        full_graph, num_satellites, ground_stations, enable_verbose_logs
    )

    # 4. Generate Forwarding State
    fstate = {}
    gid_to_sat_gsl_if_idx = [0] * num_ground_stations
    
    output_filename = output_dynamic_state_dir + "/fstate_" + str(time_since_epoch_ns) + ".txt"
    
    # Counters for logging
    stats = {'BR': 0, 'SBR': 0, 'Drop': 0}

    with open(output_filename, "w+") as f_out:
        
        # Iterate over all pairs that need routing
        # (Sat -> GS)
        for src in range(num_satellites):
            for dst_gid in range(num_ground_stations):
                dst = num_satellites + dst_gid
                
                # Check if destination GS has any satellites in range
                if len(ground_station_satellites_in_range[dst_gid]) == 0:
                    # No satellite in range - mark as dropped
                    new_entry = (-1, -1, -1)
                    prev_entry = prev_output.get("fstate", {}).get((src, dst), None)
                    
                    # Always add to fstate
                    fstate[(src, dst)] = new_entry

                    # Only write to file if changed
                    if new_entry != prev_entry:
                        f_out.write(f"{src},{dst},-1,-1,-1\n")
                        stats['Drop'] += 1
                    continue
                
                hops = next_hops_map.get((src, dst), {'br': None, 'sbr': None})
                
                # Decision
                final_next_hop = make_routing_decision(src, dst, hops, traffic_states)
                
                # Determine interface IDs
                if final_next_hop != -1:
                    # Is it Sat or GS?
                    if final_next_hop < num_satellites:
                        # Sat-to-Sat
                        my_if = sat_neighbor_to_if.get((src, final_next_hop), -1)
                        nxt_if = sat_neighbor_to_if.get((final_next_hop, src), -1)
                        
                        # Count stats
                        if final_next_hop == hops['sbr']: stats['SBR'] += 1
                        else: stats['BR'] += 1
                        
                    else:
                        # Sat-to-GS
                        # Assuming GSL interface is appended after ISLs
                        my_if = num_isls_per_sat[src] + gid_to_sat_gsl_if_idx[final_next_hop - num_satellites]
                        nxt_if = 0
                        stats['BR'] += 1 # SBR usually not applicable for last hop
                    
                    new_entry = (final_next_hop, my_if, nxt_if)
                else:
                    new_entry = (-1, -1, -1)
                    stats['Drop'] += 1
                
                # Always add to fstate (complete state)
                fstate[(src, dst)] = new_entry

                # Only write if changed from previous output
                prev_entry = prev_output.get("fstate", {}).get((src, dst), None)
                if new_entry != prev_entry:
                    f_out.write(f"{src},{dst},{new_entry[0]},{new_entry[1]},{new_entry[2]}\n")

        # (GS -> GS) - Simplified
        for src_gid in range(num_ground_stations):
            src = num_satellites + src_gid
            for dst_gid in range(num_ground_stations):
                dst = num_satellites + dst_gid
                if src == dst: continue
                
                # Check if source GS has any satellites in range
                if len(ground_station_satellites_in_range[src_gid]) == 0:
                    # No satellite in range - mark as dropped
                    new_entry = (-1, -1, -1)
                    prev_entry = prev_output.get("fstate", {}).get((src, dst), None)
                    
                    # Always add to fstate
                    fstate[(src, dst)] = new_entry

                    if new_entry != prev_entry:
                        f_out.write(f"{src},{dst},-1,-1,-1\n")
                    continue
                
                hops = next_hops_map.get((src, dst), {'br': None, 'sbr': None})
                final_next_hop = hops['br'] # Just use BR for GS uplink
                
                if final_next_hop is not None and final_next_hop < num_satellites:
                    my_if = 0
                    nxt_if = num_isls_per_sat[final_next_hop] + gid_to_sat_gsl_if_idx[src_gid]
                    new_entry = (final_next_hop, my_if, nxt_if)
                else:
                    new_entry = (-1, -1, -1)
                
                # Always add to fstate (complete state)
                fstate[(src, dst)] = new_entry

                # Only write if changed from previous output
                prev_entry = prev_output.get("fstate", {}).get((src, dst), None)
                if new_entry != prev_entry:
                    f_out.write(f"{src},{dst},{new_entry[0]},{new_entry[1]},{new_entry[2]}\n")

    # 5. Write GSL Bandwidth (Required by ns-3)
    bw_filename = output_dynamic_state_dir + "/gsl_if_bandwidth_" + str(time_since_epoch_ns) + ".txt"
    with open(bw_filename, "w+") as f_out:
        if time_since_epoch_ns == 0: # Static bandwidth
            for node_id in range(num_satellites):
                f_out.write(f"{node_id},{num_isls_per_sat[node_id]},{list_gsl_interfaces_info[node_id]['aggregate_max_bandwidth']}\n")
            for node_id in range(num_satellites, num_satellites + num_ground_stations):
                f_out.write(f"{node_id},0,{list_gsl_interfaces_info[node_id]['aggregate_max_bandwidth']}\n")

    if enable_verbose_logs:
        print(f"  > Routing Decisions: BR={stats['BR']}, SBR={stats['SBR']}, Drop={stats['Drop']}")
        print("="*60)

    return {"fstate": fstate}