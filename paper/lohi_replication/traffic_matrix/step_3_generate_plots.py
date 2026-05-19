# Analysis and plotting for the dynamic traffic-matrix experiment.
# Mirrors paper/ns3_experiments/traffic_matrix/step_3_generate_plots.py but
# reads routes from the dynamic_state fstate files instead of pre-computed
# networkx_path files.

import os
import sys
import shutil
import subprocess
import tempfile
import argparse
import numpy as np
from datetime import datetime

# [新增] 導入繪圖所需套件
import numpy as np
import matplotlib
matplotlib.use("Agg")   # 非互動式後端，避免在無顯示器環境出錯
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature
from matplotlib.lines import Line2D
import astropy.units as u

sys.path.append("/home/pflin/research/hypatia-pf/satgenpy")
sys.path.append(os.path.join(os.path.dirname(__file__)))
from dynamic_run_list import (
    add_traffic_mode_argument,
    describe_traffic_mode_selection,
    get_tm_dynamic_run_list,
)

import exputil

# ---------------------------------------------------------------------------
# Logging helper: write stdout/stderr to both terminal and file
# ---------------------------------------------------------------------------
class TeeLogger:
    def __init__(self, original_stream, log_fp):
        self.original_stream = original_stream
        self.log_fp = log_fp

    def write(self, data):
        self.original_stream.write(data)
        self.log_fp.write(data)

    def flush(self):
        self.original_stream.flush()
        self.log_fp.flush()


def setup_logging(log_file_path):
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
    log_fp = open(log_file_path, "w", buffering=1)  # line-buffered
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = TeeLogger(original_stdout, log_fp)
    sys.stderr = TeeLogger(original_stderr, log_fp)
    return original_stdout, original_stderr, log_fp


def restore_logging(original_stdout, original_stderr, log_fp):
    sys.stdout = original_stdout
    sys.stderr = original_stderr
    log_fp.close()


def find_missing_analysis_inputs(run_dir, dynamic_state_algorithm):
    algorithm_run_dir = os.path.join(run_dir, dynamic_state_algorithm)
    required_paths = [
        algorithm_run_dir,
        os.path.join(algorithm_run_dir, "dynamic_state", "fstate_0.txt"),
        os.path.join(algorithm_run_dir, "logs_ns3", "isl_utilization.csv"),
    ]
    return [path for path in required_paths if not os.path.exists(path)]

# ---------------------------------------------------------------------------
# gnuplot template (same style as lohi_replication/a_b/analysis_dynamic_result.py)
# ---------------------------------------------------------------------------
PLOT_TEMPLATE = """\
set terminal pdfcairo font "Helvetica,18" linewidth 1.5 rounded dashed
set style line 80 lt rgb "#808080"
set style line 81 lt 0
set style line 81 lt rgb "#999999"
set grid back linestyle 81
set border 3 back linestyle 80
set xtics nomirror
set ytics nomirror
set style line 1 lt rgb "#2177b0" lw 2.0 pt 1 ps 0
set output "[OUTPUT-FILE]"
set xlabel "Time (s)"
set ylabel "Max ISL utilization on path (ratio)"
set xrange [0:200]
set yrange [0:1]
set key off
set datafile separator ","
plot "[DATA-FILE]" using ($1/1e9):2 title "" w l ls 1
"""

# [新增] RTT 圖表模板（參考 analysis_dynamic_result.py 的 plot_script_template）
PLOT_RTT_TEMPLATE = """\
set terminal pdfcairo font "Helvetica,24" linewidth 1.5 rounded dashed
set style line 80 lt rgb "#808080"
set style line 81 lt 0
set style line 81 lt rgb "#999999"
set grid back linestyle 81
set border 3 back linestyle 80
set xtics nomirror
set ytics nomirror
set style line 1 lt rgb "#2177b0" lw 2.4 pt 1 ps 0
set output "[OUTPUT-FILE]"
set xlabel "Time (s)"
set ylabel "NetworkX RTT (ms)"
set xrange [0:]
set yrange [0:]
set key off
set datafile separator ","
plot "[DATA-FILE]" using ($1/1000000000):($2/1000000) title "" w lp ls 1
"""


