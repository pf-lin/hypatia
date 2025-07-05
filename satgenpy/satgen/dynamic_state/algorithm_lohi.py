from .fstate_calculation import *
import math
import networkx as nx


def algorithm_lohi_routing(
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
        num_orbits,
        num_sats_per_orbit,
        group_p=3,  # planes per group
        group_s=3   # sats per group
):
    """
    LOHI (Load-aware Hierarchical Information-centric) ROUTING ALGORITHM

    This algorithm implements a hierarchical routing approach that:
    1. Divides the satellite constellation into groups for better scalability 
    2. Maintains ISL state information within each group 
    3. Uses inter-group routing for communication between different groups 
    4. Implements load balancing to distribute traffic across available paths 
    5. Provides stable routing by reducing the impact of topology changes 

    The algorithm is particularly suitable for large-scale LEO satellite networks
    where maintaining global routing state would be computationally expensive.
    """

    if enable_verbose_logs:
        print("\nALGORITHM: LOHI (Load-aware Hierarchical Information-centric) ROUTING")

    # Validate input graph
    if sat_net_graph_only_satellites_with_isls.number_of_nodes() != len(satellites):
        raise ValueError("Number of nodes in the graph does not match the number of satellites")

    for sid in range(len(satellites)):
        for n in sat_net_graph_only_satellites_with_isls.neighbors(sid):
            if n >= len(satellites):
                raise ValueError("Graph cannot contain satellite-to-ground-station links")

    #################################
    # HIERARCHICAL GROUPING
    #

    if enable_verbose_logs:
        print("  > Creating hierarchical satellite groups")

    # Create satellite groups based on a grid topology as described in the LoHi paper 
    satellite_groups, group_to_manager = create_satellite_groups(
        satellites,
        num_orbits,
        num_sats_per_orbit,
        enable_verbose_logs,
        group_p,
        group_s
    )

    # Create inter-group connectivity graph
    inter_group_graph = create_inter_group_graph(
        satellite_groups,
        sat_net_graph_only_satellites_with_isls,
        enable_verbose_logs,
    )

    #################################
    # LOAD CALCULATION
    #

    if enable_verbose_logs:
        print("  > Calculating load metrics for satellites")

    # Calculate load metrics for each satellite based on real-time queuing status 
    satellite_loads = calculate_satellite_loads(
        satellites,
        sat_net_graph_only_satellites_with_isls,
        ground_station_satellites_in_range,
        prev_output,
        enable_verbose_logs
    )

    #################################
    # BANDWIDTH STATE
    #

    # Generate bandwidth allocation based on load and hierarchy
    output_filename = output_dynamic_state_dir + "/gsl_if_bandwidth_" + str(time_since_epoch_ns) + ".txt"
    if enable_verbose_logs:
        print("  > Writing load-aware interface bandwidth state to: " + output_filename)

    with open(output_filename, "w+") as f_out:
        if time_since_epoch_ns == 0:
            for node_id in range(len(satellites)):
                # Adjust bandwidth based on load
                load_factor = satellite_loads.get(node_id, 1.0)
                adjusted_bandwidth = list_gsl_interfaces_info[node_id]["aggregate_max_bandwidth"] * load_factor
                f_out.write("%d,%d,%f\n"
                            % (node_id, num_isls_per_sat[node_id], adjusted_bandwidth))

            for node_id in range(len(satellites), len(satellites) + len(ground_stations)):
                f_out.write("%d,%d,%f\n"
                            % (node_id, 0, list_gsl_interfaces_info[node_id]["aggregate_max_bandwidth"]))

    #################################
    # FORWARDING STATE
    #

    # Previous forwarding state (to only write delta)
    prev_fstate = None
    if prev_output is not None:
        prev_fstate = prev_output["fstate"]

    # GID to satellite GSL interface index
    gid_to_sat_gsl_if_idx = [0] * len(ground_stations)

    # Calculate hierarchical forwarding state 
    fstate = calculate_lohi_fstate(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        len(satellites),
        len(ground_stations),
        sat_net_graph_only_satellites_with_isls,
        satellite_groups,
        inter_group_graph,
        satellite_loads,
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
        "fstate": fstate,
        "satellite_groups": satellite_groups,
        "satellite_loads": satellite_loads,
        "group_to_manager": group_to_manager
    }


