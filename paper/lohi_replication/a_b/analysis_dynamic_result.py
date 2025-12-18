"""
分析動態 NS-3 模擬生成的 fstate
"""

import sys
import os
import shutil
import numpy as np

# 添加 satgenpy 路徑
sys.path.append("/home/pflin/research/hypatia-pf/satgenpy")


# ===== 新增：日誌類別，同時輸出到終端和檔案 =====
class TeeLogger:
    """同時寫入到 stdout/stderr 和檔案"""
    def __init__(self, log_file, mode='w', original_stream=None):
        self.file = open(log_file, mode)
        self.original_stream = original_stream
        
    def write(self, message):
        if self.original_stream:
            self.original_stream.write(message)
        self.file.write(message)
        self.file.flush()  # 立即寫入檔案
        
    def flush(self):
        if self.original_stream:
            self.original_stream.flush()
        self.file.flush()
        
    def close(self):
        self.file.close()


def setup_logging(log_file_path):
    """
    設定日誌，將 stdout 和 stderr 同時輸出到終端和檔案
    
    Args:
        log_file_path: 日誌檔案路徑
    
    Returns:
        原始的 stdout 和 stderr（用於恢復）
    """
    # 確保目錄存在
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
    
    # 保存原始的 stdout 和 stderr
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    # 創建 TeeLogger
    sys.stdout = TeeLogger(log_file_path, 'w', original_stdout)
    sys.stderr = TeeLogger(log_file_path, 'a', original_stderr)  # 'a' 模式追加錯誤訊息
    
    return original_stdout, original_stderr


def restore_logging(original_stdout, original_stderr):
    """恢復原始的 stdout 和 stderr"""
    if hasattr(sys.stdout, 'close'):
        sys.stdout.close()
    if hasattr(sys.stderr, 'close'):
        sys.stderr.close()
    
    sys.stdout = original_stdout
    sys.stderr = original_stderr


plot_script_template = """
#####################################
### STYLING

# Terminal (gnuplot 4.4+); Swiss neutral Helvetica font
set terminal pdfcairo font "Helvetica, 24" linewidth 1.5 rounded dashed

# Line style for axes
set style line 80 lt rgb "#808080"

# Line style for grid
set style line 81 lt 0  # Dashed
set style line 81 lt rgb "#999999"  # Grey grid

# Grey grid and border
set grid back linestyle 81
set border 3 back linestyle 80
set xtics nomirror
set ytics nomirror

# Line styles
set style line 1 lt rgb "#2177b0" lw 2.4 pt 1 ps 0
set style line 2 lt rgb "#fc7f2b" lw 2.4 pt 2 ps 0
set style line 3 lt rgb "#2f9e37" lw 2.4 pt 3 ps 0
set style line 4 lt rgb "#d42a2d" lw 2.4 pt 4 ps 1.4
set style line 5 lt rgb "#80007F" lw 2.4 pt 5 ps 1.4
set style line 6 lt rgb "#8a554c" lw 2.4 pt 6 ps 1.4
set style line 7 lt rgb "#e079be" lw 2.4 pt 0 ps 1.4
set style line 8 lt rgb "#7d7d7d" lw 2.4 pt 0 ps 1.4
set style line 9 lt rgb "#000000" lw 2.4 pt 0 ps 1.4

# Output
set output "[OUTPUT-FILE]"

#####################################
### AXES AND KEY

# Axes labels
set xlabel "Time (s)" # Markup: e.g. 99^{th}, {/Symbol s}, {/Helvetica-Italic P}
set ylabel "NetworkX RTT (ms)"

# Axes ranges
set xrange [0:]       # Explicitly set the x-range [lower:upper]
set yrange [0:]       # Explicitly set the y-range [lower:upper]
# set xtics (0, 100, 300, 500, 700, 900)
# set ytics <start>, <incr> {,<end>}
# set format x "%.2f%%"  # Set the x-tic format, e.g. in this case it takes 2 sign. decimals: "24.13%""

# For logarithmic axes
# set log x           # Set logarithmic x-axis
# set log y           # Set logarithmic y-axis
# set mxtics 3        # Set number of intermediate tics on x-axis (for log plots)
# set mytics 3        # Set number of intermediate tics on y-axis (for log plots)

# Font of the key (a.k.a. legend)
set key font ",14"
set key reverse
set key top right Left
set key spacing 2

#####################################
### PLOTS
set datafile separator ","
plot    "[DATA-FILE]" using ($1/1000000000):($2/1000000) title "" w lp ls 1, \
"""