def _run_gnuplot(plot_script_str):
    """Write a temp .plt file and execute gnuplot."""
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".plt", delete=False) as tf:
            tf.write(plot_script_str)
            tmp = tf.name
        result = subprocess.run(["gnuplot", tmp], capture_output=True, text=True)
        if result.returncode != 0:
            print("gnuplot error: %s" % result.stderr)
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


# ---------------------------------------------------------------------------
# [新增] networkx_path 與 networkx_rtt 產生函式
# 參考 analysis_dynamic_result.py 的 print_routes_and_rtt_for_dynamic_run
# 在 dynamic closed-loop simulation 跑完後，讀取所有 fstate_*.txt 來產生
# ---------------------------------------------------------------------------
def generate_networkx_path_and_rtt(
    algorithm_run_dir,
    satellite_network_dir,
    src_node_id,
    dst_node_id,
    dynamic_state_update_interval_ns,
    simulation_end_time_ns,
    data_dir,
    pdf_dir,
):
    """
    讀取 dynamic_state/ 下所有 fstate_*.txt，
    產生 networkx_path_{src}_to_{dst}.txt 與 networkx_rtt_{src}_to_{dst}.txt，
    並繪製 RTT 圖表。

    參考 lohi_replication/a_b/analysis_dynamic_result.py 的實作。
    """
    from satgen.post_analysis.graph_tools import get_path, compute_path_length_without_graph
    from satgen.isls import read_isls
    from satgen.ground_stations import read_ground_stations_extended
    from satgen.tles import read_tles
    import exputil

    print("  > [networkx] Loading satellite network from: %s" % satellite_network_dir)

    # 讀取衛星網路基本資料
    ground_stations = read_ground_stations_extended(
        os.path.join(satellite_network_dir, "ground_stations.txt"))
    tles = read_tles(os.path.join(satellite_network_dir, "tles.txt"))
    satellites = tles["satellites"]
    list_isls = read_isls(
        os.path.join(satellite_network_dir, "isls.txt"), len(satellites))
    epoch = tles["epoch"]

    description = exputil.PropertiesConfig(
        os.path.join(satellite_network_dir, "description.txt"))
    max_gsl_length_m = exputil.parse_positive_float(
        description.get_property_or_fail("max_gsl_length_m"))
    max_isl_length_m = exputil.parse_positive_float(
        description.get_property_or_fail("max_isl_length_m"))

    dynamic_state_dir = os.path.join(algorithm_run_dir, "dynamic_state")

    # 輸出檔案路徑
    path_filename = os.path.join(data_dir, "networkx_path_%d_to_%d.txt" % (src_node_id, dst_node_id))
    rtt_filename = os.path.join(data_dir, "networkx_rtt_%d_to_%d.txt" % (src_node_id, dst_node_id))
    pdf_rtt_filename = os.path.join(pdf_dir, "time_vs_networkx_rtt_%d_to_%d.pdf" % (src_node_id, dst_node_id))

    fstate = {}
    current_path = []
    rtt_ns_list = []
    path_change = 0

    print("  > [networkx] Iterating fstate files t=0 to t=%d ns..." % simulation_end_time_ns)

    with open(path_filename, "w") as f_path:
        for t in range(0, simulation_end_time_ns, dynamic_state_update_interval_ns):
            fstate_file = os.path.join(dynamic_state_dir, "fstate_%d.txt" % t)
            if not os.path.exists(fstate_file):
                print("    Warning: %s not found, skipping" % fstate_file)
                continue

            # 載入 fstate（累積更新，與 analysis_dynamic_result.py 相同做法）
            with open(fstate_file, "r") as f_in:
                for line in f_in:
                    spl = line.strip().split(",")
                    fstate[(int(spl[0]), int(spl[1]))] = int(spl[2])

            # 計算雙向路徑長度與 RTT
            path_there = get_path(src_node_id, dst_node_id, fstate)
            path_back = get_path(dst_node_id, src_node_id, fstate)

            if path_there is not None and path_back is not None:
                length_src_to_dst_m = compute_path_length_without_graph(
                    path_there, epoch, t, satellites,
                    ground_stations, list_isls,
                    max_gsl_length_m, max_isl_length_m)
                length_dst_to_src_m = compute_path_length_without_graph(
                    path_back, epoch, t, satellites,
                    ground_stations, list_isls,
                    max_gsl_length_m, max_isl_length_m)
                rtt_ns = (length_src_to_dst_m + length_dst_to_src_m) * 1e9 / 299792458.0
            else:
                rtt_ns = 0.0
                path_there = None

            rtt_ns_list.append((t, rtt_ns))

            # 只有路徑變化時才寫入 path 檔案（與 analysis_dynamic_result.py 相同）
            new_path = path_there
            if current_path != new_path:
                current_path = new_path
                path_str = ("-".join(map(str, current_path))
                            if current_path else "Unreachable")
                f_path.write("%d,%s\n" % (t, path_str))
                print("    Path change at t=%.1f s → %s  (RTT=%.2f ms)" % (
                    t / 1e9, path_str, rtt_ns / 1e6))
                path_change += 1
    
    print("  > [networkx] Total path changes: %d" % path_change)

    # 寫入 RTT 資料
    with open(rtt_filename, "w") as f_rtt:
        for t, rtt_ns in rtt_ns_list:
            f_rtt.write("%d,%.10f\n" % (t, rtt_ns))

    print("  > [networkx] Written: %s" % path_filename)
    print("  > [networkx] Written: %s" % rtt_filename)

    # 繪製 RTT 圖表
    script = PLOT_RTT_TEMPLATE.replace("[DATA-FILE]", rtt_filename).replace(
        "[OUTPUT-FILE]", pdf_rtt_filename)
    _run_gnuplot(script)
    print("  > [networkx] RTT PDF → %s" % pdf_rtt_filename)