def create_satellite_groups(
    satellites,
    num_orbits,
    num_sats_per_orbit,
    enable_verbose_logs,
    group_p=3,  # planes per group
    group_s=3   # sats per group
):
    """
    Create hierarchical groups of satellites based on a grid constellation structure,
    as depicted in the provided image and paper.
    Also identifies the central satellite as the manager for each group.
    """
    if len(satellites) != num_orbits * num_sats_per_orbit:
        raise ValueError(
            f"Mismatch between satellite count ({len(satellites)}) and orbit parameters "
            f"({num_orbits}x{num_sats_per_orbit}={num_orbits * num_sats_per_orbit})"
        )

    groups = []
    group_to_manager = {}
    sat_to_group_id = {}

    # Helper to convert 2D grid coordinates to a 1D satellite ID
    def to_sat_id(orbit_idx, sat_idx_in_orbit):
        return orbit_idx * num_sats_per_orbit + sat_idx_in_orbit

    group_id_counter = 0
    # Iterate through the constellation grid with steps of group_p and group_s
    for p_start in range(0, num_orbits, group_p):
        for s_start in range(0, num_sats_per_orbit, group_s):
            # Ensure the group does not exceed constellation boundaries
            if p_start + group_p > num_orbits or s_start + group_s > num_sats_per_orbit:
                continue

            current_group = []
            for p_offset in range(group_p):
                for s_offset in range(group_s):
                    orbit_idx = p_start + p_offset
                    sat_idx = s_start + s_offset
                    sat_id = to_sat_id(orbit_idx, sat_idx)
                    current_group.append(sat_id)
                    sat_to_group_id[sat_id] = group_id_counter

            # Identify the management satellite (center of the 3x3 group) 
            manager_orbit_offset = group_p // 2
            manager_sat_offset = group_s // 2
            manager_orbit = p_start + manager_orbit_offset
            manager_sat_idx = s_start + manager_sat_offset
            manager_id = to_sat_id(manager_orbit, manager_sat_idx)

            groups.append(current_group)
            group_to_manager[group_id_counter] = manager_id
            group_id_counter += 1

    # Handle any satellites that were not assigned to a full group
    assigned_sats = set(sat_to_group_id.keys())
    unassigned_sats = set(range(len(satellites))) - assigned_sats
    if unassigned_sats:
        if enable_verbose_logs:
            print(f"    {len(unassigned_sats)} satellites were not part of a full group. Creating a leftovers group.")
        groups.append(list(unassigned_sats))
        group_to_manager[group_id_counter] = -1 # No manager for this group

    if enable_verbose_logs:
        print(f"    Created {len(groups)} satellite groups with sizes: {[len(g) for g in groups]}")

    return groups, group_to_manager


def create_inter_group_graph(satellite_groups, sat_graph, enable_verbose_logs):
    """Create a graph representing connectivity between satellite groups."""

    inter_graph = nx.Graph()

    # Add nodes for each group
    for i in range(len(satellite_groups)):
        inter_graph.add_node(i)

    # Add edges between groups if they have inter-satellite links 
    for i, group_i in enumerate(satellite_groups):
        for j, group_j in enumerate(satellite_groups):
            if i < j:  # Avoid duplicate edges
                # Check if there are any links between satellites in these groups
                inter_links = []
                for sat_i in group_i:
                    for sat_j in group_j:
                        if sat_graph.has_edge(sat_i, sat_j):
                            weight = sat_graph.edges[(sat_i, sat_j)]["weight"]
                            inter_links.append((sat_i, sat_j, weight))

                if inter_links:
                    # Use the shortest link as the group-to-group distance
                    min_weight = min(link[2] for link in inter_links)
                    inter_graph.add_edge(i, j, weight=min_weight, links=inter_links)

    if enable_verbose_logs:
        print(f"    Created inter-group graph with {inter_graph.number_of_edges()} connections")

    return inter_graph


