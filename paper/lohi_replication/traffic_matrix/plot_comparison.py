"""
比較不同演算法的 RTT（traffic_matrix 版本）
"""

import argparse
import os
import sys
import numpy as np
import matplotlib.pyplot as plt


def read_rtt_data(file_path):
    time_s = []
    rtt_ms = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            t_ns, r_ns = line.split(",")
            time_s.append(float(t_ns) / 1e9)
            rtt_ms.append(float(r_ns) / 1e6)
    return np.array(time_s), np.array(rtt_ms)


class TeeOutput:
    def __init__(self, file_path):
        self.terminal = sys.stdout
        self.log = open(file_path, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()


def find_rtt_file(run_base_dir, algo, src, dst):
    # traffic_matrix/data/[run_name]/[dynamic_state_algorithm]/networkx_rtt_{src}_to_{dst}.txt
    return os.path.join(
        run_base_dir,
        algo,
        f"networkx_rtt_{src}_to_{dst}.txt",
    )


def stats_text(name, values):
    if len(values) == 0:
        return f"{name}\n  (無有效資料)\n"
    return (
        f"{name}\n"
        f"  資料點數: {len(values)}\n"
        f"  平均 RTT: {np.mean(values):.2f} ms\n"
        f"  最小 RTT: {np.min(values):.2f} ms\n"
        f"  最大 RTT: {np.max(values):.2f} ms\n"
        f"  標準差: {np.std(values):.2f} ms\n"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="run_name（位於 traffic_matrix/data 底下）")
    parser.add_argument("--src", type=int, required=True)
    parser.add_argument("--dst", type=int, required=True)
    parser.add_argument(
        "--algorithms",
        nargs="+",
        required=True,
        help="要比較的演算法資料夾名稱，例如 algorithm_tlr algorithm_queue_aware_over_isls",
    )
    parser.add_argument("--width", type=float, default=15.0, help="圖寬（inch）")
    parser.add_argument("--height", type=float, default=6.0, help="圖高（inch）")
    parser.add_argument("--output-prefix", default="rtt_comparison")
    args = parser.parse_args()

    # 以此腳本為基準定位到 traffic_matrix/data/[run_name]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    run_base_dir = os.path.join(script_dir, "data", args.run_dir)
    os.makedirs(run_base_dir, exist_ok=True)

    log_path = os.path.join(run_base_dir, f"{args.output_prefix}_statistics.txt")
    tee = TeeOutput(log_path)
    sys.stdout = tee

    print("=== RTT Comparison (traffic_matrix) ===")
    print(f"run_dir: {args.run_dir}")
    print(f"src -> dst: {args.src} -> {args.dst}")
    print(f"algorithms: {args.algorithms}\n")

    all_data = {}
    for algo in args.algorithms:
        fp = find_rtt_file(run_base_dir, algo, args.src, args.dst)
        if not os.path.exists(fp):
            print(f"[WARN] 找不到檔案，略過: {fp}")
            continue
        t, r = read_rtt_data(fp)
        all_data[algo] = (t, r)
        print(f"[OK] {algo}: {len(r)} points")

    if not all_data:
        print("\n[ERROR] 沒有可用資料。")
        sys.stdout = tee.terminal
        tee.close()
        return

    # 畫圖（x 軸拉長）
    fig, ax = plt.subplots(figsize=(args.width, args.height))
    colors = ["#2177b0", "#fc7f2b", "#2f9e37", "#d42a2d", "#80007F", "#8a554c"]

    localized = False
    if not localized:
        ymax = 0.0
        xmax = 0.0
        for i, (algo, (t, r)) in enumerate(all_data.items()):
            color = colors[i % len(colors)]
            ax.plot(t, r, label=algo, linewidth=1.4, alpha=0.9, color=color)
            ymax = max(ymax, float(np.max(r)))
            xmax = max(xmax, float(np.max(t)))

        ax.set_xlabel("Time (s)")
        ax.set_ylabel("NetworkX RTT (ms)")
        ax.set_title(f"RTT Comparison ({args.src} -> {args.dst})")
        ax.grid(True, linestyle="--", alpha=0.3, color="#999999")
        ax.legend(loc="upper right")
        ax.set_xlim(0, xmax)
        ax.set_ylim(0, ymax * 1.05)
        plt.tight_layout()
    else:
        all_r_values = []
        all_r_values_nonzero = []
        xmax = 0.0

        for i, (algo, (t, r)) in enumerate(all_data.items()):
            color = colors[i % len(colors)]
            ax.plot(t, r, label=algo, linewidth=1.4, alpha=0.9, color=color)
            xmax = max(xmax, float(np.max(t)))
            all_r_values.extend(r.tolist())
            all_r_values_nonzero.extend(r[r > 0].tolist())

        ax.set_xlabel("Time (s)")
        ax.set_ylabel("NetworkX RTT (ms)")
        ax.set_title(f"RTT Comparison ({args.src} -> {args.dst})")
        ax.grid(True, linestyle="--", alpha=0.3, color="#999999")
        ax.legend(loc="upper right")
        ax.set_xlim(0, xmax)

        # y 軸不從 0 開始：優先用非 0 資料估算範圍
        y_arr = np.array(all_r_values_nonzero if len(all_r_values_nonzero) > 0 else all_r_values)
        ymin = float(np.min(y_arr))
        ymax = float(np.max(y_arr))
        yrange = max(ymax - ymin, 1e-9)
        pad = yrange * 0.05
        ax.set_ylim(ymin - pad, ymax + pad)

        plt.tight_layout()

    pdf_path = os.path.join(run_base_dir, f"{args.output_prefix}.pdf")
    png_path = os.path.join(run_base_dir, f"{args.output_prefix}.png")
    plt.savefig(pdf_path, dpi=300, bbox_inches="tight")
    plt.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"\nPDF: {pdf_path}")
    print(f"PNG: {png_path}")

    print("\n=== 統計資訊（包含 RTT = 0）===")
    for algo, (_, r) in all_data.items():
        print(stats_text(algo, r))

    print("\n=== 統計資訊（排除 RTT = 0）===")
    for algo, (_, r) in all_data.items():
        r_nonzero = r[r > 0]
        zero_count = int(np.sum(r == 0))
        print(f"{algo}\n  RTT=0 數量: {zero_count}")
        print(stats_text("", r_nonzero))

    print(f"統計檔案: {log_path}")

    sys.stdout = tee.terminal
    tee.close()

    print("完成。")
    print(f"輸出: {pdf_path}, {png_path}, {log_path}")


if __name__ == "__main__":
    main()