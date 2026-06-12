# UDP/PDR ISL Load Percentage Mapping 分析報告

## 1. 總結結論

- 已成功用既有 30 個 settings、既有 UDP schedule 與 Baseline shortest-path
  forwarding states 重算 offered ISL resource load；reference replay success
  ratio 全部為 100%，confidence 為 high。
- PDR 已完全移出 scenario definition。正式 `traffic_load_label` 只由
  routing-independent offered ISL resource load 決定；Queue-aware pressure
  只作 observed validation。
- 30 點的 official global offered load 範圍只有 **1.319%-11.354%**，
  label 分布為：Low=30。
- 因此目前資料**無法**對應老師想看的 40/60/80/90/100%。最重的
  `load=3.0,bg=56` 也只有 11.354%。
- 目前列出 5 個 pressure-span provisional anchors，但全部
  `recommended_for_60s=false`；在補齊正式百分比 mapping 前不應直接跑
  60s 或 200s formal experiment。
- 唯一建議的下一步是：依 official 公式設計 targeted 10s calibration，
  先補可達 40% 與 60% 的點並重新檢查 GSL safety，再決定是否往
  80/90/100% 延伸。

## 2. 資料來源

- `runs/comparison_calibration/src754_dst785_isl10mbps_gsl100mbps_10s/`
  下的 scenario summary 與 GSL/ISL diagnostics。
- 每個 run 的 `run_metadata.json`、`config_ns3.properties`、
  `udp_burst_schedule.csv`、`isl_corridor_load_summary.csv`。
- 每個 algorithm 的 `logs_ns3/isl_utilization.csv` 與既有
  `comparison_packet_delivery/core/` outcome/queue/loss CSV。
- Baseline reference：
  `paper/satellite_networks_state/gen_data/.../dynamic_state_1000ms_for_200s/`
  的 0-7 s、1 s forwarding-state snapshots。
- 30 個 Queue-aware 與 2 個既有 Baseline algorithm outcomes 全部通過
  GSL safety gate。

## 3. 新 congestion definition

正式公式為：

```text
offered_isl_resource_load_% =
  100 * sum(flow_rate_Mbps * time-averaged baseline ISL hop count)
  / (2880 directed ISLs * 10 Mbps)
```

Official reference 是 traffic window 0-8 s 內的 Baseline shortest-path
time average；supplemental reference 是固定 `t=0` snapshot。兩者皆不使用
任何 PDR。正式 label 門檻為 Low <50%、Medium 50-70%、High 70-85%、
Severe 85-100%、Overload >=100%。

由於分母是整個 constellation 的 28,800 Mbps directed-ISL capacity，
它量測的是 global resource fraction，不是 hotspot corridor 的局部 load。
因此報告另外保留 active-reference capacity 與 peak reference-link demand
作診斷，但不拿它們替換 official label。

## 4. Scenario mapping 結果