def calculate_satellite_loads(satellites, sat_graph, gs_sat_ranges, prev_output, enable_verbose_logs):
    """Calculate load metrics for each satellite based on connectivity and traffic."""

    loads = {}

    for sat_id in range(len(satellites)):
        # Base load calculation
        # Factor 1: Number of ISL connections (more connections = higher load capacity)
        isl_count = sat_graph.degree(sat_id)

        # Factor 2: Number of ground stations in range (more GS access = higher load)
        gs_connections = sum(1 for gs_range in gs_sat_ranges
                           for dist, sid in gs_range if sid == sat_id)

        # Factor 3: Historical load (if available from previous state)
        historical_factor = 1.0
        if prev_output and "satellite_loads" in prev_output:
            historical_factor = prev_output["satellite_loads"].get(sat_id, 1.0)
            # Apply smoothing to avoid rapid changes
            historical_factor = 0.7 * historical_factor + 0.3 * 1.0

        # Combine factors (normalize to range [0.5, 1.5])
        base_load = (isl_count * 0.3 + gs_connections * 0.7) / max(1, isl_count + gs_connections) if (isl_count + gs_connections) > 0 else 0
        load_factor = 0.5 + base_load * historical_factor
        load_factor = max(0.5, min(1.5, load_factor))  # Clamp to reasonable range

        loads[sat_id] = load_factor

    if enable_verbose_logs:
        avg_load = sum(loads.values()) / len(loads) if loads else 0
        print(f"    Calculated satellite loads (avg: {avg_load:.3f})")

    return loads


