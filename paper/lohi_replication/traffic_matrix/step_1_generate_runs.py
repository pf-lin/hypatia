# Generates run directories for the dynamic traffic matrix experiment.
# Mirrors paper/ns3_experiments/traffic_matrix/step_1_generate_runs.py but
# adapted for the dynamic (closed-loop) routing architecture from
# paper/lohi_replication/a_b.

import exputil
import networkload
import random
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__)))
from dynamic_run_list import get_tm_dynamic_run_list

# [修改] 直接引入 satgenpy 套件，用於在 step_1 計算衝突衛星（不依賴 networkx_path 檔案）
sys.path.append("/home/pflin/research/hypatia-pf/satgenpy")
from satgen.dynamic_state.generate_dynamic_state import generate_dynamic_state_at
from satgen.isls import read_isls
from satgen.ground_stations import read_ground_stations_extended
from satgen.tles import read_tles
from satgen.interfaces import read_gsl_interfaces_info
from satgen.post_analysis.graph_tools import get_path

local_shell = exputil.LocalShell()

# [修改] 將原本的兩個函式合併為一個統一的函式：
# 1. 先算出所有 time step 的 fstate（只跑一次，所有 pair 共用）
# 2. 從中找出 focus pair 的衝突衛星集合
# 3. 再用同一份 fstate 批次判斷所有 pair 是否衝突
# 總計只需跑 1 次全程 fstate，而非 (1 + N_pairs) 次

def compute_all_fstates(satellite_network_dir, simulation_end_time_ns,
                        dynamic_state_update_interval_ns, algorithm):
    """
    對整個模擬時間跑一次 fstate 計算，回傳每個 time step 的 fstate dict 列表。
    fstate[t] = { (src, dst): next_hop }
    """
    print("  > [step_1] Computing all fstates (one-time, shared across all pairs)...")

    ground_stations = read_ground_stations_extended(
        os.path.join(satellite_network_dir, "ground_stations.txt"))
    tles = read_tles(os.path.join(satellite_network_dir, "tles.txt"))
    satellites = tles["satellites"]
    epoch = tles["epoch"]
    list_isls = read_isls(
        os.path.join(satellite_network_dir, "isls.txt"), len(satellites))
    list_gsl_interfaces_info = read_gsl_interfaces_info(
        os.path.join(satellite_network_dir, "gsl_interfaces_info.txt"),
        len(satellites), len(ground_stations))

    import exputil as _eu
    desc = _eu.PropertiesConfig(os.path.join(satellite_network_dir, "description.txt"))
    max_gsl_length_m = float(desc.get_property_or_fail("max_gsl_length_m"))
    max_isl_length_m = float(desc.get_property_or_fail("max_isl_length_m"))

    import tempfile
    time_steps = list(range(0, simulation_end_time_ns, dynamic_state_update_interval_ns))
    fstates_by_step = []   # fstates_by_step[i] = fstate dict at time_steps[i]

    with tempfile.TemporaryDirectory() as tmp_dir:
        prev_output = None
        accumulated_fstate = {}   # fstate 是累積更新的（與 run_dynamic_routing.py 相同）

        for i, t in enumerate(time_steps):
            output = generate_dynamic_state_at(
                tmp_dir, epoch, t, satellites, ground_stations,
                list_isls, list_gsl_interfaces_info,
                max_gsl_length_m, max_isl_length_m,
                algorithm, prev_output,
                True, None, None, None, 0.7, 0.3, dynamic_state_update_interval_ns
            )
            prev_output = output

            fstate_file = os.path.join(tmp_dir, "fstate_%d.txt" % t)
            if os.path.exists(fstate_file):
                with open(fstate_file, "r") as f_in:
                    for line in f_in:
                        spl = line.strip().split(",")
                        accumulated_fstate[(int(spl[0]), int(spl[1]))] = int(spl[2])

            # 存當前時刻的快照（shallow copy 即可，因為 key 不會被刪除）
            fstates_by_step.append(dict(accumulated_fstate))

            if (i + 1) % 200 == 0:
                print("[%d/%d] t=%.1f s" % (i + 1, len(time_steps), t / 1e9))

    print("  > [step_1] Done. %d fstate snapshots computed." % len(fstates_by_step))
    return fstates_by_step