def analyze_dynamic_simulation_results(
    run_name,
    dynamic_state_update_interval_ms=100,
    simulation_end_time_s=200,
    src=757,  # Chicago
    dst=736   # Lagos
):
    """
    分析動態模擬的結果
    
    Args:
        run_name: 運行名稱（例如 "oneweb_1200_isls_757_to_736_with_TcpNewReno_at_10_Mbps_dynamic"）
        dynamic_state_update_interval_ms: 動態狀態更新間隔（毫秒）
        simulation_end_time_s: 模擬結束時間（秒）
        src: 源節點 ID
        dst: 目標節點 ID
    """
    
    # 路徑配置
    base_dir = "/home/pflin/research/hypatia-pf/paper"
    
    # Run 目錄（包含動態生成的 fstate）
    run_dir = os.path.join(base_dir, "lohi_replication/a_b/runs", run_name)
    
    # 衛星網路配置目錄（包含 tles.txt, ground_stations.txt 等）
    satellite_network_dir = os.path.join(
        base_dir,
        "satellite_networks_state/gen_data/"
        "oneweb_1200_isls_plus_grid_ground_stations_top_100_algorithm_free_one_only_over_isls"
    )
    
    # 輸出目錄
    analysis_output_dir = os.path.join(run_dir, "analysis")
    
    # 如果分析目錄已存在，先刪除它
    if os.path.exists(analysis_output_dir):
        shutil.rmtree(analysis_output_dir)

    # 創建輸出目錄
    os.makedirs(analysis_output_dir, exist_ok=True)
    os.makedirs(os.path.join(analysis_output_dir, "pdf"), exist_ok=True)
    os.makedirs(os.path.join(analysis_output_dir, "data"), exist_ok=True)
    os.makedirs(os.path.join(analysis_output_dir, "command_logs"), exist_ok=True)

    # ===== 新增：設定日誌 =====
    log_file = os.path.join(
        analysis_output_dir,
        "command_logs",
        f"oneweb_isls_{src}_to_{dst}.log"
    )
    original_stdout, original_stderr = setup_logging(log_file)
    
    try:
        print("\n" + "="*70)
        print("DYNAMIC SIMULATION RESULTS ANALYSIS")
        print("="*70)
        print(f"Run name: {run_name}")
        print(f"Source: {src} (Ground Station)")
        print(f"Destination: {dst} (Ground Station)")
        print(f"Update interval: {dynamic_state_update_interval_ms} ms")
        print(f"Simulation duration: {simulation_end_time_s} s")
        print(f"Log file: {log_file}")
        print("="*70 + "\n")
        
        # ===== 分析 1: 路徑和 RTT（文本輸出）=====
        print("\n[Analysis 1] Analyzing routes and RTT (text output)...")
        print("-" * 70)
        
        try:
            # 修改這個函數，讓它使用 run_dir 中的 dynamic_state
            print_routes_and_rtt_for_dynamic_run(
                analysis_output_dir,
                satellite_network_dir,
                run_dir,  # 新增：直接傳入 run_dir
                dynamic_state_update_interval_ms,
                simulation_end_time_s,
                src,
                dst
            )
            print("\n✓ Analysis 1 completed")
            print(f"  > Output: {analysis_output_dir}/data/networkx_path_{src}_to_{dst}.txt")
            print(f"  > Output: {analysis_output_dir}/data/networkx_rtt_{src}_to_{dst}.txt")
            print(f"  > Output: {analysis_output_dir}/pdf/time_vs_networkx_rtt_{src}_to_{dst}.pdf")
        except Exception as e:
            print(f"\n✗ Analysis 1 failed: {e}")
            import traceback
            traceback.print_exc()  # 印出完整的錯誤堆疊
        
        # ===== 分析 2: 圖形化路徑視覺化 =====
        print("\n[Analysis 2] Generating graphical route visualizations...")
        print("-" * 70)
        
        try:
            print_graphical_routes_and_rtt_for_dynamic_run(
                analysis_output_dir,
                satellite_network_dir,
                run_dir,  # 新增：直接傳入 run_dir
                dynamic_state_update_interval_ms,
                simulation_end_time_s,
                src,
                dst
            )
            print("\n✓ Analysis 2 completed")
            print(f"  > Output: {analysis_output_dir}/pdf/graphics_*.pdf")
        except Exception as e:
            print(f"\n✗ Analysis 2 failed: {e}")
            import traceback
            traceback.print_exc()  # 印出完整的錯誤堆疊
        
        print("\n" + "="*70)
        print("ANALYSIS COMPLETED")
        print("="*70)
        print(f"\nAll results saved to: {analysis_output_dir}")
        print(f"Log file: {log_file}")
        print()

    finally:
        # ===== 恢復原始的 stdout/stderr =====
        restore_logging(original_stdout, original_stderr)