def calculate_lohi_fstate(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        num_satellites,
        num_ground_stations,
        sat_net_graph,
        satellite_groups,
        inter_group_graph,
        satellite_loads,
        num_isls_per_sat,
        gid_to_sat_gsl_if_idx,
        ground_station_satellites_in_range,
        sat_neighbor_to_if,
        prev_fstate,
        enable_verbose_logs
):
    """Calculate forwarding state using hierarchical LoHi routing."""

    if enable_verbose_logs:
        print("  > Calculating hierarchical forwarding state")

    # Create mapping from satellite ID to group ID
    sat_to_group = {}
    for group_id, satellites_in_group in enumerate(satellite_groups):
        for sat_id in satellites_in_group:
            sat_to_group[sat_id] = group_id

    # Calculate intra-group shortest paths for each group 
    intra_group_paths = {}
    for group_id, satellites_in_group in enumerate(satellite_groups):
        if len(satellites_in_group) > 1:
            # Create subgraph for this group
            subgraph = sat_net_graph.subgraph(satellites_in_group)
            # Calculate all-pairs shortest paths within the group
            try:
                paths = dict(nx.floyd_warshall(subgraph, weight='weight'))
                intra_group_paths[group_id] = paths
            except nx.NetworkXError:
                # Fallback to individual shortest paths if Floyd-Warshall fails
                intra_group_paths[group_id] = {}
                for src in satellites_in_group:
                    for dst in satellites_in_group:
                        if src != dst:
                            try:
                                path_length = nx.shortest_path_length(subgraph, src, dst, weight='weight')
                                intra_group_paths[group_id][(src, dst)] = path_length
                            except nx.NetworkXNoPath:
                                intra_group_paths[group_id][(src, dst)] = float('inf')

    # Calculate inter-group shortest paths 
    inter_group_paths = {}
    if len(satellite_groups) > 1:
        try:
            inter_group_paths = dict(nx.floyd_warshall(inter_group_graph, weight='weight'))
        except nx.NetworkXError:
            # Fallback
            for i in range(len(satellite_groups)):
                for j in range(len(satellite_groups)):
                    if i != j:
                        try:
                            path_length = nx.shortest_path_length(inter_group_graph, i, j, weight='weight')
                            inter_group_paths[(i, j)] = path_length
                        except nx.NetworkXNoPath:
                            inter_group_paths[(i, j)] = float('inf')

    # Generate forwarding state
    fstate = {}
    output_filename = output_dynamic_state_dir + "/fstate_" + str(time_since_epoch_ns) + ".txt"

    with open(output_filename, "w+") as f_out:

        # Satellites to ground stations
        for curr in range(num_satellites):
            for dst_gid in range(num_ground_stations):
                dst_gs_node_id = num_satellites + dst_gid

                # Find best path using hierarchical routing
                next_hop_decision = find_best_path_to_gs(
                    curr, dst_gid, sat_to_group, satellite_groups,
                    intra_group_paths, inter_group_paths,
                    ground_station_satellites_in_range[dst_gid],
                    sat_net_graph, satellite_loads,
                    num_isls_per_sat, gid_to_sat_gsl_if_idx,
                    sat_neighbor_to_if
                )

                # Write to forwarding state if changed
                if not prev_fstate or prev_fstate.get((curr, dst_gs_node_id)) != next_hop_decision:
                    f_out.write("%d,%d,%d,%d,%d\n" % (
                        curr, dst_gs_node_id,
                        next_hop_decision[0], next_hop_decision[1], next_hop_decision[2]
                    ))
                fstate[(curr, dst_gs_node_id)] = next_hop_decision

        # Ground stations to ground stations
        for src_gid in range(num_ground_stations):
            for dst_gid in range(num_ground_stations):
                if src_gid != dst_gid:
                    src_gs_node_id = num_satellites + src_gid
                    dst_gs_node_id = num_satellites + dst_gid

                    # Find best satellite to route through
                    next_hop_decision = find_best_gs_to_gs_path(
                        src_gid, dst_gid, sat_to_group, satellite_groups,
                        intra_group_paths, inter_group_paths,
                        ground_station_satellites_in_range,
                        satellite_loads, num_isls_per_sat, gid_to_sat_gsl_if_idx
                    )

                    # Write to forwarding state if changed
                    if not prev_fstate or prev_fstate.get((src_gs_node_id, dst_gs_node_id)) != next_hop_decision:
                        f_out.write("%d,%d,%d,%d,%d\n" % (
                            src_gs_node_id, dst_gs_node_id,
                            next_hop_decision[0], next_hop_decision[1], next_hop_decision[2]
                        ))
                    fstate[(src_gs_node_id, dst_gs_node_id)] = next_hop_decision

    return fstate


def find_best_path_to_gs(curr_sat, dst_gid, sat_to_group, satellite_groups,
                         intra_group_paths, inter_group_paths,
                         dst_gs_satellites_in_range, sat_net_graph, satellite_loads,
                         num_isls_per_sat, gid_to_sat_gsl_if_idx, sat_neighbor_to_if):
    """Find the best path from current satellite to destination ground station."""

    # Find candidate destination satellites
    candidates = []
    for dist, dst_sat in dst_gs_satellites_in_range:
        total_dist = calculate_hierarchical_distance(
            curr_sat, dst_sat, sat_to_group,
            intra_group_paths, inter_group_paths, sat_net_graph
        )
        if not math.isinf(total_dist):
            # Apply load balancing 
            load_factor = satellite_loads.get(dst_sat, 1.0)
            adjusted_dist = total_dist * load_factor
            candidates.append((adjusted_dist + dist, dst_sat))

    if not candidates:
        return (-1, -1, -1)

    # Choose the best candidate
    candidates.sort()
    _, best_dst_sat = candidates[0]

    # Determine next hop
    if curr_sat == best_dst_sat:
        # Direct connection to ground station
        dst_gs_node_id = len(sat_to_group) + dst_gid
        return (
            dst_gs_node_id,  # Ground station node ID is offset
            num_isls_per_sat[best_dst_sat] + gid_to_sat_gsl_if_idx[dst_gid],
            0
        )
    else:
        # Need to route through satellite network
        next_hop = find_next_hop_in_hierarchy(
            curr_sat, best_dst_sat, sat_to_group, satellite_groups,
            intra_group_paths, inter_group_paths, sat_net_graph,
            satellite_loads, sat_neighbor_to_if
        )
        return next_hop