| setting_id | offered_isl_resource_load_percent | traffic_load_label | observed_pressure_condition | safe_for_isl_focused_experiment |
| --- | --- | --- | --- | --- |
| L1.0/B16 | 1.3194 | Low | Non-congested | true |
| L1.2/B16 | 1.5833 | Low | Non-congested | true |
| L1.0/B24 | 1.8417 | Low | Localized congestion | true |
| L1.4/B16 | 1.8472 | Low | Localized congestion | true |
| L1.2/B24 | 2.2101 | Low | Localized congestion | true |
| L1.0/B32 | 2.3278 | Low | Localized congestion | true |
| L1.4/B24 | 2.5784 | Low | Localized congestion | true |
| L1.2/B32 | 2.7934 | Low | Localized congestion | true |
| L1.6/B24 | 2.9468 | Low | Localized congestion | true |
| L1.4/B32 | 3.2590 | Low | Sustained congestion | true |
| L1.8/B24 | 3.3151 | Low | Localized congestion | true |
| L2.0/B24 | 3.6834 | Low | Sustained congestion | true |
| L1.6/B32 | 3.7245 | Low | Sustained congestion | true |
| L1.8/B32 | 4.1901 | Low | Sustained congestion | true |
| L1.6/B40 | 4.2060 | Low | Sustained congestion | true |
| L2.0/B32 | 4.6557 | Low | Sustained congestion | true |
| L1.8/B40 | 4.7318 | Low | Sustained congestion | true |
| L2.2/B32 | 5.1212 | Low | Sustained congestion | true |
| L2.0/B40 | 5.2575 | Low | Sustained congestion | true |
| L2.4/B32 | 5.5868 | Low | Sustained congestion | true |
| L2.2/B40 | 5.7833 | Low | Sustained congestion | true |
| L2.4/B40 | 6.3090 | Low | Sustained congestion | true |
| L2.2/B48 | 7.0278 | Low | Sustained congestion | true |
| L2.4/B48 | 7.6667 | Low | Sustained congestion | true |
| L2.6/B48 | 8.3056 | Low | Sustained congestion | true |
| L2.8/B48 | 8.9444 | Low | Overloaded | true |
| L3.0/B48 | 9.5833 | Low | Overloaded | true |
| L2.6/B56 | 9.8403 | Low | Overloaded | true |
| L2.8/B56 | 10.5972 | Low | Overloaded | true |
| L3.0/B56 | 11.3542 | Low | Overloaded | true |

Queue-aware observed condition 分布為：Localized congestion=8, Non-congested=2, Overloaded=5, Sustained congestion=15。這些 condition 只描述 adaptive
routing 下量到的壓力，不改變所有 setting 的 official `Low` label。

## 5. Observed ISL pressure

`observed_isl_pressure_summary.csv` 同時包含：

- all-ISL capacity-time mean/p50/p95/p99/max（未使用 capacity 視為 0）。
- active-ISL mean/p50/p95/p99/max。
- target-corridor active p50/p95/p99/max，以及含 idle capacity 的 p95。
- 每條 directed ISL 的 traffic-window mean 所得到的 top1/top5/top10。
- links over 60/70/80/90/100%、queue capacity samples 與 saturation span。

Queue-aware measured ranges: all-ISL p95 0.1069-0.5591、active-ISL p95 0.3389-0.5667、target-corridor active p95 0.4445-0.7375、links over 90% 0-3、ISL capacity samples 0-41915。

Observed condition exact thresholds 已寫入
`scenario_definition_summary.csv` 與 `congestion_mapping_notes.md`。目前分布：
Localized congestion=8, Non-congested=2, Overloaded=5, Sustained congestion=15。

## 6. PDR outcome

`pdr_outcome_by_scenario.csv` 保留 aggregate/focus/background/min/p5 PDR、
lost packets、failed-flow count 與 dominant loss attribution。PDR 是
algorithm outcome；產生 traffic label 與 observed condition 的函式均不
讀取 PDR。

Queue-aware aggregate PDR 範圍為 0.6407-1.0000；Baseline 只有兩個 既有 outcome 點：

| setting_id | aggregate_pdr | focus_pdr | background_pdr |
| --- | --- | --- | --- |
| load=1.0,bg=16 | 0.7878 | 0.9987 | 0.7615 |
| load=2.0,bg=40 | 0.3917 | 0.3959 | 0.3915 |

## 7. Formal candidates

| scenario_id | setting_id | offered_isl_resource_load_percent | traffic_load_label | observed_pressure_condition | recommended_for_60s |
| --- | --- | --- | --- | --- | --- |
| P1 | load=1.0,bg=16 | 1.3194 | Low | Non-congested | false |
| P2 | load=1.8,bg=24 | 3.3151 | Low | Localized congestion | false |
| P3 | load=2.0,bg=32 | 4.6557 | Low | Sustained congestion | false |
| P4 | load=2.4,bg=40 | 6.3090 | Low | Sustained congestion | false |
| P5 | load=2.8,bg=56 | 10.5972 | Low | Overloaded | false |

這 5 點只能當「observed pressure progression」的 provisional anchors，
不能被寫成 40/60/80/90/100% formal scenarios。