def print_routes_and_rtt_for_dynamic_run(
    base_output_dir,
    satellite_network_dir,
    run_dir,  # 新增參數
    dynamic_state_update_interval_ms,
    simulation_end_time_s,
    src,
    dst
):
    """
    修改版的 print_routes_and_rtt，使用動態生成的 fstate
    """
    import exputil
    import tempfile
    import subprocess
    from satgen.post_analysis.graph_tools import (
        get_path, 
        compute_path_length_without_graph
    )
    from satgen.isls import read_isls
    from satgen.ground_stations import read_ground_stations_extended
    from satgen.tles import read_tles
    
    # Local shell
    local_shell = exputil.LocalShell()
    
    # ===== 關鍵修改：使用 run_dir 中的 dynamic_state =====
    satellite_network_dynamic_state_dir = os.path.join(run_dir, "dynamic_state")
    
    # 輸出目錄
    pdf_dir = os.path.join(base_output_dir, "pdf")
    data_dir = os.path.join(base_output_dir, "data")
    local_shell.make_full_dir(pdf_dir)
    local_shell.make_full_dir(data_dir)
    
    # 載入網路配置
    ground_stations = read_ground_stations_extended(
        os.path.join(satellite_network_dir, "ground_stations.txt")
    )
    tles = read_tles(os.path.join(satellite_network_dir, "tles.txt"))
    satellites = tles["satellites"]
    list_isls = read_isls(
        os.path.join(satellite_network_dir, "isls.txt"),
        len(satellites)
    )
    epoch = tles["epoch"]
    description = exputil.PropertiesConfig(
        os.path.join(satellite_network_dir, "description.txt")
    )
    
    # 參數
    simulation_end_time_ns = simulation_end_time_s * 1000 * 1000 * 1000
    dynamic_state_update_interval_ns = dynamic_state_update_interval_ms * 1000 * 1000
    max_gsl_length_m = exputil.parse_positive_float(
        description.get_property_or_fail("max_gsl_length_m")
    )
    max_isl_length_m = exputil.parse_positive_float(
        description.get_property_or_fail("max_isl_length_m")
    )
    
    # 數據文件路徑
    data_path_filename = os.path.join(
        data_dir, 
        f"networkx_path_{src}_to_{dst}.txt"
    )
    
    with open(data_path_filename, "w+") as data_path_file:
        fstate = {}
        current_path = []
        rtt_ns_list = []
        
        for t in range(0, simulation_end_time_ns, dynamic_state_update_interval_ns):
            fstate_file = os.path.join(
                satellite_network_dynamic_state_dir,
                f"fstate_{t}.txt"
            )
            
            if not os.path.exists(fstate_file):
                print(f"Warning: {fstate_file} not found, skipping t={t}ns")
                continue
            
            with open(fstate_file, "r") as f_in:
                for line in f_in:
                    spl = line.split(",")
                    current = int(spl[0])
                    destination = int(spl[1])
                    next_hop = int(spl[2])
                    fstate[(current, destination)] = next_hop
                
                # 計算路徑長度
                path_there = get_path(src, dst, fstate)
                path_back = get_path(dst, src, fstate)
                
                if path_there is not None and path_back is not None:
                    length_src_to_dst_m = compute_path_length_without_graph(
                        path_there, epoch, t, satellites,
                        ground_stations, list_isls,
                        max_gsl_length_m, max_isl_length_m
                    )
                    length_dst_to_src_m = compute_path_length_without_graph(
                        path_back, epoch, t,
                        satellites, ground_stations, list_isls,
                        max_gsl_length_m, max_isl_length_m
                    )
                    rtt_ns = (length_src_to_dst_m + length_dst_to_src_m) * 1000000000.0 / 299792458.0
                else:
                    length_src_to_dst_m = 0.0
                    length_dst_to_src_m = 0.0
                    rtt_ns = 0.0
                
                # 添加到 RTT 列表
                rtt_ns_list.append((t, rtt_ns))
                
                # 只有路徑改變時才輸出
                new_path = get_path(src, dst, fstate)
                if current_path != new_path:
                    current_path = new_path
                    
                    print(f"Change at t={t} ns (= {t / 1e9} seconds)")
                    print(f"  > Path..... {' -- '.join(map(str, current_path)) if current_path else 'Unreachable'}")
                    print(f"  > Length... {length_src_to_dst_m + length_dst_to_src_m} m")
                    print(f"  > RTT...... {rtt_ns / 1e6:.2f} ms")
                    print()
                    
                    # 寫入路徑文件
                    data_path_file.write(
                        f"{t},{'-'.join(map(str, current_path)) if current_path else 'Unreachable'}\n"
                    )
        
        # 寫入 RTT 數據
        data_filename = os.path.join(data_dir, f"networkx_rtt_{src}_to_{dst}.txt")
        with open(data_filename, "w+") as data_file:
            for t, rtt_ns in rtt_ns_list:
                data_file.write(f"{t},{rtt_ns:.10f}\n")
        
        # 生成圖表
        pdf_filename = os.path.join(
            pdf_dir,
            f"time_vs_networkx_rtt_{src}_to_{dst}.pdf"
        )

        plot_script = plot_script_template
        plot_script = plot_script.replace("[OUTPUT-FILE]", pdf_filename)
        plot_script = plot_script.replace("[DATA-FILE]", data_filename)

        temp_path = None # 先初始化變數，避免 finally 找不到變數報錯

        try:
            # 1. 建立並寫入暫存檔
            # 使用 with 語法，離開此縮排後檔案會自動 Flush 並 Close，確保資料完整寫入硬碟
            with tempfile.NamedTemporaryFile(mode='w', suffix='.plt', delete=False) as tf:
                tf.write(plot_script)
                temp_path = tf.name  # 將路徑存出來，因為離開 with 後 tf 變數雖在但檔案已關閉

            # 2. 執行 Gnuplot
            # 此時檔案已由 Python 釋放，Gnuplot 可以安全讀取
            result = subprocess.run(
                ["gnuplot", temp_path],
                capture_output=True, # 捕捉 stdout 和 stderr
                text=True            # 將輸出解碼為字串 (Python 3.7+)
            )

            # 3. 檢查執行結果
            if result.returncode == 0:
                print(f"Generated plot: {pdf_filename}")
            else:
                # 如果 Gnuplot 失敗，印出詳細錯誤訊息 (stderr)
                print(f"Error: Gnuplot failed via return code {result.returncode}")
                print(f"Gnuplot Stderr: {result.stderr}")
                # 選擇性：如果失敗了，也可以拋出異常讓上層處理
                # raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)

        except Exception as e:
            print(f"Unexpected Error: {e}")

        finally:
            # 4. 清理暫存檔
            # 判斷 temp_path 是否有值且檔案是否存在
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError as e:
                    print(f"Warning: Could not remove temp file {temp_path}: {e}")