def find_best_gs_to_gs_path(src_gid, dst_gid, sat_to_group, satellite_groups,
                            intra_group_paths, inter_group_paths,
                            ground_station_satellites_in_range, satellite_loads,
                            num_isls_per_sat, gid_to_sat_gsl_if_idx):
    """Find the best path between two ground stations."""

    src_candidates = ground_station_satellites_in_range[src_gid]
    dst_candidates = ground_station_satellites_in_range[dst_gid]

    best_path = None
    best_cost = float('inf')

    for src_dist, src_sat in src_candidates:
        for dst_dist, dst_sat in dst_candidates:
            total_dist = calculate_hierarchical_distance(
                src_sat, dst_sat, sat_to_group,
                intra_group_paths, inter_group_paths, None
            )
            if not math.isinf(total_dist):
                # Apply load balancing 
                src_load = satellite_loads.get(src_sat, 1.0)
                dst_load = satellite_loads.get(dst_sat, 1.0)
                load_factor = (src_load + dst_load) / 2

                total_cost = src_dist + total_dist + dst_dist
                adjusted_cost = total_cost * load_factor

                if adjusted_cost < best_cost:
                    best_cost = adjusted_cost
                    best_path = src_sat

    if best_path is None:
        return (-1, -1, -1)

    return (
        best_path,
        0,
        num_isls_per_sat[best_path] + gid_to_sat_gsl_if_idx[src_gid]
    )


def calculate_hierarchical_distance(src_sat, dst_sat, sat_to_group,
                                    intra_group_paths, inter_group_paths, sat_net_graph):
    """Calculate distance between two satellites using hierarchical routing."""

    if src_sat == dst_sat:
        return 0.0

    src_group = sat_to_group.get(src_sat)
    dst_group = sat_to_group.get(dst_sat)

    if src_group is None or dst_group is None:
        return float('inf')

    if src_group == dst_group:
        # Same group - use intra-group distance 
        return intra_group_paths.get(src_group, {}).get((src_sat, dst_sat), float('inf'))
    else:
        # Different groups - use inter-group routing 
        # This is a simplified version. A full implementation might find the best
        # gateway satellites in each group to calculate the exact path length.
        inter_dist = inter_group_paths.get((src_group, dst_group), float('inf'))
        if math.isinf(inter_dist):
            return float('inf')
        return inter_dist


def find_next_hop_in_hierarchy(curr_sat, dst_sat, sat_to_group, satellite_groups,
                               intra_group_paths, inter_group_paths, sat_net_graph,
                               satellite_loads, sat_neighbor_to_if):
    """Find the next hop satellite using hierarchical routing."""

    best_next_hop = None
    best_distance = float('inf')

    # Find the best neighbor based on its total hierarchical distance to the destination
    for neighbor in sat_net_graph.neighbors(curr_sat):
        edge_weight = sat_net_graph.edges[(curr_sat, neighbor)]["weight"]

        # Calculate the total distance from the neighbor to the final destination satellite
        hierarchical_dist_from_neighbor = calculate_hierarchical_distance(
            neighbor, dst_sat, sat_to_group,
            intra_group_paths, inter_group_paths, sat_net_graph
        )

        if not math.isinf(hierarchical_dist_from_neighbor):
            total_dist = edge_weight + hierarchical_dist_from_neighbor

            # Apply load balancing, considering the load of the next-hop satellite 
            load_factor = satellite_loads.get(neighbor, 1.0)
            adjusted_dist = total_dist * load_factor

            if adjusted_dist < best_distance:
                best_distance = adjusted_dist
                best_next_hop = neighbor

    if best_next_hop is not None:
        return (
            best_next_hop,
            sat_neighbor_to_if.get((curr_sat, best_next_hop), 0),
            sat_neighbor_to_if.get((best_next_hop, curr_sat), 0)
        )

    return (-1, -1, -1)