def find_conflicts_from_fstates(fstates_by_step, src, dst):
    """
    從已計算好的 fstates_by_step 中，找出 src→dst 在所有 time step 的第一跳/最後跳衛星。
    """
    satellite_conflicts_set = set()
    for fstate in fstates_by_step:
        path = get_path(src, dst, fstate)
        if path is not None and len(path) >= 3:
            satellite_conflicts_set.add(path[1])
            satellite_conflicts_set.add(path[-2])
    print("  > [step_2] Focus pair %d→%d: %d conflicting satellites: %s" % (
        src, dst, len(satellite_conflicts_set), sorted(satellite_conflicts_set)))
    return satellite_conflicts_set


def batch_check_conflicts(pairs, fstates_by_step, satellite_conflicts):
    """
    對所有 pairs，用已計算好的 fstates_by_step 批次判斷是否有衝突。
    只要任一 time step 的第一跳/最後跳在 satellite_conflicts 中即視為衝突。
    回傳 (non_conflicting, conflicting) 兩個 list。
    """
    non_conflicting = []
    conflicting = []
    for idx, p in enumerate(pairs):
        conflict = False
        for fstate in fstates_by_step:
            path = get_path(p[0], p[1], fstate)
            if path is not None and len(path) >= 3:
                if path[1] in satellite_conflicts or path[-2] in satellite_conflicts:
                    conflict = True
                    break   # 提早結束這個 pair 的檢查
        if conflict:
            conflicting.append(p)
        else:
            non_conflicting.append(p)
        if (idx + 1) % 10 == 0:
            print("    Checked %d/%d pairs..." % (idx + 1, len(pairs)))
    return non_conflicting, conflicting


# ---------------------------------------------------------------------------
# [修改] 預先計算 fstates，避免重複計算
# 只有 specific 模式才需要，且每個 satellite_network 只計算一次
# ---------------------------------------------------------------------------
precomputed_fstates = {}   # key: (satellite_network_dir, algorithm)