def print_graphical_routes_and_rtt_for_dynamic_run(
    base_output_dir,
    satellite_network_dir,
    run_dir,  # 新增參數
    dynamic_state_update_interval_ms,
    simulation_end_time_s,
    src,
    dst
):
    """
    修改版的 print_graphical_routes_and_rtt，使用動態生成的 fstate
    """
    import exputil
    from satgen.post_analysis.graph_tools import (
        get_path,
        compute_path_length_without_graph,
        create_basic_ground_station_for_satellite_shadow
    )
    from satgen.isls import read_isls
    from satgen.ground_stations import read_ground_stations_extended
    from satgen.tles import read_tles
    import astropy.units as u
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    import cartopy.feature
    from matplotlib.lines import Line2D
    
    # Local shell
    local_shell = exputil.LocalShell()
    
    # ===== 關鍵修改：使用 run_dir 中的 dynamic_state =====
    satellite_network_dynamic_state_dir = os.path.join(run_dir, "dynamic_state")
    
    # 輸出目錄
    pdf_dir = os.path.join(base_output_dir, "pdf")
    local_shell.make_full_dir(pdf_dir)
    
    # 載入網路配置
    ground_stations = read_ground_stations_extended(
        os.path.join(satellite_network_dir, "ground_stations.txt")
    )
    tles = read_tles(os.path.join(satellite_network_dir, "tles.txt"))
    satellites = tles["satellites"]
    list_isls = read_isls(
        os.path.join(satellite_network_dir, "isls.txt"),
        len(satellites)
    )
    epoch = tles["epoch"]
    description = exputil.PropertiesConfig(
        os.path.join(satellite_network_dir, "description.txt")
    )
    
    # 參數
    simulation_end_time_ns = simulation_end_time_s * 1000 * 1000 * 1000
    dynamic_state_update_interval_ns = dynamic_state_update_interval_ms * 1000 * 1000
    max_gsl_length_m = exputil.parse_positive_float(
        description.get_property_or_fail("max_gsl_length_m")
    )
    max_isl_length_m = exputil.parse_positive_float(
        description.get_property_or_fail("max_isl_length_m")
    )
    
    # 顏色定義
    GROUND_STATION_USED_COLOR = "#3b3b3b"
    GROUND_STATION_UNUSED_COLOR = "black"
    SATELLITE_USED_COLOR = "#a61111"
    SATELLITE_UNUSED_COLOR = "red"
    ISL_COLOR = "#eb6b38"
    
    # 處理每個時間點
    fstate = {}
    current_path = []
    
    for t in range(0, simulation_end_time_ns, dynamic_state_update_interval_ns):
        fstate_file = os.path.join(
            satellite_network_dynamic_state_dir,
            f"fstate_{t}.txt"
        )
        
        if not os.path.exists(fstate_file):
            print(f"Warning: {fstate_file} not found, skipping t={t}ns")
            continue
        
        with open(fstate_file, "r") as f_in:
            for line in f_in:
                spl = line.split(",")
                current = int(spl[0])
                destination = int(spl[1])
                next_hop = int(spl[2])
                fstate[(current, destination)] = next_hop
            
            # 計算路徑
            path_there = get_path(src, dst, fstate)
            path_back = get_path(dst, src, fstate)
            
            if path_there is not None and path_back is not None:
                length_src_to_dst_m = compute_path_length_without_graph(
                    path_there, epoch, t, satellites,
                    ground_stations, list_isls,
                    max_gsl_length_m, max_isl_length_m
                )
                length_dst_to_src_m = compute_path_length_without_graph(
                    path_back, epoch, t,
                    satellites, ground_stations, list_isls,
                    max_gsl_length_m, max_isl_length_m
                )
                rtt_ns = (length_src_to_dst_m + length_dst_to_src_m) * 1000000000.0 / 299792458.0
            else:
                rtt_ns = 0.0
            
            # 只有路徑改變時才生成圖表
            new_path = get_path(src, dst, fstate)
            if current_path != new_path:
                current_path = new_path
                
                if current_path is None:
                    continue
                
                print(f"Generating graphic for t={t}ns ({t/1e9:.1f}s)...")
                
                # 創建圖表
                pdf_filename = os.path.join(
                    pdf_dir,
                    f"graphics_{src}_to_{dst}_time_{int(t/1000000)}ms.pdf"
                )
                
                fig = plt.figure()#figsize=(12, 6))
                ax = plt.axes(projection=ccrs.PlateCarree())
                
                # 背景
                ax.add_feature(cartopy.feature.OCEAN, zorder=0)
                ax.add_feature(cartopy.feature.LAND, zorder=0, edgecolor='black', linewidth=0.2)
                ax.add_feature(cartopy.feature.BORDERS, edgecolor='gray', linewidth=0.2)
                
                time_moment_str = str(epoch + t * u.ns)
                
                # 繪製所有衛星（未使用）
                for node_id in range(len(satellites)):
                    shadow_gs = create_basic_ground_station_for_satellite_shadow(
                        satellites[node_id], str(epoch), time_moment_str
                    )
                    lat = float(shadow_gs["latitude_degrees_str"])
                    lon = float(shadow_gs["longitude_degrees_str"])
                    
                    plt.plot(lon, lat, color=SATELLITE_UNUSED_COLOR,
                            fillstyle='none', markeredgewidth=0.1,
                            markersize=0.5, marker='^')
                    plt.text(lon + 0.5, lat, str(node_id),
                            color=SATELLITE_UNUSED_COLOR,
                            fontdict={"size": 1})
                
                # 繪製所有地面站（未使用）
                for gid in range(len(ground_stations)):
                    lat = float(ground_stations[gid]["latitude_degrees_str"])
                    lon = float(ground_stations[gid]["longitude_degrees_str"])
                    plt.plot(lon, lat, color=GROUND_STATION_UNUSED_COLOR,
                            fillstyle='none', markeredgewidth=0.2,
                            markersize=1.0, marker='o')
                
                # 繪製路徑上的鏈路
                for v in range(1, len(current_path)):
                    from_node_id = current_path[v - 1]
                    to_node_id = current_path[v]
                    
                    # 獲取座標
                    if from_node_id < len(satellites):
                        shadow_gs = create_basic_ground_station_for_satellite_shadow(
                            satellites[from_node_id], str(epoch), time_moment_str
                        )
                        from_lat = float(shadow_gs["latitude_degrees_str"])
                        from_lon = float(shadow_gs["longitude_degrees_str"])
                    else:
                        from_lat = float(ground_stations[from_node_id - len(satellites)]["latitude_degrees_str"])
                        from_lon = float(ground_stations[from_node_id - len(satellites)]["longitude_degrees_str"])
                    
                    if to_node_id < len(satellites):
                        shadow_gs = create_basic_ground_station_for_satellite_shadow(
                            satellites[to_node_id], str(epoch), time_moment_str
                        )
                        to_lat = float(shadow_gs["latitude_degrees_str"])
                        to_lon = float(shadow_gs["longitude_degrees_str"])
                    else:
                        to_lat = float(ground_stations[to_node_id - len(satellites)]["latitude_degrees_str"])
                        to_lon = float(ground_stations[to_node_id - len(satellites)]["longitude_degrees_str"])
                    
                    # 繪製連線（處理日期變更線）
                    plot_connection_with_dateline_handling(
                        ax, from_lon, from_lat, to_lon, to_lat,
                        color=ISL_COLOR, linewidth=0.5, marker=''
                    )
                
                # 繪製路徑上的節點
                for v in range(len(current_path)):
                    node_id = current_path[v]
                    
                    if node_id < len(satellites):
                        shadow_gs = create_basic_ground_station_for_satellite_shadow(
                            satellites[node_id], str(epoch), time_moment_str
                        )
                        lat = float(shadow_gs["latitude_degrees_str"])
                        lon = float(shadow_gs["longitude_degrees_str"])
                        
                        plt.plot(lon, lat, color=SATELLITE_USED_COLOR,
                                marker='^', markersize=0.65)
                        plt.text(lon + 0.9, lat, str(node_id),
                                fontdict={"size": 2, "weight": "bold"})
                    else:
                        lat = float(ground_stations[node_id - len(satellites)]["latitude_degrees_str"])
                        lon = float(ground_stations[node_id - len(satellites)]["longitude_degrees_str"])
                        
                        plt.plot(lon, lat, color=GROUND_STATION_USED_COLOR,
                                marker='o', markersize=0.9)
                
                # 圖例
                ax.legend(
                    handles=[
                        Line2D([0], [0], marker='o', label="Ground station (used)",
                              linewidth=0, color='#3b3b3b', markersize=5),
                        Line2D([0], [0], marker='o', label="Ground station (unused)",
                              linewidth=0, color='black', markersize=5, fillstyle='none', markeredgewidth=0.5),
                        Line2D([0], [0], marker='^', label="Satellite (used)",
                              linewidth=0, color='#a61111', markersize=5),
                        Line2D([0], [0], marker='^', label="Satellite (unused)",
                              linewidth=0, color='red', markersize=5, fillstyle='none', markeredgewidth=0.5),
                    ],
                    loc='lower left',
                    fontsize='xx-small'
                )
                
                # 標題
                ax.set_title(f"Route at t={t/1e9:.1f}s (RTT={rtt_ns/1e6:.2f}ms)")
                
                # 保存
                fig.savefig(pdf_filename, bbox_inches='tight')#, dpi=150)
                plt.close(fig)
                
                print(f"  > Saved: {pdf_filename}")


def plot_connection_with_dateline_handling(ax, from_lon, from_lat, to_lon, to_lat, n=50, **kwargs):
    """處理日期變更線的連線繪製"""
    def norm(arr):
        a = np.array(arr, dtype=float)
        return ((a + 180) % 360) - 180
    
    from_lon = float(norm(from_lon))
    to_lon = float(norm(to_lon))
    
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


if __name__ == "__main__":
    # 分析動態模擬結果
    analyze_dynamic_simulation_results(
        run_name="oneweb_1200_isls_757_to_736_with_TcpNewReno_at_10_Mbps_dynamic",
        dynamic_state_update_interval_ms=100,
        simulation_end_time_s=200,
        src=757,  # Chicago
        dst=736   # Lagos
    )