## 8. 是否需要補 simulation

需要。現有最大 official load 與 40% 仍差 28.646 percentage points。
下表顯示每個目標目前最近的點：

| target_percent | nearest_setting | actual_percent | gap_percent_points |
| --- | --- | --- | --- |
| 40 | load=3.0,bg=56 | 11.3542 | 28.6458 |
| 60 | load=3.0,bg=56 | 11.3542 | 48.6458 |
| 80 | load=3.0,bg=56 | 11.3542 | 68.6458 |
| 90 | load=3.0,bg=56 | 11.3542 | 78.6458 |
| 100 | load=3.0,bg=56 | 11.3542 | 88.6458 |

不建議單純把既有 `load_level` 當百分比，也不建議因 Queue-aware PDR
降低就宣稱已達 Severe/Overload。新 10s calibration 應直接由 reference
hop demand 反推 aggregate offered rate，並持續套用 GSL safety gate。

以下估算固定使用目前最重 setting 的平均 reference hop `11.2759`，並假設每 flow 5 Mbps；新增 flows 會改變選流與平均 hop，所以它只用來決定 targeted sweep 的起始尺度：

| target_percent | required_hop_demand_Mbps_hops | estimated_total_rate_Mbps | estimated_bg_at_5Mbps_per_flow |
| --- | --- | --- | --- |
| 40.0000 | 11520.0000 | 1021.6514 | 203.0000 |
| 60.0000 | 17280.0000 | 1532.4771 | 305.0000 |
| 80.0000 | 23040.0000 | 2043.3028 | 407.0000 |
| 90.0000 | 25920.0000 | 2298.7156 | 458.0000 |
| 100.0000 | 28800.0000 | 2554.1284 | 509.0000 |

## 9. 新增檔案

- `isl_load_percentage_mapping.csv`
- `scenario_definition_summary.csv`
- `observed_isl_pressure_summary.csv`
- `pdr_outcome_by_scenario.csv`
- `formal_candidate_table.csv`
- `gsl_safety_check.csv`
- `congestion_mapping_notes.md`
- `analysis_report_zh.md`
- `offered_isl_load_vs_pdr.png`
- `offered_isl_load_vs_target_corridor_utilization.png`
- `offered_isl_load_vs_links_over_90pct.png`
- `scenario_mapping_overview.png`
- `traffic_load_vs_observed_pressure.png`

## 10. 論文敘事建議

### 中文

本研究不直接將實驗參數 `load_level` 解讀為網路負載百分比，也不使用封包
傳遞率反推壅塞等級。每個 traffic setting 先依各 flow 的 offered rate 與
Baseline shortest-path reference 在 traffic window 內的平均 ISL hop count，
計算 capacity-normalized offered ISL resource demand；正式 scenario label
僅由此 routing-independent demand 決定。接著以各演算法實測的 all-ISL、
active-ISL、target-corridor 與 queue-saturation 指標驗證 hotspot 是否形成。
PDR 最後才作為相同 offered-load condition 下的演算法效能結果，因此不會
把某個 routing algorithm 的成功或失敗混入 scenario definition。

### English

We define traffic-load conditions using capacity-normalized ISL resource demand
rather than post-hoc packet-delivery outcomes. For each flow, its offered rate
is multiplied by the time-averaged ISL hop count of a reproducible Baseline
shortest-path reference and then normalized by the total directed ISL capacity.
Observed all-ISL, active-ISL, target-corridor, and queue-saturation metrics are
reported separately to validate whether a localized hotspot emerges under each
routing algorithm. Packet delivery ratio is evaluated only as an algorithmic
outcome under the resulting offered-load condition and never participates in
the congestion-level definition.

## 11. 下一步建議

只做一件事：補 targeted 10s calibration。先用 reference-hop demand 反推能
達到 official 40% 與 60% 的 settings，確認 flow selection 可行且 GSL
仍安全後，再決定是否有條件探索 80/90/100%；暫不跑 60s/200s formal。
