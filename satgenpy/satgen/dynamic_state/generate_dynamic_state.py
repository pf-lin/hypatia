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

from satgen.distance_tools import *
from astropy import units as u
import math
import networkx as nx
import numpy as np
from .algorithm_free_one_only_gs_relays import algorithm_free_one_only_gs_relays
from .algorithm_free_one_only_over_isls import algorithm_free_one_only_over_isls
from .algorithm_paired_many_only_over_isls import algorithm_paired_many_only_over_isls
from .algorithm_paired_one_only_over_isls import algorithm_paired_one_only_over_isls
from .algorithm_free_gs_one_sat_many_only_over_isls import algorithm_free_gs_one_sat_many_only_over_isls
from .algorithm_lohi import algorithm_lohi_routing
from .algorithm_queue_aware_over_isls import algorithm_queue_aware_over_isls


def generate_dynamic_state(
        output_dynamic_state_dir,
        epoch,
        simulation_end_time_ns,
        time_step_ns,
        offset_ns,
        satellites,
        ground_stations,
        list_isls,
        list_gsl_interfaces_info,
        max_gsl_length_m,
        max_isl_length_m,
        dynamic_state_algorithm,  # Options:
                                  # "algorithm_free_one_only_gs_relays"
                                  # "algorithm_free_one_only_over_isls"
                                  # "algorithm_paired_many_only_over_isls"
                                  # "algorithm_paired_one_only_over_isls"
                                  # "algorithm_lohi_routing"
        enable_verbose_logs,
        num_orbits=None,
        num_sats_per_orbit=None
):
    if offset_ns % time_step_ns != 0:
        raise ValueError("Offset must be a multiple of time_step_ns")
    prev_output = None
    i = 0
    total_iterations = ((simulation_end_time_ns - offset_ns) / time_step_ns)
    for time_since_epoch_ns in range(offset_ns, simulation_end_time_ns, time_step_ns):
        if not enable_verbose_logs:
            if i % int(math.floor(total_iterations) / 10.0) == 0:
                print("Progress: calculating for T=%d (time step granularity is still %d ms)" % (
                    time_since_epoch_ns, time_step_ns / 1000000
                ))
            i += 1
        prev_output = generate_dynamic_state_at(
            output_dynamic_state_dir,
            epoch,
            time_since_epoch_ns,
            satellites,
            ground_stations,
            list_isls,
            list_gsl_interfaces_info,
            max_gsl_length_m,
            max_isl_length_m,
            dynamic_state_algorithm,
            prev_output,
            enable_verbose_logs,
            num_orbits,
            num_sats_per_orbit
        )


