"""
TLR (Traffic-Light-Based Intelligent Routing) Algorithm
Based on: "TLR: A Traffic-Light-Based Intelligent Routing Strategy for NGEO Satellite IP Networks"
"""

import csv
import os
import math
import networkx as nx
from collections import defaultdict


# ========== 1. Constants & Configuration ==========

class TLRConfig:
    """TLR Algorithm Configuration"""
    def __init__(self):
        # Buffer configuration
        self.buffer_size = 75  # packets (configurable)
        
        # QOR (Queue Occupancy Rate) thresholds for individual links
        self.qor_t1 = 0.5  # Green -> Yellow threshold
        self.qor_t2 = 0.8  # Yellow -> Red threshold
        
        # TQOR (Total Queue Occupancy Rate) thresholds for satellite nodes
        self.tqor_t_gy = 0.6  # Green -> Yellow threshold
        self.tqor_t_yr = 0.9  # Yellow -> Red threshold


# ========== 2. Traffic Light Color Definitions ==========

class TrafficColor:
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


# ========== 3. Load Queue Statistics & Calculate States ==========

def load_queue_and_calculate_states(queue_stats_file, num_satellites, config, enable_verbose_logs):
    """
    Load queue statistics and calculate traffic light states
    
    Returns:
        dict: {
            'link_queue_len': {(sat_from, sat_to): queue_length},
            'link_qor': {(sat_from, sat_to): qor_value},
            'link_color': {(sat_from, sat_to): TrafficColor},
            'node_tqor': {sat_id: tqor_value},
            'node_color': {sat_id: TrafficColor},
            'final_link_color': {(sat_from, sat_to): TrafficColor}
        }
    """
    
    # Initialize data structures
    link_queue_len = {}
    link_qor = {}
    link_color = {}
    node_outgoing_queue_sum = defaultdict(int)
    node_total_buffer = {}
    node_tqor = {}
    node_color = {}
    
    # === Step 1: Load queue statistics ===
    if not queue_stats_file:
        if enable_verbose_logs:
            print("  > No queue stats file provided, initializing with zeros.")
        # Initialize with zeros
        link_queue_len = {(i, j): 0 for i in range(num_satellites) for j in range(num_satellites) if i != j}
    elif not os.path.exists(queue_stats_file):
        if enable_verbose_logs:
            print(f"  > Warning: Queue stats file not found: {queue_stats_file}")
    else:
        with open(queue_stats_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sat_from = int(row['from'])
                sat_to = int(row['to'])
                
                if sat_from < num_satellites and sat_to < num_satellites:
                    queue_len = int(row['packet_sum'])
                    link_queue_len[(sat_from, sat_to)] = queue_len
    
    # === Step 2: Calculate QOR for each link (Current Hop State) ===
    for (sat_from, sat_to), q_len in link_queue_len.items():
        qor = q_len / config.buffer_size
        link_qor[(sat_from, sat_to)] = qor
        
        # Determine link color based on QOR thresholds (Table I, Current Hop)
        if qor < config.qor_t1:
            link_color[(sat_from, sat_to)] = TrafficColor.GREEN
        elif qor < config.qor_t2:
            link_color[(sat_from, sat_to)] = TrafficColor.YELLOW
        else:
            link_color[(sat_from, sat_to)] = TrafficColor.RED
        
        # Accumulate outgoing queue for TQOR calculation
        node_outgoing_queue_sum[sat_from] += q_len
    
    # === Step 3: Calculate TQOR for each node (Next Hop State) ===
    for sat_id in range(num_satellites):
        # Count number of outgoing links (ISLs)
        num_outgoing = sum(1 for (from_id, _) in link_queue_len.keys() if from_id == sat_id)
        
        if num_outgoing == 0:
            node_tqor[sat_id] = 0.0
            node_color[sat_id] = TrafficColor.GREEN
            continue
        
        # Total buffer = buffer_size * number of outgoing links
        total_buffer = config.buffer_size * num_outgoing
        node_total_buffer[sat_id] = total_buffer
        
        # TQOR = sum of all outgoing queues / total buffer
        tqor = node_outgoing_queue_sum[sat_id] / total_buffer if total_buffer > 0 else 0.0
        node_tqor[sat_id] = tqor
        
        # Determine node color based on TQOR thresholds (Table I, Next Hop)
        if tqor < config.tqor_t_gy:
            node_color[sat_id] = TrafficColor.GREEN
        elif tqor < config.tqor_t_yr:
            node_color[sat_id] = TrafficColor.YELLOW
        else:
            node_color[sat_id] = TrafficColor.RED
    
    # === Step 4: Combine to get Final Link Color (Table I) ===
    final_link_color = {}
    
    for (sat_from, sat_to) in link_queue_len.keys():
        current_hop_color = link_color.get((sat_from, sat_to), TrafficColor.GREEN)
        next_hop_color = node_color.get(sat_to, TrafficColor.GREEN)
        
        # Apply Table I logic (Combination of Current Hop QOR and Next Hop TQOR)
        final_color = combine_traffic_colors(current_hop_color, next_hop_color)
        final_link_color[(sat_from, sat_to)] = final_color
    
    # === Logging ===
    if enable_verbose_logs:
        print("\n  === TLR Traffic Light States ===")
        
        # Count link colors
        link_color_counts = {TrafficColor.GREEN: 0, TrafficColor.YELLOW: 0, TrafficColor.RED: 0}
        for color in final_link_color.values():
            link_color_counts[color] += 1
        
        print(f"  > Links: Green={link_color_counts[TrafficColor.GREEN]}, "
              f"Yellow={link_color_counts[TrafficColor.YELLOW]}, "
              f"Red={link_color_counts[TrafficColor.RED]}")
        
        # Count node colors
        node_color_counts = {TrafficColor.GREEN: 0, TrafficColor.YELLOW: 0, TrafficColor.RED: 0}
        for color in node_color.values():
            node_color_counts[color] += 1
        
        print(f"  > Nodes: Green={node_color_counts[TrafficColor.GREEN]}, "
              f"Yellow={node_color_counts[TrafficColor.YELLOW]}, "
              f"Red={node_color_counts[TrafficColor.RED]}")
    
    return {
        'link_queue_len': link_queue_len,
        'link_qor': link_qor,
        'link_color': link_color,
        'node_tqor': node_tqor,
        'node_color': node_color,
        'final_link_color': final_link_color
    }


def combine_traffic_colors(current_hop_color, next_hop_color):
    """
    Combine Current Hop QOR color and Next Hop TQOR color (Table I from paper)
    
    Table I Logic:
    Current\\Next  | Green  | Yellow | Red
    ---------------|--------|--------|-----
    Green          | Green  | Yellow | Red
    Yellow         | Yellow | Yellow | Red
    Red            | Red    | Red    | Red
    """
    if current_hop_color == TrafficColor.RED or next_hop_color == TrafficColor.RED:
        return TrafficColor.RED
    elif current_hop_color == TrafficColor.YELLOW or next_hop_color == TrafficColor.YELLOW:
        return TrafficColor.YELLOW
    else:
        return TrafficColor.GREEN


# ========== 4. Calculate BR and SBR Paths ==========

def calculate_br_and_sbr_paths(graph, num_satellites, num_ground_stations, enable_verbose_logs):
    """
    Calculate Best Route (BR) and Second Best Route (SBR) for all pairs
    
    Returns:
        dict: {
            (src, dst): {
                'br': [path_list],  # Best Route
                'sbr': [path_list]  # Second Best Route (or None if no alternative)
            }
        }
    """
    paths = {}
    
    if enable_verbose_logs:
        print("\n  === Calculating BR and SBR Paths ===")
    
    # For each satellite to each ground station
    for src_sat in range(num_satellites):
        for dst_gid in range(num_ground_stations):
            dst_node = num_satellites + dst_gid
            
            try:
                # Get top 2 shortest simple paths
                k_paths = list(nx.shortest_simple_paths(
                    graph, 
                    source=src_sat, 
                    target=dst_node, 
                    weight='weight'
                ))
                
                br = k_paths[0] if len(k_paths) > 0 else None
                sbr = k_paths[1] if len(k_paths) > 1 else None
                
                paths[(src_sat, dst_node)] = {
                    'br': br,
                    'sbr': sbr
                }
                
            except nx.NetworkXNoPath:
                paths[(src_sat, dst_node)] = {
                    'br': None,
                    'sbr': None
                }
    
    # Ground station to ground station
    for src_gid in range(num_ground_stations):
        for dst_gid in range(num_ground_stations):
            if src_gid == dst_gid:
                continue
            
            src_node = num_satellites + src_gid
            dst_node = num_satellites + dst_gid
            
            try:
                k_paths = list(nx.shortest_simple_paths(
                    graph,
                    source=src_node,
                    target=dst_node,
                    weight='weight'
                ))
                
                br = k_paths[0] if len(k_paths) > 0 else None
                sbr = k_paths[1] if len(k_paths) > 1 else None
                
                paths[(src_node, dst_node)] = {
                    'br': br,
                    'sbr': sbr
                }
                
            except nx.NetworkXNoPath:
                paths[(src_node, dst_node)] = {
                    'br': None,
                    'sbr': None
                }
    
    if enable_verbose_logs:
        pairs_with_sbr = sum(1 for p in paths.values() if p['sbr'] is not None)
        print(f"  > Total paths calculated: {len(paths)}")
        print(f"  > Paths with SBR available: {pairs_with_sbr}")
    
    return paths


# ========== 5. Make Routing Decision (Table II) ==========

def make_routing_decision(src, dst, paths_info, traffic_states, enable_verbose_logs=False):
    """
    Apply Table II logic to decide between BR and SBR
    
    Table II Logic:
    BR Color | SBR Color | Decision
    ---------|-----------|----------
    Green    | *         | Use BR
    Yellow   | Green     | Use SBR (offload)
    Yellow   | Yellow    | Use SBR (offload)
    Yellow   | Red       | Use BR
    Red      | Green     | Use SBR
    Red      | Yellow    | Use SBR
    Red      | Red       | Use BR (or apply drop logic)
    
    Returns:
        str: 'BR' or 'SBR'
    """
    br_path = paths_info['br']
    sbr_path = paths_info['sbr']
    
    # No path available
    if br_path is None:
        return 'BR'  # Will result in -1 (drop)
    
    # Get next hop for BR
    if len(br_path) < 2:
        return 'BR'  # Direct connection or unreachable
    
    next_hop_br = br_path[1]
    link_br = (src, next_hop_br)
    
    # Get BR link color
    br_color = traffic_states['final_link_color'].get(link_br, TrafficColor.GREEN)
    
    # No SBR available
    if sbr_path is None or len(sbr_path) < 2:
        return 'BR'
    
    # Get next hop for SBR
    next_hop_sbr = sbr_path[1]
    link_sbr = (src, next_hop_sbr)
    
    # Get SBR link color
    sbr_color = traffic_states['final_link_color'].get(link_sbr, TrafficColor.GREEN)
    
    # Apply Table II logic
    if br_color == TrafficColor.GREEN:
        return 'BR'
    
    elif br_color == TrafficColor.YELLOW:
        if sbr_color in [TrafficColor.GREEN, TrafficColor.YELLOW]:
            return 'SBR'  # Offload to avoid congestion
        else:  # sbr_color == RED
            return 'BR'
    
    else:  # br_color == RED
        if sbr_color in [TrafficColor.GREEN, TrafficColor.YELLOW]:
            return 'SBR'
        else:  # sbr_color == RED
            # Both are RED - choose the one with lower QOR
            qor_br = traffic_states['link_qor'].get(link_br, 1.0)
            qor_sbr = traffic_states['link_qor'].get(link_sbr, 1.0)
            
            if qor_sbr < qor_br:
                return 'SBR'
            else:
                return 'BR'


# ========== 6. Main TLR Algorithm ==========

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
    """
    TLR (Traffic-Light-Based Intelligent Routing) Algorithm
    """
    
    if enable_verbose_logs:
        print("\n" + "="*70)
        print("ALGORITHM: TLR (Traffic-Light-Based Intelligent Routing)")
        print("="*70)
    
    # Initialize configuration
    if tlr_config is None:
        tlr_config = TLRConfig()
    
    num_satellites = len(satellites)
    num_ground_stations = len(ground_stations)
    
    # === Step 1: Load queue statistics and calculate traffic light states ===
    traffic_states = load_queue_and_calculate_states(
        queue_stats_file,
        num_satellites,
        tlr_config,
        enable_verbose_logs
    )
    
    # === Step 2: Build full network graph (satellites + ground stations) ===
    full_graph = sat_net_graph_only_satellites_with_isls.copy()
    
    # Add ground stations and GSLs
    for gid, gs_sats_in_range in enumerate(ground_station_satellites_in_range):
        gs_node = num_satellites + gid
        full_graph.add_node(gs_node)
        
        for (distance_m, sat_id) in gs_sats_in_range:
            full_graph.add_edge(sat_id, gs_node, weight=distance_m)
    
    # === Step 3: Calculate BR and SBR for all pairs ===
    all_paths = calculate_br_and_sbr_paths(
        full_graph,
        num_satellites,
        num_ground_stations,
        enable_verbose_logs
    )
    
    # === Step 4: Generate forwarding state ===
    fstate = {}
    gid_to_sat_gsl_if_idx = [0] * num_ground_stations
    
    output_filename = output_dynamic_state_dir + "/fstate_" + str(time_since_epoch_ns) + ".txt"
    
    if enable_verbose_logs:
        print(f"\n  > Writing forwarding state to: {output_filename}")
    
    decisions_br = 0
    decisions_sbr = 0
    decisions_drop = 0
    
    with open(output_filename, "w+") as f_out:
        
        # Satellites to ground stations
        for src_sat in range(num_satellites):
            for dst_gid in range(num_ground_stations):
                dst_node = num_satellites + dst_gid
                
                paths_info = all_paths.get((src_sat, dst_node), {'br': None, 'sbr': None})
                
                # Make routing decision
                decision = make_routing_decision(
                    src_sat,
                    dst_node,
                    paths_info,
                    traffic_states,
                    enable_verbose_logs=False
                )
                
                # Get the chosen path
                if decision == 'SBR' and paths_info['sbr'] is not None:
                    chosen_path = paths_info['sbr']
                    decisions_sbr += 1
                elif paths_info['br'] is not None:
                    chosen_path = paths_info['br']
                    decisions_br += 1
                else:
                    chosen_path = None
                    decisions_drop += 1
                
                # Determine next hop
                next_hop_decision = (-1, -1, -1)
                
                if chosen_path and len(chosen_path) >= 2:
                    next_hop = chosen_path[1]
                    
                    if next_hop < num_satellites:
                        # Next hop is satellite
                        next_hop_decision = (
                            next_hop,
                            sat_neighbor_to_if.get((src_sat, next_hop), 0),
                            sat_neighbor_to_if.get((next_hop, src_sat), 0)
                        )
                    else:
                        # Next hop is ground station
                        next_hop_decision = (
                            next_hop,
                            num_isls_per_sat[src_sat] + gid_to_sat_gsl_if_idx[next_hop - num_satellites],
                            0
                        )
                
                # Write if changed
                prev_fstate = prev_output['fstate'] if prev_output else None
                if not prev_fstate or prev_fstate.get((src_sat, dst_node)) != next_hop_decision:
                    f_out.write("%d,%d,%d,%d,%d\n" % (
                        src_sat,
                        dst_node,
                        next_hop_decision[0],
                        next_hop_decision[1],
                        next_hop_decision[2]
                    ))
                
                fstate[(src_sat, dst_node)] = next_hop_decision
        
        # Ground stations to ground stations
        for src_gid in range(num_ground_stations):
            for dst_gid in range(num_ground_stations):
                if src_gid == dst_gid:
                    continue
                
                src_node = num_satellites + src_gid
                dst_node = num_satellites + dst_gid
                
                paths_info = all_paths.get((src_node, dst_node), {'br': None, 'sbr': None})
                
                # For GS-to-GS, just use BR (simplified)
                chosen_path = paths_info['br']
                
                next_hop_decision = (-1, -1, -1)
                
                if chosen_path and len(chosen_path) >= 2:
                    next_hop = chosen_path[1]
                    
                    # Next hop must be a satellite for GS-to-GS
                    if next_hop < num_satellites:
                        next_hop_decision = (
                            next_hop,
                            0,
                            num_isls_per_sat[next_hop] + gid_to_sat_gsl_if_idx[src_gid]
                        )
                
                prev_fstate = prev_output['fstate'] if prev_output else None
                if not prev_fstate or prev_fstate.get((src_node, dst_node)) != next_hop_decision:
                    f_out.write("%d,%d,%d,%d,%d\n" % (
                        src_node,
                        dst_node,
                        next_hop_decision[0],
                        next_hop_decision[1],
                        next_hop_decision[2]
                    ))
                
                fstate[(src_node, dst_node)] = next_hop_decision
    
    # === Step 5: Write GSL interface bandwidth ===
    output_filename = output_dynamic_state_dir + "/gsl_if_bandwidth_" + str(time_since_epoch_ns) + ".txt"
    if enable_verbose_logs:
        print("  > Writing interface bandwidth state to: " + output_filename)
    
    with open(output_filename, "w+") as f_out:
        if time_since_epoch_ns == 0:
            for node_id in range(num_satellites):
                f_out.write("%d,%d,%f\n" % (
                    node_id,
                    num_isls_per_sat[node_id],
                    list_gsl_interfaces_info[node_id]["aggregate_max_bandwidth"]
                ))
            for node_id in range(num_satellites, num_satellites + num_ground_stations):
                f_out.write("%d,%d,%f\n" % (
                    node_id,
                    0,
                    list_gsl_interfaces_info[node_id]["aggregate_max_bandwidth"]
                ))
    
    # === Logging ===
    if enable_verbose_logs:
        print(f"\n  === Routing Decisions Summary ===")
        print(f"  > Used BR (Best Route): {decisions_br}")
        print(f"  > Used SBR (Second Best Route): {decisions_sbr}")
        print(f"  > Dropped (no path): {decisions_drop}")
        print("="*70 + "\n")
    
    return {
        "fstate": fstate
    }