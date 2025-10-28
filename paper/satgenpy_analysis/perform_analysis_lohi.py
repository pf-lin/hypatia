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

import exputil
import time

local_shell = exputil.LocalShell()
max_num_processes = 6

# Check that no screen is running
if local_shell.count_screens() != 0:
    print(
        "There is a screen already running. "
        "Please kill all screens before running this analysis script (killall screen)."
    )
    exit(1)

# # Re-create data directory
# local_shell.remove_force_recursive("lohi_data")
# local_shell.make_full_dir("lohi_data")
# local_shell.make_full_dir("lohi_data/command_logs")

# Where to store all commands
commands_to_run = []

# # 6x12 constellation with algorithm_free_one_only_over_isls
# print("Generating commands for 6x12 constellation with algorithm_free_one_only_over_isls...")

# # Test route 1: Ground station 108 to 109 (first two ground stations after satellites)
# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "6x12_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls "
#     "100 200 108 109 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_6x12_isls_108_to_109.log 2>&1"
# )

# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "6x12_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls "
#     "100 200 108 109 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_6x12_isls_108_to_109.log 2>&1"
# )

# # Test route 2: Ground station 110 to 115 (medium distance)
# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "6x12_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls "
#     "100 200 110 115 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_6x12_isls_110_to_115.log 2>&1"
# )

# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "6x12_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls "
#     "100 200 110 115 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_6x12_isls_110_to_115.log 2>&1"
# )

# # 6x12 constellation with LOHI routing - test routes
# print("Generating commands for 6x12 constellation with LOHI routing...")

# # Test route 1: Ground station 108 to 109 (first two ground stations after satellites)
# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "6x12_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing "
#     "100 200 108 109 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_6x12_lohi_108_to_109.log 2>&1"
# )

# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "6x12_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing "
#     "100 200 108 109 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_6x12_lohi_108_to_109.log 2>&1"
# )

# # Test route 2: Ground station 110 to 115 (medium distance)
# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "6x12_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing "
#     "100 200 110 115 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_6x12_lohi_110_to_115.log 2>&1"
# )

# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "6x12_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing "
#     "100 200 110 115 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_6x12_lohi_110_to_115.log 2>&1"
# )

# # 6x18 constellation with LOHI routing - test routes
# print("Generating commands for 6x18 constellation with LOHI routing...")

# # Test route 1: Ground station 108 to 109 (first two ground stations after satellites)
# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "6x18_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing "
#     "100 200 108 109 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_6x18_lohi_108_to_109.log 2>&1"
# )

# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "6x18_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing "
#     "100 200 108 109 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_6x18_lohi_108_to_109.log 2>&1"
# )

# # Test route 2: Ground station 110 to 115 (medium distance)
# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "6x18_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing "
#     "100 200 110 115 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_6x18_lohi_110_to_115.log 2>&1"
# )

# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "6x18_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing "
#     "100 200 110 115 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_6x18_lohi_110_to_115.log 2>&1"
# )

# # OneWeb 1200 constellation with LOHI routing
# print("Generating commands for OneWeb 1200 constellation with LOHI routing...")

# # Major international routes similar to existing analysis
# # Paris (744 equivalent) to Moscow (741 equivalent) for OneWeb numbering
# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing "
#     "100 200 744 741 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_oneweb_lohi_744_to_741.log 2>&1"
# )

# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing "
#     "100 200 744 741 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_oneweb_lohi_744_to_741.log 2>&1"
# )

# # Chicago to Zhengzhou route for OneWeb
# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing "
#     "100 200 757 807 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_oneweb_lohi_757_to_807.log 2>&1"
# )

# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing "
#     "100 200 757 807 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_oneweb_lohi_757_to_807.log 2>&1"
# )

# OneWeb 1200 constellation with algorithm_free_one_only_over_isls
print("Generating commands for OneWeb 1200 constellation with algorithm_free_one_only_over_isls...")

# Major international routes similar to existing analysis
# Paris (744 equivalent) to Moscow (741 equivalent) for OneWeb numbering
commands_to_run.append(
    "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
    "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
    "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls "
    "100 200 744 741 "
    "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_oneweb_isls_744_to_741.log 2>&1"
)

commands_to_run.append(
    "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
    "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
    "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls "
    "100 200 744 741 "
    "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_oneweb_isls_744_to_741.log 2>&1"
)

# Chicago (757) to Zhengzhou (807) route for OneWeb
commands_to_run.append(
    "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
    "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
    "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls "
    "100 200 757 807 "
    "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_oneweb_isls_757_to_807.log 2>&1"
)

commands_to_run.append(
    "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
    "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
    "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls "
    "100 200 757 807 "
    "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_oneweb_isls_757_to_807.log 2>&1"
)

# Chicago (757) to Lagos (736) route for OneWeb
commands_to_run.append(
    "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
    "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
    "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls "
    "100 200 757 736 "
    "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_oneweb_isls_757_to_736.log 2>&1"
)

commands_to_run.append(
    "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
    "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
    "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls "
    "100 200 757 736 "
    "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_oneweb_isls_757_to_736.log 2>&1"
)

