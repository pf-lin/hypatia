# The MIT License (MIT)
#
# Copyright (c) 2020 ETH Zurich
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from .fstate_calculation import *


def algorithm_paired_one_only_over_isls(
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
        enable_verbose_logs
):
    """
    PAIRED-ONE ONLY OVER INTER-SATELLITE LINKS ALGORITHM

    "one"
    This algorithm assumes that every satellite and ground station has exactly 1 GSL interface.

    "paired"
    Every ground station is paired to its nearest satellite. This pairing is enforced in the
    forwarding state: from then on all packets from this ground station will be sent to this satellite.

    "only_over_isls"
    It calculates a forwarding state, which is essentially a single shortest path.
    It only considers paths which go over the inter-satellite network, and does not make use of ground
    stations relay. This means that every path looks like:
    (src gs) - (sat) - (sat) - ... - (sat) - (dst gs)
    """

    if enable_verbose_logs:
        print("\nALGORITHM: PAIRED ONE ONLY OVER ISLS")

    # Check the graph
    if sat_net_graph_only_satellites_with_isls.number_of_nodes() != len(satellites):
        raise ValueError("Number of nodes in the graph does not match the number of satellites")
    for sid in range(len(satellites)):
        for n in sat_net_graph_only_satellites_with_isls.neighbors(sid):
            if n >= len(satellites):
                raise ValueError("Graph cannot contain satellite-to-ground-station links")

    ###########################################################
    # Select the nearest satellite for each ground station
    #

    # Keep track of which satellite GSL interfaces are paired
    # because it is the closest satellite to a ground station
    satellite_gsl_ifs_paired = []
    for sid in range(len(satellites)):
        satellite_gsl_ifs_paired.append([])

    # Go over each ground station
    ground_station_satellites_in_range_select_one_at_most = []
    for gid in range(len(ground_stations)):

        # Find the closest satellite
        chosen_sid = -1
        best_distance_m = 1000000000000000
        for (distance_m, sid) in ground_station_satellites_in_range[gid]:
            if distance_m < best_distance_m:
                chosen_sid = sid
                best_distance_m = distance_m

        # It is possible that a ground station does not have a single satellite in-range
        if chosen_sid == -1:
            ground_station_satellites_in_range_select_one_at_most.append([])
        else:
            ground_station_satellites_in_range_select_one_at_most.append([(best_distance_m, chosen_sid)])
            satellite_gsl_ifs_paired[chosen_sid].append(gid)

    ##################################################
    # Determine the new GSL interface bandwidth state
    #

    # Bandwidth state
    gsl_if_bandwidth_state = {}

    # For the satellite
    for sid in range(len(satellites)):
        # The paired GSL interfaces share the total bandwidth
        satellite_frequency_chosen = len(satellite_gsl_ifs_paired[sid])
        if satellite_frequency_chosen > 0:
            # Satellite has pairing(s) - divide bandwidth equally
            gsl_if_bandwidth_state[(sid, num_isls_per_sat[sid])] = 1.0 / float(satellite_frequency_chosen)
        else:
            # No pairings, full bandwidth available
            gsl_if_bandwidth_state[(sid, num_isls_per_sat[sid])] = 1.0

    # For the ground stations, the same principle applies
    for gid in range(len(ground_stations)):
        # Check if it is paired
        if len(ground_station_satellites_in_range_select_one_at_most[gid]) == 1:
            # Find the satellite it is paired to, and then only get its fair share
            paired_satellite_id = ground_station_satellites_in_range_select_one_at_most[gid][0][1]
            satellite_frequency_chosen = len(satellite_gsl_ifs_paired[paired_satellite_id])
            gsl_if_bandwidth_state[(len(satellites) + gid, 0)] = 1.0 / float(satellite_frequency_chosen)
        else:
            # Not paired, full bandwidth (though no connectivity)
            gsl_if_bandwidth_state[(len(satellites) + gid, 0)] = 1.0

    ######################################################
    # Write the new GSL interface bandwidth state (delta)
    #

    # Previous GSL interface bandwidth state (to only write delta)
    prev_gsl_if_bandwidth_state = None
    if prev_output is not None and "gsl_if_bandwidth_state" in prev_output:
        prev_gsl_if_bandwidth_state = prev_output["gsl_if_bandwidth_state"]

    output_filename = output_dynamic_state_dir + "/gsl_if_bandwidth_" + str(time_since_epoch_ns) + ".txt"
    if enable_verbose_logs:
        print("  > Writing interface bandwidth state to: " + output_filename)
    with open(output_filename, "w+") as f_out:
        for (node_id, if_id) in gsl_if_bandwidth_state:
            # Only write if no previous state or if the state has changed
            if (
                    prev_gsl_if_bandwidth_state is None
                    or
                    (node_id, if_id) not in prev_gsl_if_bandwidth_state
                    or
                    prev_gsl_if_bandwidth_state[(node_id, if_id)] != gsl_if_bandwidth_state[(node_id, if_id)]
            ):
                f_out.write("%d,%d,%f\n" % (
                    node_id,
                    if_id,
                    gsl_if_bandwidth_state[(node_id, if_id)]
                ))

    #################################
    # FORWARDING STATE
    #

    # Previous forwarding state (to only write delta)
    prev_fstate = None
    if prev_output is not None and "fstate" in prev_output:
        prev_fstate = prev_output["fstate"]

    # GID to satellite GSL interface index
    # For "one" mode, all ground stations use the first (and only) GSL interface of satellites
    gid_to_sat_gsl_if_idx = [0] * len(ground_stations)  

    # Forwarding state using shortest paths
    fstate = calculate_fstate_shortest_path_without_gs_relaying(
        output_dynamic_state_dir,
        time_since_epoch_ns,
        len(satellites),
        len(ground_stations),
        sat_net_graph_only_satellites_with_isls,
        num_isls_per_sat,
        gid_to_sat_gsl_if_idx,
        ground_station_satellites_in_range_select_one_at_most,  # Use restricted satellite selection
        sat_neighbor_to_if,
        prev_fstate,
        enable_verbose_logs
    )

    if enable_verbose_logs:
        print("")

    return {
        "fstate": fstate,
        "gsl_if_bandwidth_state": gsl_if_bandwidth_state
    }