for run in get_tm_dynamic_run_list():

    traffic_mode = run["traffic_mode"]
    movement = run["movement"]
    run_name = run["name"]
    dynamic_state_algorithm = run["dynamic_state_algorithm"]

    satellite_network_dir = os.path.join(
        "/home/pflin/research/hypatia-pf/paper/satellite_networks_state/gen_data",
        run["satellite_network"]
    )

    # Prepare run directory (algorithm sub-folder, same as lohi_replication/a_b)
    run_dir = "runs/%s/%s" % (run_name, dynamic_state_algorithm)
    local_shell.remove_force_recursive(run_dir)
    local_shell.make_full_dir(run_dir)

    # config_ns3.properties from template
    local_shell.copy_file("templates/template_config_ns3.properties", run_dir + "/config_ns3.properties")
    local_shell.sed_replace_in_file_plain(run_dir + "/config_ns3.properties",
                                          "[DYNAMIC-STATE]", str(run["dynamic_state"]))
    local_shell.sed_replace_in_file_plain(run_dir + "/config_ns3.properties",
                                          "[SATELLITE-NETWORK]", str(run["satellite_network"]))
    local_shell.sed_replace_in_file_plain(run_dir + "/config_ns3.properties",
                                          "[DYNAMIC-STATE-ALGORITHM]", str(run["dynamic_state_algorithm"]))
    local_shell.sed_replace_in_file_plain(run_dir + "/config_ns3.properties",
                                          "[DYNAMIC-STATE-UPDATE-INTERVAL-NS]", str(run["dynamic_state_update_interval_ns"]))
    local_shell.sed_replace_in_file_plain(run_dir + "/config_ns3.properties",
                                          "[SIMULATION-END-TIME-NS]", str(run["simulation_end_time_ns"]))
    local_shell.sed_replace_in_file_plain(run_dir + "/config_ns3.properties",
                                          "[ISL-DATA-RATE-MEGABIT-PER-S]", str(run["data_rate_megabit_per_s"]))
    local_shell.sed_replace_in_file_plain(run_dir + "/config_ns3.properties",
                                          "[GSL-DATA-RATE-MEGABIT-PER-S]", str(run["data_rate_megabit_per_s"]))
    local_shell.sed_replace_in_file_plain(run_dir + "/config_ns3.properties",
                                          "[ISL-MAX-QUEUE-SIZE-PKTS]", str(run["queue_size_pkt"]))
    local_shell.sed_replace_in_file_plain(run_dir + "/config_ns3.properties",
                                          "[GSL-MAX-QUEUE-SIZE-PKTS]", str(run["queue_size_pkt"]))
    local_shell.sed_replace_in_file_plain(run_dir + "/config_ns3.properties",
                                          "[ENABLE-ISL-UTILIZATION-TRACKING]",
                                          "true" if run["enable_isl_utilization_tracking"] else "false")
    if run["enable_isl_utilization_tracking"]:
        local_shell.sed_replace_in_file_plain(
            run_dir + "/config_ns3.properties",
            "[ISL-UTILIZATION-TRACKING-INTERVAL-NS-COMPLETE]",
            "isl_utilization_tracking_interval_ns=" + str(run["isl_utilization_tracking_interval_ns"])
        )
    else:
        local_shell.sed_replace_in_file_plain(run_dir + "/config_ns3.properties",
                                              "[ISL-UTILIZATION-TRACKING-INTERVAL-NS-COMPLETE]", "")
    local_shell.sed_replace_in_file_plain(run_dir + "/config_ns3.properties",
                                          "[ENABLE-LINK-QUEUE-TRACKING]",
                                          "true" if run["enable_link_queue_tracking"] else "false")

    # Make sub-directories needed at runtime
    local_shell.make_full_dir(run_dir + "/logs_ns3")
    local_shell.make_full_dir(run_dir + "/dynamic_state")
    local_shell.make_full_dir(run_dir + "/queue_stats")
    local_shell.make_full_dir(run_dir + "/prev_output_cache")

    # .gitignore
    local_shell.write_file(run_dir + "/.gitignore", "logs_ns3\ndynamic_state\nqueue_stats\nprev_output_cache")

    # =====================================================================
    # Generate the traffic schedule  (same logic as ns3_experiments/traffic_matrix)
    # =====================================================================

    if traffic_mode == "specific":

        # Create the initial random reciprocal pairing with already one pair known (738, 793)
        random.seed(123456789)
        random.randint(0, 100000000)  # Legacy reasons
        seed_from_to = random.randint(0, 100000000)
        a = set(range(720, 820))
        a.remove(738)
        a.remove(793)
        initial_list_from_to = [(738, 793), (793, 738)]
        initial_list_from_to = initial_list_from_to + networkload.generate_from_to_reciprocated_random_pairing(
            list(a),
            seed_from_to
        )

        static_state_algorithm = "algorithm_free_one_only_over_isls"
        cache_key = (satellite_network_dir, static_state_algorithm)

        # [修改] 只有第一次才計算，後續 run 直接重用
        if cache_key not in precomputed_fstates:
            precomputed_fstates[cache_key] = compute_all_fstates(
                satellite_network_dir=satellite_network_dir,
                simulation_end_time_ns=run["simulation_end_time_ns"],
                dynamic_state_update_interval_ns=run["dynamic_state_update_interval_ns"],
                algorithm=static_state_algorithm
            )
        fstates_by_step = precomputed_fstates[cache_key]

        # focus pair 的衝突衛星
        satellite_conflicts = find_conflicts_from_fstates(
            fstates_by_step, run["src_node_id"], run["dst_node_id"])

        # 批次判斷所有 pair
        extra_non_conflicting, conflicting_pairs = batch_check_conflicts(
            initial_list_from_to[2:], fstates_by_step, satellite_conflicts)
        non_conflicting_pairs = [(738, 793), (793, 738)] + extra_non_conflicting

        print("  > Specific mode: %d non-conflicting, %d conflicting" % (
            len(non_conflicting_pairs), len(conflicting_pairs)))

        list_from_to = non_conflicting_pairs

    elif traffic_mode == "general":

        random.seed(123456789)
        random.randint(0, 100000000)  # Legacy reasons
        seed_from_to = random.randint(0, 100000000)
        a = set(range(720, 820))
        a.remove(738)
        a.remove(793)
        list_from_to = [(738, 793), (793, 738)]
        list_from_to = list_from_to + networkload.generate_from_to_reciprocated_random_pairing(
            list(a),
            seed_from_to
        )

    else:
        raise ValueError("Unknown traffic mode: " + traffic_mode)

    # Write the schedule into the algorithm sub-folder
    networkload.write_schedule(
        run_dir + "/schedule_oneweb_1200.csv",
        len(list_from_to),
        list_from_to,
        [1000000000000] * len(list_from_to),
        [0] * len(list_from_to)
    )

    print("Generated run: %s  (%d flows)" % (run_dir, len(list_from_to)))

print("\nSuccess")