def generate_dynamic_state_at(
        output_dynamic_state_dir,
        epoch,
        time_since_epoch_ns,
        satellites,
        ground_stations,
        list_isls,
        list_gsl_interfaces_info,
        max_gsl_length_m,
        max_isl_length_m,
        dynamic_state_algorithm,
        prev_output,
        enable_verbose_logs,
        num_orbits=None,
        num_sats_per_orbit=None,
        queue_stats_file=None,  # for queue-aware algorithm
        alpha=0.7,              # weight for distance
        beta=0.3                # weight for queue delay
):
    if enable_verbose_logs:
        print("FORWARDING STATE AT T = " + (str(time_since_epoch_ns))
              + "ns (= " + str(time_since_epoch_ns / 1e9) + " seconds)")

    #################################

    if enable_verbose_logs:
        print("\nBASIC INFORMATION")

    # Time
    time = epoch + time_since_epoch_ns * u.ns
    if enable_verbose_logs:
        print("  > Epoch.................. " + str(epoch))
        print("  > Time since epoch....... " + str(time_since_epoch_ns) + " ns")
        print("  > Absolute time.......... " + str(time))

    # Graphs
    sat_net_graph_only_satellites_with_isls = nx.Graph()
    sat_net_graph_all_with_only_gsls = nx.Graph()

    # Information
    for i in range(len(satellites)):
        sat_net_graph_only_satellites_with_isls.add_node(i)
        sat_net_graph_all_with_only_gsls.add_node(i)
    for i in range(len(satellites) + len(ground_stations)):
        sat_net_graph_all_with_only_gsls.add_node(i)
    if enable_verbose_logs:
        print("  > Satellites............. " + str(len(satellites)))
        print("  > Ground stations........ " + str(len(ground_stations)))
        print("  > Max. range GSL......... " + str(max_gsl_length_m) + "m")
        print("  > Max. range ISL......... " + str(max_isl_length_m) + "m")

    #################################

    if enable_verbose_logs:
        print("\nISL INFORMATION")

    # ISL edges
    total_num_isls = 0
    num_isls_per_sat = [0] * len(satellites)
    sat_neighbor_to_if = {}

    isl_distances = []

    for (a, b) in list_isls:

        # ISLs are not permitted to exceed their maximum distance
        # TODO: Technically, they can (could just be ignored by forwarding state calculation),
        # TODO: but practically, defining a permanent ISL between two satellites which
        # TODO: can go out of distance is generally unwanted
        sat_distance_m = distance_m_between_satellites(satellites[a], satellites[b], str(epoch), str(time))
        isl_distances.append(sat_distance_m)
        if sat_distance_m > max_isl_length_m:
            raise ValueError(
                "The distance between two satellites (%d and %d) "
                "with an ISL exceeded the maximum ISL length (%.2fm > %.2fm at t=%dns)"
                % (a, b, sat_distance_m, max_isl_length_m, time_since_epoch_ns)
            )

        # Add to networkx graph
        sat_net_graph_only_satellites_with_isls.add_edge(
            a, b, weight=sat_distance_m
        )

        # Interface mapping of ISLs
        sat_neighbor_to_if[(a, b)] = num_isls_per_sat[a]
        sat_neighbor_to_if[(b, a)] = num_isls_per_sat[b]
        num_isls_per_sat[a] += 1
        num_isls_per_sat[b] += 1
        total_num_isls += 1

    if enable_verbose_logs:
        print("  > Total ISLs............. " + str(len(list_isls)))
        print("  > Min. ISLs/satellite.... " + str(np.min(num_isls_per_sat)))
        print("  > Max. ISLs/satellite.... " + str(np.max(num_isls_per_sat)))

    # 計算並顯示距離統計
    if len(isl_distances) > 0:
        min_distance = np.min(isl_distances)
        max_distance = np.max(isl_distances)
        avg_distance = np.mean(isl_distances)
        median_distance = np.median(isl_distances)
        std_distance = np.std(isl_distances)
        
        if enable_verbose_logs:
            print("\nISL DISTANCE STATISTICS")
            print(f"  > Min. distance.......... {min_distance:.2f} m ({min_distance/1000:.2f} km)")
            print(f"  > Max. distance.......... {max_distance:.2f} m ({max_distance/1000:.2f} km)")
            print(f"  > Average distance....... {avg_distance:.2f} m ({avg_distance/1000:.2f} km)")
            print(f"  > Median distance........ {median_distance:.2f} m ({median_distance/1000:.2f} km)")
            print(f"  > Std. deviation......... {std_distance:.2f} m ({std_distance/1000:.2f} km)")
        
        # 保存距離統計到檔案
        distance_stats_file = output_dynamic_state_dir + "/isl_distance_stats_" + str(time_since_epoch_ns) + ".txt"
        with open(distance_stats_file, "w+") as f_stats:
            f_stats.write("ISL Distance Statistics\n")
            f_stats.write("=" * 60 + "\n")
            f_stats.write(f"Time: {time_since_epoch_ns} ns ({time_since_epoch_ns / 1e9} seconds)\n")
            f_stats.write(f"Total ISLs: {len(list_isls)}\n")
            f_stats.write(f"Min distance: {min_distance:.2f} m ({min_distance/1000:.2f} km)\n")
            f_stats.write(f"Max distance: {max_distance:.2f} m ({max_distance/1000:.2f} km)\n")
            f_stats.write(f"Average distance: {avg_distance:.2f} m ({avg_distance/1000:.2f} km)\n")
            f_stats.write(f"Median distance: {median_distance:.2f} m ({median_distance/1000:.2f} km)\n")
            f_stats.write(f"Std deviation: {std_distance:.2f} m ({std_distance/1000:.2f} km)\n")
            f_stats.write("\nDetailed ISL distances:\n")
            for i, (a, b) in enumerate(list_isls):
                f_stats.write(f"ISL {a:3d}-{b:3d}: {isl_distances[i]:10.2f} m ({isl_distances[i]/1000:8.2f} km)\n")
    
    else:
        if enable_verbose_logs:
            print("  > Total ISLs............. 0 (no ISLs defined)")

    #################################

    if enable_verbose_logs:
        print("\nGSL INTERFACE INFORMATION")

    satellite_gsl_if_count_list = list(map(
        lambda x: x["number_of_interfaces"],
        list_gsl_interfaces_info[0:len(satellites)]
    ))
    ground_station_gsl_if_count_list = list(map(
        lambda x: x["number_of_interfaces"],
        list_gsl_interfaces_info[len(satellites):(len(satellites) + len(ground_stations))]
    ))
    if enable_verbose_logs:
        print("  > Min. GSL IFs/satellite........ " + str(np.min(satellite_gsl_if_count_list)))
        print("  > Max. GSL IFs/satellite........ " + str(np.max(satellite_gsl_if_count_list)))
        print("  > Min. GSL IFs/ground station... " + str(np.min(ground_station_gsl_if_count_list)))
        print("  > Max. GSL IFs/ground_station... " + str(np.max(ground_station_gsl_if_count_list)))

    #################################

    if enable_verbose_logs:
        print("\nGSL IN-RANGE INFORMATION")

    # What satellites can a ground station see
    ground_station_satellites_in_range = []
    for ground_station in ground_stations:
        # Find satellites in range
        satellites_in_range = []
        for sid in range(len(satellites)):
            distance_m = distance_m_ground_station_to_satellite(
                ground_station,
                satellites[sid],
                str(epoch),
                str(time)
            )
            if distance_m <= max_gsl_length_m:
                satellites_in_range.append((distance_m, sid))
                sat_net_graph_all_with_only_gsls.add_edge(
                    sid, len(satellites) + ground_station["gid"], weight=distance_m
                )

        ground_station_satellites_in_range.append(satellites_in_range)

    # Print how many are in range
    ground_station_num_in_range = list(map(lambda x: len(x), ground_station_satellites_in_range))
    if enable_verbose_logs:
        print("  > Min. satellites in range... " + str(np.min(ground_station_num_in_range)))
        print("  > Max. satellites in range... " + str(np.max(ground_station_num_in_range)))

    #################################

    #
    # Call the dynamic state algorithm which:
    #
    # (a) Output the gsl_if_bandwidth_<t>.txt files
    # (b) Output the fstate_<t>.txt files
    #
    if dynamic_state_algorithm == "algorithm_free_one_only_over_isls":

        return algorithm_free_one_only_over_isls(
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
        )

    elif dynamic_state_algorithm == "algorithm_free_gs_one_sat_many_only_over_isls":

        return algorithm_free_gs_one_sat_many_only_over_isls(
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
        )

    elif dynamic_state_algorithm == "algorithm_free_one_only_gs_relays":

        return algorithm_free_one_only_gs_relays(
            output_dynamic_state_dir,
            time_since_epoch_ns,
            satellites,
            ground_stations,
            sat_net_graph_all_with_only_gsls,
            num_isls_per_sat,
            list_gsl_interfaces_info,
            prev_output,
            enable_verbose_logs
        )

    elif dynamic_state_algorithm == "algorithm_paired_many_only_over_isls":

        return algorithm_paired_many_only_over_isls(
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
        )

    elif dynamic_state_algorithm == "algorithm_paired_one_only_over_isls":

        return algorithm_paired_one_only_over_isls(
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
        )

    elif dynamic_state_algorithm == "algorithm_lohi_routing":

        return algorithm_lohi_routing(
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
            num_sats_per_orbit
        )
    
    elif dynamic_state_algorithm == "algorithm_queue_aware_over_isls":
        
        return algorithm_queue_aware_over_isls(
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
            queue_stats_file,
            alpha,
            beta
        )

    else:
        raise ValueError("Unknown dynamic state algorithm: " + str(dynamic_state_algorithm))