def _plot_connection_with_dateline_handling(ax, from_lon, from_lat, to_lon, to_lat, n=50, **kwargs):
    """處理跨日期變更線的連線繪製（與 analysis_dynamic_result.py 完全相同）"""
    def norm(arr):
        a = np.array(arr, dtype=float)
        return ((a + 180) % 360) - 180

    from_lon = float(norm(from_lon))
    to_lon   = float(norm(to_lon))

    d = to_lon - from_lon
    if d > 180:
        to_lon -= 360
    elif d < -180:
        to_lon += 360

    lon_cont = np.linspace(from_lon, to_lon, n)
    lat_cont = np.linspace(from_lat, to_lat, n)
    lon_plot = norm(lon_cont)

    diffs = np.abs(np.diff(lon_plot))
    split_positions = np.where(diffs > 180)[0] + 1

    if split_positions.size == 0:
        ax.plot(lon_plot, lat_cont, **kwargs)
    else:
        lon_segs = np.split(lon_plot, split_positions)
        lat_segs = np.split(lat_cont, split_positions)
        for lon_seg, lat_seg in zip(lon_segs, lat_segs):
            if len(lon_seg) >= 2:
                ax.plot(lon_seg, lat_seg, **kwargs)


def generate_graphical_routes(
    algorithm_run_dir,
    satellite_network_dir,
    src_node_id,
    dst_node_id,
    dynamic_state_update_interval_ns,
    simulation_end_time_ns,
    pdf_dir,
):
    """
    對每個路徑變化時刻產生一張世界地圖 PDF，
    標示出衛星、地面站與當前路徑。
    移植自 analysis_dynamic_result.py 的 print_graphical_routes_and_rtt_for_dynamic_run。
    """
    from satgen.post_analysis.graph_tools import (
        get_path,
        compute_path_length_without_graph,
        create_basic_ground_station_for_satellite_shadow,
    )
    from satgen.isls import read_isls
    from satgen.ground_stations import read_ground_stations_extended
    from satgen.tles import read_tles

    print("  > [graphic] Loading satellite network from: %s" % satellite_network_dir)

    ground_stations = read_ground_stations_extended(
        os.path.join(satellite_network_dir, "ground_stations.txt"))
    tles = read_tles(os.path.join(satellite_network_dir, "tles.txt"))
    satellites  = tles["satellites"]
    list_isls   = read_isls(os.path.join(satellite_network_dir, "isls.txt"), len(satellites))
    epoch       = tles["epoch"]

    import exputil as _eu
    desc = _eu.PropertiesConfig(os.path.join(satellite_network_dir, "description.txt"))
    max_gsl_length_m = _eu.parse_positive_float(desc.get_property_or_fail("max_gsl_length_m"))
    max_isl_length_m = _eu.parse_positive_float(desc.get_property_or_fail("max_isl_length_m"))

    dynamic_state_dir = os.path.join(algorithm_run_dir, "dynamic_state")

    # [新增] 在 pdf/[run_name]/[dynamic_state_algorithm] 底下建立專用資料夾
    graphics_dir = os.path.join(pdf_dir, "graphical_routes")
    os.makedirs(graphics_dir, exist_ok=True)

    # 顏色常數（與 analysis_dynamic_result.py 相同）
    GS_USED_COLOR        = "#3b3b3b"
    GS_UNUSED_COLOR      = "black"
    SAT_USED_COLOR       = "#a61111"
    SAT_UNUSED_COLOR     = "red"
    ISL_COLOR            = "#eb6b38"

    fstate       = {}
    current_path = []

    print("  > [graphic] Iterating fstate files t=0 to t=%d ns..." % simulation_end_time_ns)

    for t in range(0, simulation_end_time_ns, dynamic_state_update_interval_ns):
        fstate_file = os.path.join(dynamic_state_dir, "fstate_%d.txt" % t)
        if not os.path.exists(fstate_file):
            continue

        # 累積更新 fstate
        with open(fstate_file, "r") as f_in:
            for line in f_in:
                spl = line.strip().split(",")
                fstate[(int(spl[0]), int(spl[1]))] = int(spl[2])

        path_there = get_path(src_node_id, dst_node_id, fstate)
        path_back  = get_path(dst_node_id, src_node_id, fstate)

        # 計算 RTT（用於圖表標題）
        if path_there is not None and path_back is not None:
            rtt_ns = (
                compute_path_length_without_graph(
                    path_there, epoch, t, satellites,
                    ground_stations, list_isls,
                    max_gsl_length_m, max_isl_length_m)
                + compute_path_length_without_graph(
                    path_back, epoch, t, satellites,
                    ground_stations, list_isls,
                    max_gsl_length_m, max_isl_length_m)
            ) * 1e9 / 299792458.0
        else:
            rtt_ns = 0.0

        # 只在路徑變化時產生圖表
        if current_path == path_there:
            continue
        current_path = path_there

        if current_path is None:
            continue

        print("    Generating graphic for t=%.1f s  (RTT=%.2f ms)..." % (
            t / 1e9, rtt_ns / 1e6))

        pdf_filename = os.path.join(
            graphics_dir,  # [修改] 改寫到子資料夾
            "graphics_%d_to_%d_time_%dms.pdf" % (
                src_node_id, dst_node_id, int(t / 1_000_000))
        )

        time_moment_str = str(epoch + t * u.ns)

        fig = plt.figure()
        ax  = plt.axes(projection=ccrs.PlateCarree())

        # 背景地圖
        ax.add_feature(cartopy.feature.OCEAN,   zorder=0)
        ax.add_feature(cartopy.feature.LAND,    zorder=0,
                       edgecolor="black", linewidth=0.2)
        ax.add_feature(cartopy.feature.BORDERS, edgecolor="gray", linewidth=0.2)

        # 所有衛星（未使用）
        for node_id in range(len(satellites)):
            shadow = create_basic_ground_station_for_satellite_shadow(
                satellites[node_id], str(epoch), time_moment_str)
            lat = float(shadow["latitude_degrees_str"])
            lon = float(shadow["longitude_degrees_str"])
            plt.plot(lon, lat, color=SAT_UNUSED_COLOR,
                     fillstyle="none", markeredgewidth=0.1,
                     markersize=0.5, marker="^")
            plt.text(lon + 0.5, lat, str(node_id),
                     color=SAT_UNUSED_COLOR, fontdict={"size": 1})

        # 所有地面站（未使用）
        for gid in range(len(ground_stations)):
            lat = float(ground_stations[gid]["latitude_degrees_str"])
            lon = float(ground_stations[gid]["longitude_degrees_str"])
            plt.plot(lon, lat, color=GS_UNUSED_COLOR,
                     fillstyle="none", markeredgewidth=0.2,
                     markersize=1.0, marker="o")

        # 路徑上的連線
        for v in range(1, len(current_path)):
            from_id = current_path[v - 1]
            to_id   = current_path[v]

            def _get_latlon(node_id):
                if node_id < len(satellites):
                    s = create_basic_ground_station_for_satellite_shadow(
                        satellites[node_id], str(epoch), time_moment_str)
                    return float(s["latitude_degrees_str"]), float(s["longitude_degrees_str"])
                else:
                    gs = ground_stations[node_id - len(satellites)]
                    return float(gs["latitude_degrees_str"]), float(gs["longitude_degrees_str"])

            from_lat, from_lon = _get_latlon(from_id)
            to_lat,   to_lon   = _get_latlon(to_id)
            _plot_connection_with_dateline_handling(
                ax, from_lon, from_lat, to_lon, to_lat,
                color=ISL_COLOR, linewidth=0.5, marker="")

        # 路徑上的節點
        for node_id in current_path:
            if node_id < len(satellites):
                s = create_basic_ground_station_for_satellite_shadow(
                    satellites[node_id], str(epoch), time_moment_str)
                lat = float(s["latitude_degrees_str"])
                lon = float(s["longitude_degrees_str"])
                plt.plot(lon, lat, color=SAT_USED_COLOR, marker="^", markersize=0.65)
                plt.text(lon + 0.9, lat, str(node_id),
                         fontdict={"size": 2, "weight": "bold"})
            else:
                gs  = ground_stations[node_id - len(satellites)]
                lat = float(gs["latitude_degrees_str"])
                lon = float(gs["longitude_degrees_str"])
                plt.plot(lon, lat, color=GS_USED_COLOR, marker="o", markersize=0.9)

        # 圖例
        ax.legend(
            handles=[
                Line2D([0], [0], marker="o", label="Ground station (used)",
                       linewidth=0, color=GS_USED_COLOR, markersize=5),
                Line2D([0], [0], marker="o", label="Ground station (unused)",
                       linewidth=0, color=GS_UNUSED_COLOR, markersize=5,
                       fillstyle="none", markeredgewidth=0.5),
                Line2D([0], [0], marker="^", label="Satellite (used)",
                       linewidth=0, color=SAT_USED_COLOR, markersize=5),
                Line2D([0], [0], marker="^", label="Satellite (unused)",
                       linewidth=0, color=SAT_UNUSED_COLOR, markersize=5,
                       fillstyle="none", markeredgewidth=0.5),
            ],
            loc="lower left", fontsize="xx-small",
        )

        ax.set_title("Route at t=%.1f s  (RTT=%.2f ms)" % (t / 1e9, rtt_ns / 1e6))
        fig.savefig(pdf_filename, bbox_inches="tight")
        plt.close(fig)
        print("    Saved: %s" % pdf_filename)

    print("  > [graphic] Done.")


