# H80 200s 後論文實驗就緒度分析

## 1. 總結結論

- **H80 200s 支持 60s 的主要結論。** 兩個 duration 都維持 `Baseline < LoHi < LHTR < Queue-aware` 的 aggregate-PDR 排序，也維持 `Queue-aware < LHTR < LoHi < Baseline` 的 estimated-RTT 排序。
- LHTR 相對 LoHi 的 PDR gain 從 60s 的 **28.93 percentage points** 變成 200s 的 **28.85 percentage points**，只差 0.07 pp，主效果高度穩定。
- Queue-aware 相對 LHTR 的 upper-bound gap 從 **7.32 pp** 縮至 **6.32 pp**。Queue-aware 仍最佳，但 LHTR 已大幅縮小 LoHi 與理想參考之間的距離。
- 判定為 **A：目前 5-level 60s + H80 200s 足夠支撐論文主結果**。限制是每個 scenario 只有單次 formal run，不能宣稱跨 seed 的統計普遍性。
- **不需要立即補 H100+ 200s。** 它可作額外 stress-test backup，但不是進入論文寫作前的必要條件。
- 唯一最重要的下一步是：**開始整理論文實驗章節與圖表。**

## 2. 使用資料

- `paper/lohi_replication/udp_pdr/analysis_reports/hotspot_5level_60s_comparison/hotspot_5level_cross_level_summary.csv`
- `paper/lohi_replication/udp_pdr/analysis_reports/hotspot_5level_60s_comparison/tables/pdr_algorithm_gaps_by_level.csv`
- `paper/lohi_replication/udp_pdr/analysis_reports/hotspot_5level_60s_comparison/tables/lhtr_diagnostics_across_hotspot_levels.csv`
- `paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim60s_stop58s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/core/`
- `paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim200s_stop198s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/core/`
- `paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim200s_stop198s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/diagnostics/`
- `paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim200s_stop198s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr/algorithm_lhtr/lhtr_diagnostics/`
- `paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim200s_stop198s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr/algorithm_lohi/lohi_manager_diagnostics/`
- `paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim200s_stop198s_isl10mbps_gsl100mbps_lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr/algorithm_lhtr/run_metadata.json`

分析未重跑 simulation，也未修改任何 routing algorithm、policy 或 congestion-level 定義。

## 3. H80 60s vs 200s

| Duration | Algorithm | Aggregate PDR | Focus PDR | Background PDR | Mean RTT ms | P95 RTT ms | Lost packets | PDR rank | RTT rank |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 60s | Queue-aware | 0.9601 | 0.9798 | 0.9588 | 213.0 | 249.3 | 17,499 | 1 | 1 |
| 60s | LHTR | 0.8868 | 0.9293 | 0.8842 | 234.3 | 310.3 | 49,596 | 2 | 2 |
| 60s | LoHi | 0.5975 | 0.7110 | 0.5904 | 273.1 | 391.7 | 176,370 | 3 | 3 |
| 60s | Baseline | 0.5172 | 0.2371 | 0.5347 | 776.0 | 798.5 | 211,580 | 4 | 4 |
| 200s | Queue-aware | 0.9631 | 0.9820 | 0.9619 | 226.1 | 263.1 | 55,175 | 1 | 1 |
| 200s | LHTR | 0.9000 | 0.9304 | 0.8981 | 250.6 | 340.5 | 149,662 | 2 | 2 |
| 200s | LoHi | 0.6114 | 0.6977 | 0.6060 | 286.7 | 405.0 | 581,326 | 3 | 3 |
| 200s | Baseline | 0.4696 | 0.5222 | 0.4663 | 982.1 | 1207.1 | 793,422 | 4 | 4 |

重點：

1. 200s aggregate PDR 為 Baseline=0.4696、LoHi=0.6114、LHTR=0.9000、Queue-aware=0.9631。
2. LHTR 200s 比 LoHi 高 28.85 pp；mean estimated RTT 低 36.1 ms，p95 低 64.5 ms。
3. Baseline aggregate PDR 比 60s 低 4.76 pp，mean RTT 增加 206.2 ms，顯示固定 shortest path 在較長 observation window 中持續承受 queue pressure。
4. Lost packets 是不同 traffic duration 下的絕對數，不能直接用倍數比較；PDR 與 `lost_packets_per_traffic_s` 才適合跨 duration 解讀。
5. 60s RTT 採樣間隔為 0.1s（581 valid samples/direction），200s 為 1s（199 samples/direction）。排序一致，但小幅均值差異不應全解讀為 duration effect。

## 4. PDR、loss 與 flow tail

- 200s 的 p5/min flow PDR：Baseline=0.1001/0.0695、LoHi=0.4130/0.4072、LHTR=0.8684/0.8617、Queue-aware=0.9420/0.9384。
- 四個演算法的 dominant attribution 都是 `isl_saturation_associated_loss`；associated loss ratio 為 ISL=1.0、GSL=0、mixed=0。
- Exact physical queue/PHY drop categories 為 0。這只表示現有 attribution pipeline 未取得 exact physical-drop evidence；**associated loss 不可改寫成 physical drop proof**。
- GSL 最大 queue 只有 1-3 packets，而 ISL queue 達 100 packets，支持實驗主要量測 ISL bottleneck。

