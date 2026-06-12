---
marp: true
theme: default
paginate: true
size: 16:9
---

# UDP/PDR Dynamic Routing 實驗進度

## ISL corridor congestion 與 packet delivery

2026-06-05

---

# 目前一句話結論

在目前最完整的 60 秒、24-background-flow 壓力案例中：

- **Queue-aware PDR = 98.93%**
- LHTR PDR = 95.24%
- LoHi PDR = 82.58%
- Static baseline PDR = 56.96%

Queue-aware 相對 static：

- Aggregate PDR 提高 **41.97 percentage points**
- Packet loss 減少 **97.51%**
- Focus-flow PDR 從 33.23% 提高到 **96.44%**

LHTR 取得 Queue-aware 相對 static PDR 改善量的 **91.2%**。

---

# 實驗設定

- OneWeb moving constellation
- 2 focus flows: `738 <-> 793`
- 24 background flows
- Per-flow target rate: 3 Mbps
- Total target rate: 78 Mbps
- ISL/GSL capacity: 10 Mbps
- Traffic: 0-58 s
- Simulation end: 60 s
- Drain time: 2 s

目標：將 background traffic 集中到 focus middle-ISL corridor。

---

# 如何找到有效的壅塞案例

1. 早期 load sweep
   - 約 1.3x 後，static routing 開始明顯退化。
2. Drain-time validation
   - 移除 simulation-end in-flight loss。
3. 4-background-flow ISL hotspot
   - 壓力不足，多數案例 PDR 仍為 100%。
4. Background-flow sweep
   - 舊 selector 的轉折約在 16-32 flows。
5. Flow-selection improvement
   - 同樣 24 flows，但讓 traffic 更集中於 target corridor。

---

# 舊版 background-flow sweep

![bg right:60%](runs_backup_bg_1p4_1p8_20260602_003003/comparison_packet_delivery_across_background_flow_counts/background_flow_count_vs_pdr.png)

1.8x load：

- 8/16 flows：多數演算法仍接近 100%
- 32 flows：PDR 開始下降
- 64 flows：Queue-aware/LHTR 明顯優於 static/LoHi

舊 selector 的壅塞 transition 約在 **16-32 flows**。

---

# 新版 traffic concentration

![bg right:54%](runs/run_core_isl_hotspot_specific_load_1p8x_bg_flow_count_24_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/corridor_concentration_summary.png)

- 22/24 background flows 有 middle-ISL overlap
- Average overlap score: 13.33
- Target edge estimated load: **2.7x capacity**
- Top non-focus edge: 1.8x capacity
- Top loaded edge 位於 target corridor

同樣 24 flows，flow placement 比 flow count 更關鍵。

---

# Aggregate PDR

![bg right:62%](runs/run_core_isl_hotspot_specific_load_1p8x_bg_flow_count_24_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/aggregate_pdr.png)

| Algorithm | PDR | Lost packets |
|---|---:|---:|
| Static | 56.96% | 162,252 |
| Queue-aware | **98.93%** | **4,040** |
| LoHi | 82.58% | 65,680 |
| LHTR | 95.24% | 17,959 |

---

# Focus-flow protection

![bg right:62%](runs/run_core_isl_hotspot_specific_load_1p8x_bg_flow_count_24_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/focus_flow_pdr.png)

| Algorithm | Mean focus PDR |
|---|---:|
| Static | 33.23% |
| Queue-aware | **96.44%** |
| LoHi | 83.39% |
| LHTR | 89.30% |

Queue-aware 對 focus traffic 的保護最完整。

---

# Directional asymmetry

| Algorithm | 738 -> 793 | 793 -> 738 |
|---|---:|---:|
| Static | 19.02% | 47.44% |
| Queue-aware | **99.96%** | **92.92%** |
| LoHi | 91.36% | 75.42% |
| LHTR | 99.97% | 78.63% |

重點：

- 路由效果具有方向性。
- LHTR 一個方向接近無 loss，反方向仍明顯退化。
- 不能只報兩條 focus flows 的平均值。

---

# 先釐清研究主張

目前數據**不支持**：

> LHTR 的 PDR 已經比 Queue-aware 好。

目前數據支持：

> Queue-aware 是每 100 ms 使用全網 queue 狀態重算全域 SPF 的強 reference。
> LHTR 在 hierarchy 限制下取得其相對 static 改善量的 91.2%，剩餘差距可追到
> 特定 attachment 與 GSL concentration 問題。

---

# 為何 Queue-aware 目前較好

| Mechanism | Queue-aware | LHTR |
|---|---|---|
| Queue-aware scope | 全部 ISLs | PID 內 ISLs |
| Inter-group path | 全域 SPF | group graph 先選 `next_pid` |
| Border choice | 不受 group border 限制 | 既定 PID pair 內選擇 |
| Directional queue | 雙向最大值 | 目前只取一個方向 |
| GSL load awareness | 無 | 無 |

Queue-aware 的 candidate space 與資訊範圍都更強，適合作為
**global-information reference**，不是相同複雜度的直接對手。

---

# 35.1 秒的關鍵轉折

LHTR 在 `t = 35.1 s` 將 flows 15-17：

- destination attachment：sat 278 -> sat 277
- Queue-aware path：19-21 hops，仍由 sat 278 下行
- LHTR path：**32-33 hops**，改由 sat 277 下行

sat 277 原本已有 flows 1、21、23：