# ---------------------------------------------------------------------------
# Core analysis (dynamic version of plot_pair_path_max_utilization)
# ---------------------------------------------------------------------------

def analyze_pair_path_utilization(run_dir, dynamic_state_algorithm,
                                  src_node_id, dst_node_id,
                                  dynamic_state_update_interval_ns,
                                  simulation_end_time_ns):
    """
    Compute and plot the max ISL utilization on the path src→dst for a
    dynamic traffic-matrix run.

    Key difference vs. the static version:
      - Routes are read directly from the fstate_*.txt files produced
        during the closed-loop simulation (same approach as
        analysis_dynamic_result.py).
      - ISL utilization is read from logs_ns3/isl_utilization.csv
        (identical format to the static experiment).
    """
    from satgen.post_analysis.graph_tools import get_path
    from satgen.isls import read_isls
    from satgen.ground_stations import read_ground_stations_extended
    from satgen.tles import read_tles

    algorithm_run_dir = os.path.join(run_dir, dynamic_state_algorithm)

    # [修改] 衛星網路目錄指向 OneWeb
    satellite_network_dir = os.path.join(
        "/home/pflin/research/hypatia-pf/paper/satellite_networks_state/gen_data",
        "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls"
    )
    dynamic_state_dir = os.path.join(algorithm_run_dir, "dynamic_state")

    run_short = os.path.basename(run_dir)
    data_dir = os.path.join("data", run_short, dynamic_state_algorithm)
    pdf_dir = os.path.join("pdf", run_short, dynamic_state_algorithm)
    local_shell = exputil.LocalShell()
    print("  > Clearing output directories: %s and %s" % (data_dir, pdf_dir))
    local_shell.remove_force_recursive(data_dir)
    local_shell.make_full_dir(data_dir)
    local_shell.remove_force_recursive(pdf_dir)
    local_shell.make_full_dir(pdf_dir)

    # ------------------------------------------------------------------
    # [新增] Step 0: 產生 networkx_path 與 networkx_rtt
    # 必須在 dynamic simulation 跑完後才能產生（需要所有 fstate 檔案）
    # ------------------------------------------------------------------
    print("  > Step 0: Generating networkx_path and networkx_rtt...")
    generate_networkx_path_and_rtt(
        algorithm_run_dir=algorithm_run_dir,
        satellite_network_dir=satellite_network_dir,
        src_node_id=src_node_id,
        dst_node_id=dst_node_id,
        dynamic_state_update_interval_ns=dynamic_state_update_interval_ns,
        simulation_end_time_ns=simulation_end_time_ns,
        data_dir=data_dir,
        pdf_dir=pdf_dir,
    )

    # ------------------------------------------------------------------
    # 1. Reconstruct path for every 100 ms interval from fstate files
    # ------------------------------------------------------------------
    print("  > Step 1: Reading fstate files from: %s" % dynamic_state_dir)

    # Build a compact list of (time_ns, path_list) – only record changes
    paths_timeline = []          # [(time_ns, [node, ...]) ...]
    fstate = {}

    for t in range(0, simulation_end_time_ns, dynamic_state_update_interval_ns):
        fstate_file = os.path.join(dynamic_state_dir, "fstate_%d.txt" % t)
        if not os.path.exists(fstate_file):
            print("    Warning: %s not found, skipping" % fstate_file)
            continue
        with open(fstate_file) as f:
            for line in f:
                spl = line.split(",")
                fstate[(int(spl[0]), int(spl[1]))] = int(spl[2])

        path = get_path(src_node_id, dst_node_id, fstate)
        if not paths_timeline or paths_timeline[-1][1] != path:
            paths_timeline.append((t, path if path else []))

    # ------------------------------------------------------------------
    # 2. Read ISL utilization
    # ------------------------------------------------------------------
    util_csv = os.path.join(algorithm_run_dir, "logs_ns3", "isl_utilization.csv")
    print("  > Step 2: Reading utilization: %s" % util_csv)
    link_to_utilization = {}
    with open(util_csv) as f:
        for line in f:
            spl = line.split(",")
            key = (int(spl[0]), int(spl[1]))
            from_t = int(spl[2])
            till_t = int(spl[3])
            util = float(spl[4])
            if from_t == 0:
                link_to_utilization[key] = []
            link_to_utilization[key].append((from_t, till_t, util))

    # ------------------------------------------------------------------
    # 3. Compute max utilization per 100 ms interval
    # ------------------------------------------------------------------
    number_of_intervals_total = 0
    number_of_intervals_with_a_path = 0
    number_of_intervals_with_at_least_a_third_unused = 0
    all_intervals = []

    data_100ms = os.path.join(
        data_dir, "pair_path_utilization_at_100ms_%d_to_%d.txt" % (src_node_id, dst_node_id)
    )

    with open(data_100ms, "w") as f_out:
        # Walk the path timeline to know current path at each t
        path_idx = -1
        for t in range(0, simulation_end_time_ns, dynamic_state_update_interval_ns):

            # Advance path index when a new path takes effect
            while (path_idx + 1 < len(paths_timeline) and
                   paths_timeline[path_idx + 1][0] <= t):
                path_idx += 1

            current_path = paths_timeline[path_idx][1] if path_idx >= 0 else []

            # Collect utilization for every ISL hop on this path
            utilization_list = []
            for i in range(2, len(current_path) - 1):
                pair = (current_path[i - 1], current_path[i])
                if pair in link_to_utilization:
                    for (from_t, till_t, util) in link_to_utilization[pair]:
                        if from_t <= t < till_t:
                            utilization_list.append(util)

            max_util = max(utilization_list) if utilization_list else 0.0
            f_out.write("%d,%.20f\n" % (t, max_util))
            all_intervals.append((t, max_util))

            if utilization_list:
                if max_util < 2.0 / 3.0:
                    number_of_intervals_with_at_least_a_third_unused += 1
                number_of_intervals_with_a_path += 1
            number_of_intervals_total += 1

    # ------------------------------------------------------------------
    # 4. Print / save statistics
    # ------------------------------------------------------------------
    stat_file = os.path.join(
        data_dir, "utilization_information_%d_to_%d.txt" % (src_node_id, dst_node_id)
    )
    with open(stat_file, "w") as f_out:
        for s in [
            "Total intervals.............................. %d" % number_of_intervals_total,
            "Intervals with a path........................ %d" % number_of_intervals_with_a_path,
            "Intervals (w/path) with utilization <= 2/3... %d" % number_of_intervals_with_at_least_a_third_unused,
            "%.2f%% of the intervals have at least 33%% unused bandwidth" % (
                float(number_of_intervals_with_at_least_a_third_unused)
                / float(number_of_intervals_with_a_path) * 100.0
                if number_of_intervals_with_a_path > 0 else 0.0
            ),
        ]:
            print(s)
            f_out.write(s + "\n")

    # ------------------------------------------------------------------
    # 5. Aggregate to 1-second granularity
    # ------------------------------------------------------------------
    data_1s = os.path.join(
        data_dir, "pair_path_utilization_at_1s_%d_to_%d.txt" % (src_node_id, dst_node_id)
    )
    with open(data_1s, "w") as f_1s:
        acc = 0.0
        for i, (t, u) in enumerate(all_intervals, start=1):
            acc += u
            if i % 10 == 0:
                f_1s.write("%d,%.20f\n" % ((i // 10 - 1) * 1_000_000_000, acc / 10.0))
                acc = 0.0

    # ------------------------------------------------------------------
    # 6. Plot
    # ------------------------------------------------------------------
    pdf_out = os.path.join(
        pdf_dir, "pair_available_bandwidth_%d_to_%d.pdf" % (src_node_id, dst_node_id)
    )
    script = PLOT_TEMPLATE.replace("[DATA-FILE]", data_1s).replace("[OUTPUT-FILE]", pdf_out)
    _run_gnuplot(script)
    print("  > PDF → %s" % pdf_out)

    # ------------------------------------------------------------------
    # [新增] Step 7a: 地圖視覺化（移植自 analysis_dynamic_result.py）
    # ------------------------------------------------------------------
    print("  > Step 7a: Generating graphical route maps...")
    generate_graphical_routes(
        algorithm_run_dir=algorithm_run_dir,
        satellite_network_dir=satellite_network_dir,
        src_node_id=src_node_id,
        dst_node_id=dst_node_id,
        dynamic_state_update_interval_ns=dynamic_state_update_interval_ns,
        simulation_end_time_ns=simulation_end_time_ns,
        pdf_dir=pdf_dir,
    )

    # ------------------------------------------------------------------
    # 7b. Optional: per-flow TCP plots (flow 0 and flow 35, same as original)
    # ------------------------------------------------------------------
    plot_tcp_flow_tool = (
        "../../../ns3-sat-sim/simulator/contrib/basic-sim/tools/plotting/plot_tcp_flow"
    )

    # [修改] 使用絕對路徑，避免從 plot_tcp_flow/ 目錄執行時路徑錯誤
    abs_base = os.path.abspath(os.path.dirname(__file__))
    abs_logs_ns3_dir = os.path.join(abs_base, algorithm_run_dir, "logs_ns3")
    abs_data_dir = os.path.join(abs_base, data_dir)
    abs_pdf_dir = os.path.join(abs_base, pdf_dir)

    for flow_id in [0, 35]:
        # [修改] logs_ns3 路徑補上 /logs_ns3，data/pdf 改用絕對路徑
        cmd = (
            "cd %s; python plot_tcp_flow.py "
            "%s "
            "%s "
            "%s "
            "%d %d"
        ) % (plot_tcp_flow_tool,
             abs_logs_ns3_dir,
             abs_data_dir,
             abs_pdf_dir,
             flow_id, 1_000_000_000)
        result = subprocess.run(cmd, shell=True, executable="/bin/bash",
                                capture_output=True, text=True)
        if result.returncode != 0:
            print("  > Warning: plot_tcp_flow failed for flow %d: %s" % (flow_id, result.stderr))
        else:
            print("  > TCP flow %d plot generated" % flow_id)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Analyze and plot dynamic traffic-matrix results."
    )
    add_traffic_mode_argument(parser)
    args = parser.parse_args()
    explicit_traffic_mode = args.traffic_mode is not None
    selected_traffic_mode, selected_traffic_modes = describe_traffic_mode_selection(
        args.traffic_mode
    )

    os.makedirs("data", exist_ok=True)
    os.makedirs("pdf", exist_ok=True)

    # [新增] 每次執行 step_3 都寫一份獨立 log
    runs = get_tm_dynamic_run_list(selected_traffic_mode)
    algo = runs[0]["dynamic_state_algorithm"] if runs else "unknown_algo"
    script_dir = os.path.abspath(os.path.dirname(__file__))
    logs_dir = os.path.join(script_dir, "logs")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # [修改] 檔名加上 dynamic_state_algorithm
    log_file_path = os.path.join(
        logs_dir,
        f"step_3_generate_plots_{algo}_{ts}.log"
    )

    original_stdout, original_stderr, log_fp = setup_logging(log_file_path)
    try:
        print("============================================================")
        print("step_3_generate_plots.py started")
        print("Log file: %s" % log_file_path)
        print("Traffic mode selection: %s (%s)" % (
            selected_traffic_mode, ", ".join(selected_traffic_modes)))
        print("============================================================")

        analyzed_count = 0
        for run in runs:
            run_name = run["name"]
            algorithm = run["dynamic_state_algorithm"]
            run_dir = os.path.join("runs", run_name)

            print("\n" + "=" * 60)
            print("Analyzing: %s / %s" % (run_name, algorithm))
            print("=" * 60)

            missing_inputs = find_missing_analysis_inputs(run_dir, algorithm)
            if missing_inputs:
                message = (
                    "Missing analysis inputs for %s / %s: %s. "
                    "Run step_2_run.py --traffic-mode %s first."
                ) % (
                    run_name,
                    algorithm,
                    ", ".join(missing_inputs),
                    selected_traffic_mode,
                )
                if explicit_traffic_mode:
                    raise RuntimeError(message)
                print("  > Warning: %s Skipping this run." % message)
                continue

            analyze_pair_path_utilization(
                run_dir=run_dir,
                dynamic_state_algorithm=algorithm,
                src_node_id=run["src_node_id"],
                dst_node_id=run["dst_node_id"],
                dynamic_state_update_interval_ns=run["dynamic_state_update_interval_ns"],
                simulation_end_time_ns=run["simulation_end_time_ns"],
            )
            analyzed_count += 1

        if analyzed_count == 0:
            raise RuntimeError(
                "No traffic-matrix runs were analyzed for traffic mode selection: %s"
                % selected_traffic_mode
            )

        print("\nstep_3_generate_plots.py finished successfully")
    finally:
        restore_logging(original_stdout, original_stderr, log_fp)


if __name__ == "__main__":
    main()