## 5. RTT 與 route

以下 RTT 都是由 replayed path、propagation/transmission delay 與 queue history 組成的 estimated RTT，不是 packet-level measured RTT。

| Algorithm | Mean RTT ms | P95 RTT ms | Propagation-only ms | Mean queue delay ms | Forward hops mean (range) | Reverse hops mean (range) | Route plots |
| --- | ---: | ---: | ---: | ---: | --- | --- | ---: |
| Queue-aware | 226.1 | 263.1 | 178.4 | 1.7 | 21.01 (18-29) | 21.01 (18-29) | 24 |
| LHTR | 250.6 | 340.5 | 180.8 | 22.6 | 21.45 (18-33) | 21.45 (18-33) | 24 |
| LoHi | 286.7 | 405.0 | 194.9 | 37.8 | 24.30 (18-38) | 24.30 (18-38) | 24 |
| Baseline | 982.1 | 1207.1 | 158.8 | 780.9 | 19.49 (18-20) | 19.49 (18-20) | 24 |

LoHi 平均 hop count 最高（24.30），LHTR 為 21.45、Queue-aware 為 21.01。LHTR 與 Queue-aware 都接受適度 path stretch 以避開 bottleneck；LoHi 路徑較長但 congestion reaction 仍不如 LHTR，因此同時呈現較高 RTT 與較低 PDR。

## 6. LHTR diagnostics

| Duration | BR selected | SBR selected | SBR ratio | Yellow | Red | Fallback |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 60s | 79,369,810 | 92,289 | 0.1161% | 161,229 | 33,077 | 0 |
| 200s | 264,753,700 | 277,857 | 0.1048% | 475,221 | 94,598 | 0 |

- H80 200s SBR ratio **沒有高於** 60s；由 0.1161% 小幅降至 0.1048%。因此不應寫成「時間越長 SBR 越多」。
- yellow/red 也沒有隨時間單調累積。分箱後的 SBR ratios 為 0-60s=0.1187%、60-120s=0.0994%、120-180s=0.1020%、180-200s=0.0879%；較合理的描述是 sustained load 下反覆出現 congestion bursts。
- SBR 與 yellow+red count 的 Pearson correlation 為 **0.896**；colored count 最高 25% 的 0.1s windows 承載 **50.9%** 的 SBR decisions，支持「SBR 集中在壅塞較強時段」。
- 200s top reasons：`br_green` 73.14%、`no_alternative_candidate` 24.51%、`sbr_stretch_too_high` 2.24%。低 SBR ratio 主要來自 candidate coverage 與 stretch admissibility，而不是 diagnostics 沒有看見 congestion。
- Eligible fstate checks 的 match rate 為 **99.883%**，fallback count 為 0，支持 implementation consistency。

## 7. LoHi diagnostics

- 8,000 筆 manager-mode records 全部為 `control_plane_only`。
- 實體 path 包含 manager 的比例只有 8.96%；manager 的角色是 control-plane border selection，並非 strict physical waypoint。
- Border compliance ratio 為 99.86%，loop check 未發現 loop。
- Manager hotspot records 約占 6.75%。這些 diagnostics 證明 manager-assisted evidence 存在，但不能把 LoHi 等同於 ideal global queue-aware routing。

## 8. 論文 readiness 判斷

### 為什麼足夠

1. 五個 60s levels 已呈現從 localized congestion 到 overload 的 severity curve，且 H60-H100+ 的排序一致。
2. H80 是 LHTR-LoHi gain 最大的 level；200s 結果幾乎重現相同 gain，排除主要結論只是短時間偶然的疑慮。
3. Queue-aware 提供同一 demand 下的理想 routing headroom，適合作為 upper bound，不是 LHTR 必須擊敗的 deployable competitor。
4. H90/H100+ 60s 已證明 severe/overload 下 LHTR 仍優於 LoHi；H100+ 200s 只會補強 stress duration，不會改變主論證結構。
5. 當前最缺的是把結果轉成論文章節、圖說與教授可快速判讀的敘事，而不是擴張 simulation matrix。

### 限制

- 每個 scenario/duration 只有一個 formal run，沒有重複 seed 或 confidence interval。
- Level 同時改變 load level 與 background-flow count，因此是 formal severity curve，不是單一自變數 controlled sweep。
- Hotspot-reference denominator 隨 touched reference ISL subset 改變，必須和 global/corridor/peak metrics 一起揭露。
- Estimated RTT 不是 packet-level RTT；loss attribution 是 association，不是 exact physical drop proof。

## 9. 主圖建議

Main：aggregate PDR across levels、mean estimated RTT across levels、LHTR-LoHi gain、Queue-aware upper-bound gap、H80 60s vs 200s PDR stability。

Supporting：focus/background PDR、H80 duration RTT、SBR ratio、yellow/red、loss attribution、H80 graphical routes。

Diagnostics only：raw decision reasons、fstate consistency、queue-at-capacity samples。

完整清單見 `thesis_recommended_figures.csv`。

## 10. 下一步

**開始整理論文實驗章節與圖表。** H100+ 200s 保留為時間與資源充裕時的 optional stress-test backup，不列為畢業主線的 blocking item。
