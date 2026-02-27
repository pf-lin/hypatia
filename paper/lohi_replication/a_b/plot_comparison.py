"""
比較兩個演算法的 RTT 結果
"""

import matplotlib.pyplot as plt
import numpy as np
import os
import sys

# 讀取資料
def read_rtt_data(filename):
    """讀取 RTT 資料檔案"""
    time_ns = []
    rtt_ms = []
    
    with open(filename, 'r') as f:
        for line in f:
            if line.strip():
                parts = line.strip().split(',')
                time_ns.append(float(parts[0]))
                rtt_ms.append(float(parts[1]))
    
    # 轉換為秒和毫秒
    time_s = [t / 1e9 for t in time_ns]
    rtt_ms = [r / 1e6 for r in rtt_ms]
    
    return time_s, rtt_ms

# 設定輸出路徑
base_run_dir = '/home/pflin/research/hypatia-pf/paper/lohi_replication/a_b/runs/oneweb_1200_isls_757_to_736_with_TcpNewReno_at_10_Mbps_dynamic'
os.makedirs(base_run_dir, exist_ok=True)

# 設定統計資訊輸出檔案
stats_output_path = os.path.join(base_run_dir, 'rtt_comparison_statistics.txt')

# 重新導向 print 輸出到檔案和終端
class TeeOutput:
    def __init__(self, file_path):
        self.terminal = sys.stdout
        self.log = open(file_path, 'w', encoding='utf-8')
    
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
    
    def flush(self):
        self.terminal.flush()
        self.log.flush()
    
    def close(self):
        self.log.close()

# 開始記錄輸出
tee = TeeOutput(stats_output_path)
sys.stdout = tee

print("=== RTT Comparison Analysis ===")
print(f"輸出路徑: {base_run_dir}\n")

# 讀取兩個檔案的資料
time_queue_aware, rtt_queue_aware = read_rtt_data(
    os.path.join(base_run_dir, 'algorithm_queue_aware_over_isls/analysis/data/networkx_rtt_757_to_736.txt')
)

time_tlr, rtt_tlr = read_rtt_data(
    os.path.join(base_run_dir, 'algorithm_tlr/analysis/data/networkx_rtt_757_to_736.txt')
)

# 創建圖表 - 使用較大的寬度
fig, ax = plt.subplots(figsize=(20, 6))

# 繪製兩條線
ax.plot(time_queue_aware, rtt_queue_aware, 
        label='Queue Aware Over ISLs', 
        linewidth=1.5, 
        color='#2177b0',
        alpha=0.8)

ax.plot(time_tlr, rtt_tlr, 
        label='TLR', 
        linewidth=1.5, 
        color='#fc7f2b',
        alpha=0.8)

# 設定圖表樣式
ax.set_xlabel('Time (s)', fontsize=14)
ax.set_ylabel('NetworkX RTT (ms)', fontsize=14)
ax.set_title('RTT Comparison: Queue Aware vs TLR (Chicago to Lagos)', fontsize=16)

# 設定網格
ax.grid(True, linestyle='--', alpha=0.3, color='#999999')

# 設定圖例
ax.legend(fontsize=12, loc='upper right')

# 設定 x 軸範圍
ax.set_xlim(0, max(max(time_queue_aware), max(time_tlr)))

# 設定 y 軸從 0 開始
ax.set_ylim(0, max(max(rtt_queue_aware), max(rtt_tlr)) * 1.05)

# 調整邊距
plt.tight_layout()

# 儲存圖片到指定路徑
pdf_output_path = os.path.join(base_run_dir, 'rtt_comparison.pdf')
plt.savefig(pdf_output_path, dpi=300, bbox_inches='tight')
print(f"PDF 圖表已儲存至: {pdf_output_path}")

# 也儲存 PNG 格式方便預覽
png_output_path = os.path.join(base_run_dir, 'rtt_comparison.png')
plt.savefig(png_output_path, dpi=300, bbox_inches='tight')
print(f"PNG 圖表已儲存至: {png_output_path}")

# 關閉圖表（不顯示）
plt.close()

##### 過濾掉 RTT 為 0 的資料點 ######
rtt_queue_aware_nonzero = [r for r in rtt_queue_aware if r > 0]
rtt_tlr_nonzero = [r for r in rtt_tlr if r > 0]

# 印出統計資訊
print("\n=== 統計資訊 (包含 RTT = 0) ===")
print(f"Queue Aware Over ISLs:")
print(f"  總資料點數: {len(rtt_queue_aware)}")
print(f"  RTT = 0 的數量: {len([r for r in rtt_queue_aware if r == 0])}")
print(f"  平均 RTT: {np.mean(rtt_queue_aware):.2f} ms")
print(f"  最小 RTT: {np.min(rtt_queue_aware):.2f} ms")
print(f"  最大 RTT: {np.max(rtt_queue_aware):.2f} ms")
print(f"  標準差: {np.std(rtt_queue_aware):.2f} ms")

print(f"\nTLR:")
print(f"  總資料點數: {len(rtt_tlr)}")
print(f"  RTT = 0 的數量: {len([r for r in rtt_tlr if r == 0])}")
print(f"  平均 RTT: {np.mean(rtt_tlr):.2f} ms")
print(f"  最小 RTT: {np.min(rtt_tlr):.2f} ms")
print(f"  最大 RTT: {np.max(rtt_tlr):.2f} ms")
print(f"  標準差: {np.std(rtt_tlr):.2f} ms")

print("\n=== 統計資訊 (排除 RTT = 0) ===")
print(f"Queue Aware Over ISLs:")
print(f"  有效資料點數: {len(rtt_queue_aware_nonzero)}")
print(f"  平均 RTT: {np.mean(rtt_queue_aware_nonzero):.2f} ms")
print(f"  最小 RTT: {np.min(rtt_queue_aware_nonzero):.2f} ms")
print(f"  最大 RTT: {np.max(rtt_queue_aware_nonzero):.2f} ms")
print(f"  標準差: {np.std(rtt_queue_aware_nonzero):.2f} ms")

print(f"\nTLR:")
print(f"  有效資料點數: {len(rtt_tlr_nonzero)}")
if len(rtt_tlr_nonzero) > 0:
    print(f"  平均 RTT: {np.mean(rtt_tlr_nonzero):.2f} ms")
    print(f"  最小 RTT: {np.min(rtt_tlr_nonzero):.2f} ms")
    print(f"  最大 RTT: {np.max(rtt_tlr_nonzero):.2f} ms")
    print(f"  標準差: {np.std(rtt_tlr_nonzero):.2f} ms")
else:
    print("  (無有效資料)")

print(f"\n統計資訊已儲存至: {stats_output_path}")

# 恢復標準輸出並關閉檔案
sys.stdout = tee.terminal
tee.close()

print(f"\n所有輸出已完成！")
print(f"輸出目錄: {base_run_dir}")
print(f"  - {os.path.basename(pdf_output_path)}")
print(f"  - {os.path.basename(png_output_path)}")
print(f"  - {os.path.basename(stats_output_path)}")