- Queue-aware：3 flows x 3 Mbps = **9 Mbps**
- LHTR：6 flows x 3 Mbps = **18 Mbps**
- GSL capacity：10 Mbps

`t = 35.2 s`，LHTR 的 GSL 277 queue 開始達到 100 packets。

---

# 這代表什麼

目前最可疑的不是 Queue-aware 寫錯，而是 LHTR 內部 cost 不一致：

1. destination attachment 用全圖 Dijkstra cost 選擇。
2. 實際路徑卻受 group path、border 與 traffic light 限制。
3. attachment decision 沒有計入 GSL capacity 或已匯入 flow count。

直接結果是 18 Mbps traffic 匯入單一 10 Mbps GSL；cost-model mismatch
是否直接造成 switch，需用 ablation 確認。

---

# Fairness 與 tail performance

| Algorithm | P5 flow PDR | Min flow PDR | Jain fairness |
|---|---:|---:|---:|
| Static | 12.17% | 4.95% | 0.7301 |
| Queue-aware | **95.98%** | **92.92%** | **0.9997** |
| LoHi | 58.34% | 37.21% | 0.9641 |
| LHTR | 76.78% | 75.10% | 0.9917 |

Queue-aware 不只是平均值最高，也沒有任何 flow 低於 0.9 PDR。

---

# 目前的 loss attribution

![bg right:58%](runs/run_core_isl_hotspot_specific_load_1p8x_bg_flow_count_24_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/loss_attribution_breakdown_v2.png)

- Physical queue drop trace: 0
- PHY drop trace: 0
- UDP send failure: 0
- Routing/no-route drop: 0
- IPv4 L3 generic drop hook: 尚未完整提供
- ISL tracker 每輪 reset，但 GSL tracker 未 reset，history coverage 不對稱

目前只能做 queue-saturation **association**，不能說已證明 physical drop。

---

# GSL queue pressure

![bg right:57%](runs/run_core_isl_hotspot_specific_load_1p8x_bg_flow_count_24_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/gsl_queue_occupancy_by_algorithm.png)

- Static GSL max queue: 2 packets
- Queue-aware/LoHi/LHTR GSL max queue: 100 packets
- LHTR 的 99.00% synthetic loss 可關聯到 GSL saturation
- Queue-aware: 73.56%
- LoHi: 46.16%

合理假說：動態路由改善 ISL congestion 後，部分壓力轉移到 GSL/access side。

---

# 必須保留的 caveat

目前可以確定：

- Queue-aware 在此 60 秒案例表現最好。
- LHTR 次佳，且明顯優於 static 與 LoHi。
- 新 selector 成功製造強 corridor pressure。

目前不能確定：

- Loss 的實際 physical drop layer。
- Static 的 loss 是否全部由 ISL queue overflow 造成。
- Queue-aware 是否在所有 orbital windows 都第一。
- 10/60/200 秒結果能否直接視為 duration sweep。
- 統計顯著性，因為尚未做多 seed/repetition。

---

# 暫時不能主張低 overhead

| Current implementation metric | Queue-aware | LHTR |
|---|---:|---:|
| Mean changed fstate entries/update | 604 | 1,941 |
| Total delta fstate lines | 443,769 | 1,244,374 |
| Iteration wall-clock proxy | 2.06 s | 4.50 s |

目前 LHTR 實作的 route churn 與 wall-clock proxy 反而較高。

因此現階段應把「低 control/runtime overhead」列為待驗證目標，
不能當成已完成的優勢。

---

# LHTR 並非所有案例都較差

| Case | Queue-aware | LHTR |
|---|---:|---:|
| 10 s diagnostic | 96.66% | **97.53%** |
| Old selector, 32 BG flows | 96.60% | **97.01%** |
| Current 60 s concentrated | **98.93%** | 95.24% |

較合理的結論：

> LHTR 的弱點集中在長時間、高集中負載下，而不是所有案例全面失效。

---

# 200 秒 provisional result

`runs_backup_1p8_bg_24_200s_dirty_*`：

| Algorithm | Aggregate PDR | Focus PDR |
|---|---:|---:|
| Static | 77.89% | 100.00% |
| Queue-aware | **99.96%** | 100.00% |
| LoHi | 64.17% | 96.04% |
| LHTR | 95.61% | 99.80% |

仍支持 Queue-aware > LHTR，但資料夾標記為 `dirty`。

用途：說明長時間行為值得正式重跑，不作為最終 duration comparison。

---

# 下一步

1. 將 `t = 35.1 s` 做成 deterministic regression case。
2. 讓 attachment cost 與實際 hierarchical path cost 一致。
3. attachment selection 加入 GSL capacity/load penalty。
4. LHTR 改用雙向 queue 最大值，與 Queue-aware 公平比較。
5. 做 traffic-light / queue-penalty ablation。
6. 修正後重跑相同 10 s、60 s、乾淨 200 s。
7. 再補 physical drop、不同 orbital windows 與 repetitions。

---

# 建議對老師的收尾

> 我目前不會宣稱 LHTR 的 PDR 已經勝過全域 Queue-aware SPF。現有結果顯示，
> LHTR 在保留階層限制下取得了 global reference 相對 static 改善的 91.2%。
> 剩餘差距集中在 35.1 秒後的 destination attachment 決策，它把六條流量匯入
> 單一 10 Mbps GSL。下一步會先修正 attachment 與 GSL-load design gap，並用 ablation
> 確認 hierarchy、traffic light 與 GSL-aware attachment 各自的影響。