# Los-Angeles-Long-Beach-Santa-Ana (740) to Shanghai (722) route for OneWeb
commands_to_run.append(
    "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
    "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
    "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls "
    "100 200 740 722 "
    "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_oneweb_isls_740_to_722.log 2>&1"
)

commands_to_run.append(
    "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
    "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
    "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls "
    "100 200 740 722 "
    "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_oneweb_isls_740_to_722.log 2>&1"
)

# # OneWeb 1200 constellation with algorithm_paired_one_only_over_isls
# print("Generating commands for OneWeb 1200 constellation with algorithm_paired_one_only_over_isls...")

# # Major international routes similar to existing analysis
# # Paris (744 equivalent) to Moscow (741 equivalent) for OneWeb numbering
# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_paired_one_only_over_isls "
#     "100 200 744 741 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_oneweb_paired_744_to_741.log 2>&1"
# )

# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_paired_one_only_over_isls "
#     "100 200 744 741 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_oneweb_paired_744_to_741.log 2>&1"
# )

# # Chicago (757) to Zhengzhou (807) route for OneWeb
# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_paired_one_only_over_isls "
#     "100 200 757 807 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_oneweb_paired_757_to_807.log 2>&1"
# )

# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_paired_one_only_over_isls "
#     "100 200 757 807 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_oneweb_paired_757_to_807.log 2>&1"
# )

# # Chicago (757) to Lagos (736) route for OneWeb
# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_paired_one_only_over_isls "
#     "100 200 757 736 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_oneweb_paired_757_to_736.log 2>&1"
# )

# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_paired_one_only_over_isls "
#     "100 200 757 736 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_oneweb_paired_757_to_736.log 2>&1"
# )

# # Los-Angeles-Long-Beach-Santa-Ana (740) to Shanghai (722) route for OneWeb
# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_paired_one_only_over_isls "
#     "100 200 740 722 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_oneweb_paired_740_to_722.log 2>&1"
# )

# commands_to_run.append(
#     "cd ../../satgenpy; python -m satgen.post_analysis.main_print_graphical_routes_and_rtt "
#     "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/"
#     "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_paired_one_only_over_isls "
#     "100 200 740 722 "
#     "> ../paper/satgenpy_analysis/lohi_data/command_logs/manual_graphical_oneweb_paired_740_to_722.log 2>&1"
# )

# Constellation comparison
print("Generating commands for constellation comparison...")
for satgenpy_generated_constellation in [
    # "6x12_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls",
    # "6x12_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing",
    # "6x18_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing",
    "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls",
    # "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_paired_one_only_over_isls",
    # "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_lohi_routing",
]:
    for duration_s in [200]:
        list_update_interval_ms = [50, 100, 1000]

        # Path
        for update_interval_ms in list_update_interval_ms:
            commands_to_run.append(
                "cd ../../satgenpy; "
                "python -m satgen.post_analysis.main_analyze_path "
                "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/%s %d %d "
                "> ../paper/satgenpy_analysis/lohi_data/command_logs/constellation_comp_path_%s_%dms_for_%ds.log "
                "2>&1"
                % (
                    satgenpy_generated_constellation,
                    update_interval_ms,
                    duration_s,
                    satgenpy_generated_constellation,
                    update_interval_ms,
                    duration_s,
                )
            )

        # RTT
        for update_interval_ms in list_update_interval_ms:
            commands_to_run.append(
                "cd ../../satgenpy; "
                "python -m satgen.post_analysis.main_analyze_rtt "
                "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/%s %d %d "
                "> ../paper/satgenpy_analysis/lohi_data/command_logs/constellation_comp_rtt_%s_%dms_for_%ds.log "
                "2>&1"
                % (
                    satgenpy_generated_constellation,
                    update_interval_ms,
                    duration_s,
                    satgenpy_generated_constellation,
                    update_interval_ms,
                    duration_s,
                )
            )

        # Time step path
        commands_to_run.append(
            "cd ../../satgenpy; "
            "python -m satgen.post_analysis.main_analyze_time_step_path "
            "../paper/satgenpy_analysis/lohi_data ../paper/satellite_networks_state/gen_data/%s %s %d "
            "> ../paper/satgenpy_analysis/lohi_data/command_logs/constellation_comp_time_step_path_%s_%ds.log "
            "2>&1"
            % (
                satgenpy_generated_constellation,
                ",".join(list(map(lambda x: str(x), list_update_interval_ms))),
                duration_s,
                satgenpy_generated_constellation,
                duration_s,
            )
        )

# Run the commands
print("Running commands (at most %d in parallel)..." % max_num_processes)
for i in range(len(commands_to_run)):
    print(
        "Starting command %d out of %d: %s"
        % (i + 1, len(commands_to_run), commands_to_run[i])
    )
    local_shell.detached_exec(commands_to_run[i])
    while local_shell.count_screens() >= max_num_processes:
        time.sleep(2)

# Awaiting final completion before exiting
print("Waiting completion of the last %d..." % max_num_processes)
while local_shell.count_screens() > 0:
    time.sleep(2)
print("Finished.")
