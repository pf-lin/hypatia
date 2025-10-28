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

# Core values
dynamic_state_update_interval_ms = 100                          # 100 millisecond update interval
simulation_end_time_s = 200                                     # 200 seconds
pingmesh_interval_ns = 1 * 1000 * 1000                          # A ping every 1ms
enable_isl_utilization_tracking = True                          # Enable utilization tracking
isl_utilization_tracking_interval_ns = 1 * 1000 * 1000 * 1000   # 1 second utilization intervals
enable_link_queue_tracking = True                               # Enable link queue tracking

# Derivatives
dynamic_state_update_interval_ns = dynamic_state_update_interval_ms * 1000 * 1000
simulation_end_time_ns = simulation_end_time_s * 1000 * 1000 * 1000
dynamic_state = "dynamic_state_" + str(dynamic_state_update_interval_ms) + "ms_for_" + str(simulation_end_time_s) + "s"

# Chosen pairs:
# > Paris (744) to Moscow (741)
# > Chicago (757) to Zhengzhou (807)
# > Chicago (757) to Lagos (736)
# > Los-Angeles-Long-Beach-Santa-Ana (740) to Shanghai (722)
full_satellite_network_isls = "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls"
chosen_pairs = [
    ("oneweb_1200_isls", 744, 741, "TcpNewReno", full_satellite_network_isls),
    ("oneweb_1200_isls", 744, 741, "TcpVegas", full_satellite_network_isls),
    ("oneweb_1200_isls", 757, 807, "TcpNewReno", full_satellite_network_isls),
    ("oneweb_1200_isls", 757, 807, "TcpVegas", full_satellite_network_isls),
    ("oneweb_1200_isls", 757, 736, "TcpNewReno", full_satellite_network_isls),
    ("oneweb_1200_isls", 757, 736, "TcpVegas", full_satellite_network_isls),
    ("oneweb_1200_isls", 740, 722, "TcpNewReno", full_satellite_network_isls),
    ("oneweb_1200_isls", 740, 722, "TcpVegas", full_satellite_network_isls),
]


def get_tcp_run_list():
    run_list = []
    for p in chosen_pairs:
        run_list += [
            {
                "name": p[0] + "_" + str(p[1]) + "_to_" + str(p[2]) + "_with_" + p[3] + "_at_10_Mbps",
                "satellite_network": p[4],
                "dynamic_state": dynamic_state,
                "dynamic_state_update_interval_ns": dynamic_state_update_interval_ns,
                "simulation_end_time_ns": simulation_end_time_ns,
                "data_rate_megabit_per_s": 10.0,
                "queue_size_pkt": 100,
                "enable_isl_utilization_tracking": enable_isl_utilization_tracking,
                "isl_utilization_tracking_interval_ns": isl_utilization_tracking_interval_ns,
                "enable_link_queue_tracking": enable_link_queue_tracking,
                "from_id": p[1],
                "to_id": p[2],
                "tcp_socket_type": p[3],
            },
        ]

    return run_list


def get_pings_run_list():

    # TCP transport protocol does not matter for the ping run
    reduced_chosen_pairs = []
    for p in chosen_pairs:
        if not (p[0], p[1], p[2], p[4]) in reduced_chosen_pairs:
            reduced_chosen_pairs.append((p[0], p[1], p[2], p[4]))  # Stripped out p[3] = transport protocol

    run_list = []
    for p in reduced_chosen_pairs:
        run_list += [
            {
                "name": p[0] + "_" + str(p[1]) + "_to_" + str(p[2]) + "_pings",
                "satellite_network": p[3],
                "dynamic_state": dynamic_state,
                "dynamic_state_update_interval_ns": dynamic_state_update_interval_ns,
                "simulation_end_time_ns": simulation_end_time_ns,
                "data_rate_megabit_per_s": 10000.0,
                "queue_size_pkt": 100000,
                "enable_isl_utilization_tracking": enable_isl_utilization_tracking,
                "isl_utilization_tracking_interval_ns": isl_utilization_tracking_interval_ns,
                "enable_link_queue_tracking": enable_link_queue_tracking,
                "from_id": p[1],
                "to_id": p[2],
                "pingmesh_interval_ns": pingmesh_interval_ns,
            }
        ]

    return run_list
