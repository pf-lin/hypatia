# Core-ISL Hotspot Reference Load Mapping

## 1. 總結結論

- Global offered ISL load 的 1.319%-11.354% 並沒有算錯；它以全星座
  2,880 條 directed ISLs 為分母，因此會稀釋刻意集中在局部 corridor 的
  hotspot traffic。
- Active-reference normalization 將既有 30 點映射到 47.359%-144.690%，
  五個 hotspot bands 均有資料：Hotspot-Light=2, Hotspot-Moderate=6, Hotspot-High=3, Hotspot-Severe=8, Hotspot-Overload=11。
- 因此 `core_isl_hotspot_specific` 應採雙層定義：hotspot-reference load
  作主要 scenario x-axis，global load 同時報告為 constellation-wide
  context；fixed target-corridor 與 peak-link demand 作 diagnostics。
- 既有點可近似老師要看的 40/60/80/90/100%+，不需要再補 10s
  calibration 才能覆蓋 levels。
- 五個候選皆通過 GSL safety gate，建議下一步跑四演算法 60s formal；
  暫不直接跑 200s。

## 2. 資料來源

- 上一輪 `analysis_reports/isl_load_percentage_mapping/` 的 mapping、
  observed pressure、PDR outcome 與 GSL safety outputs。
- 30 個 run 的 `udp_burst_schedule.csv`、
  `isl_corridor_load_summary.csv` 與 run metadata。
- Baseline/free-one-only 的 0-8 s、1 s forwarding-state snapshots。
- Queue-aware `isl_utilization.csv` 與既有 packet-delivery diagnostics。

## 3. 三種 load metric 定義

```text
global_offered_isl_load_percent =
  100 * reference hop demand
  / (2880 directed ISLs * 10 Mbps)

hotspot_reference_load_percent =
  100 * reference hop demand
  / (per-setting touched reference directed ISLs * 10 Mbps)

target_corridor_offered_load_percent =
  100 * time-averaged reference demand on target corridor
  / (target corridor directed edge count * 10 Mbps)
```

Global metric 描述全星座資源比例。Hotspot-reference metric 描述該 traffic
setting 實際 reference ISL subset 的平均 offered pressure。Target-corridor
metric 使用固定 corridor edge set，是 denominator sensitivity check。
`peak_reference_link_offered_load_percent` 再補充最熱單一 link 的壓力。

Hotspot-reference denominator 會隨 setting 的 touched-link union 改變，因此
不保證對 load/bg 完全單調。這個限制必須與 active-link count 一起揭露，
不能把 hotspot percentage 說成 global percentage。

## 4. Global vs Hotspot 比較

| setting_id | global_offered_isl_load_percent | hotspot_reference_load_percent | target_corridor_offered_load_percent | peak_reference_link_offered_load_percent | hotspot_traffic_load_label | observed_pressure_condition | safe_for_isl_focused_experiment |
| --- | --- | --- | --- | --- | --- | --- | --- |
| load=1.0,bg=24 | 1.842 | 47.359 | 75.333 | 133.333 | Hotspot-Light | Localized congestion | true |
| load=1.0,bg=32 | 2.328 | 49.295 | 90.667 | 183.333 | Hotspot-Light | Localized congestion | true |
| load=1.0,bg=16 | 1.319 | 50.000 | 58.000 | 133.333 | Hotspot-Moderate | Non-congested | true |
| load=1.2,bg=24 | 2.210 | 56.830 | 90.400 | 160.000 | Hotspot-Moderate | Localized congestion | true |
| load=1.2,bg=32 | 2.793 | 59.154 | 108.800 | 220.000 | Hotspot-Moderate | Localized congestion | true |
| load=1.2,bg=16 | 1.583 | 60.000 | 69.600 | 160.000 | Hotspot-Moderate | Non-congested | true |
| load=1.4,bg=24 | 2.578 | 66.302 | 105.467 | 186.667 | Hotspot-Moderate | Localized congestion | true |
| load=1.4,bg=32 | 3.259 | 69.013 | 126.933 | 256.667 | Hotspot-Moderate | Sustained congestion | true |
| load=1.4,bg=16 | 1.847 | 70.000 | 81.200 | 186.667 | Hotspot-High | Localized congestion | true |
| load=1.6,bg=24 | 2.947 | 75.774 | 120.533 | 213.333 | Hotspot-High | Localized congestion | true |
| load=1.6,bg=32 | 3.725 | 78.873 | 145.067 | 293.333 | Hotspot-High | Sustained congestion | true |
| load=1.8,bg=24 | 3.315 | 85.246 | 135.600 | 240.000 | Hotspot-Severe | Localized congestion | true |
| load=1.6,bg=40 | 4.206 | 86.524 | 166.933 | 400.000 | Hotspot-Severe | Sustained congestion | true |
| load=1.8,bg=32 | 4.190 | 88.732 | 163.200 | 330.000 | Hotspot-Severe | Sustained congestion | true |
| load=2.2,bg=48 | 7.028 | 91.171 | 243.467 | 623.333 | Hotspot-Severe | Sustained congestion | true |
| load=2.0,bg=24 | 3.683 | 94.717 | 150.667 | 266.667 | Hotspot-Severe | Sustained congestion | true |
| load=1.8,bg=40 | 4.732 | 97.339 | 187.800 | 450.000 | Hotspot-Severe | Sustained congestion | true |
| load=2.0,bg=32 | 4.656 | 98.591 | 181.333 | 366.667 | Hotspot-Severe | Sustained congestion | true |
| load=2.4,bg=48 | 7.667 | 99.459 | 265.600 | 680.000 | Hotspot-Severe | Sustained congestion | true |
| load=2.6,bg=48 | 8.306 | 107.748 | 287.733 | 736.667 | Hotspot-Overload | Sustained congestion | true |
| load=2.0,bg=40 | 5.258 | 108.155 | 208.667 | 500.000 | Hotspot-Overload | Sustained congestion | true |
| load=2.2,bg=32 | 5.121 | 108.450 | 199.467 | 403.333 | Hotspot-Overload | Sustained congestion | true |
| load=2.8,bg=48 | 8.944 | 116.036 | 309.867 | 793.333 | Hotspot-Overload | Overloaded | true |
| load=2.4,bg=32 | 5.587 | 118.309 | 217.600 | 440.000 | Hotspot-Overload | Sustained congestion | true |
| load=2.2,bg=40 | 5.783 | 118.970 | 229.533 | 550.000 | Hotspot-Overload | Sustained congestion | true |
| load=3.0,bg=48 | 9.583 | 124.324 | 332.000 | 850.000 | Hotspot-Overload | Overloaded | true |
| load=2.6,bg=56 | 9.840 | 125.398 | 343.200 | 910.000 | Hotspot-Overload | Overloaded | true |
| load=2.4,bg=40 | 6.309 | 129.786 | 250.400 | 600.000 | Hotspot-Overload | Sustained congestion | true |
| load=2.8,bg=56 | 10.597 | 135.044 | 369.600 | 980.000 | Hotspot-Overload | Overloaded | true |
| load=3.0,bg=56 | 11.354 | 144.690 | 396.000 | 1050.000 | Hotspot-Overload | Overloaded | true |

所有 global labels 仍為 Low。Hotspot label 分布為：
Hotspot-Light=2, Hotspot-Moderate=6, Hotspot-High=3, Hotspot-Severe=8, Hotspot-Overload=11。

Spearman rank correlation with Queue-aware target-corridor active p95：

- global offered load: 0.962
- hotspot-reference load: 0.895
- fixed target-corridor offered load: 0.962
- peak reference-link demand: 0.956

Hotspot-reference 與 observed pressure order 的 rank correlation 為 0.862。
它提供更直接的局部 capacity-scale 解讀，但與 target-corridor p95 的
相關性實際低於 global/fixed-corridor metrics，主因是 per-setting active
denominator 會擴張。因此本文不宣稱它更能預測 Queue-aware outcome；
observed metrics 仍是獨立 validation。

## 5. Hotspot scenario mapping

| setting_id | hotspot_reference_load_percent | hotspot_traffic_load_label | observed_pressure_condition | queue_aware_pdr |
| --- | --- | --- | --- | --- |
| load=1.0,bg=24 | 47.359 | Hotspot-Light | Localized congestion | 0.999 |
| load=1.0,bg=32 | 49.295 | Hotspot-Light | Localized congestion | 0.994 |
| load=1.0,bg=16 | 50.000 | Hotspot-Moderate | Non-congested | 1.000 |
| load=1.2,bg=24 | 56.830 | Hotspot-Moderate | Localized congestion | 0.996 |
| load=1.2,bg=32 | 59.154 | Hotspot-Moderate | Localized congestion | 0.986 |
| load=1.2,bg=16 | 60.000 | Hotspot-Moderate | Non-congested | 1.000 |
| load=1.4,bg=24 | 66.302 | Hotspot-Moderate | Localized congestion | 0.992 |
| load=1.4,bg=32 | 69.013 | Hotspot-Moderate | Sustained congestion | 0.971 |
| load=1.4,bg=16 | 70.000 | Hotspot-High | Localized congestion | 0.999 |
| load=1.6,bg=24 | 75.774 | Hotspot-High | Localized congestion | 0.990 |
| load=1.6,bg=32 | 78.873 | Hotspot-High | Sustained congestion | 0.951 |
| load=1.8,bg=24 | 85.246 | Hotspot-Severe | Localized congestion | 0.978 |
| load=1.6,bg=40 | 86.524 | Hotspot-Severe | Sustained congestion | 0.919 |
| load=1.8,bg=32 | 88.732 | Hotspot-Severe | Sustained congestion | 0.933 |
| load=2.2,bg=48 | 91.171 | Hotspot-Severe | Sustained congestion | 0.833 |
| load=2.0,bg=24 | 94.717 | Hotspot-Severe | Sustained congestion | 0.952 |
| load=1.8,bg=40 | 97.339 | Hotspot-Severe | Sustained congestion | 0.905 |
| load=2.0,bg=32 | 98.591 | Hotspot-Severe | Sustained congestion | 0.905 |
| load=2.4,bg=48 | 99.459 | Hotspot-Severe | Sustained congestion | 0.797 |
| load=2.6,bg=48 | 107.748 | Hotspot-Overload | Sustained congestion | 0.761 |
| load=2.0,bg=40 | 108.155 | Hotspot-Overload | Sustained congestion | 0.856 |
| load=2.2,bg=32 | 108.450 | Hotspot-Overload | Sustained congestion | 0.872 |
| load=2.8,bg=48 | 116.036 | Hotspot-Overload | Overloaded | 0.742 |
| load=2.4,bg=32 | 118.309 | Hotspot-Overload | Sustained congestion | 0.856 |
| load=2.2,bg=40 | 118.970 | Hotspot-Overload | Sustained congestion | 0.820 |
| load=3.0,bg=48 | 124.324 | Hotspot-Overload | Overloaded | 0.717 |
| load=2.6,bg=56 | 125.398 | Hotspot-Overload | Overloaded | 0.698 |
| load=2.4,bg=40 | 129.786 | Hotspot-Overload | Sustained congestion | 0.802 |
| load=2.8,bg=56 | 135.044 | Hotspot-Overload | Overloaded | 0.670 |
| load=3.0,bg=56 | 144.690 | Hotspot-Overload | Overloaded | 0.641 |

最接近老師指定 percentages 的既有 settings：

| target_percent | setting_id | hotspot_percent | hotspot_label | observed_condition |
| --- | --- | --- | --- | --- |
| 40 | load=1.0,bg=24 | 47.359 | Hotspot-Light | Localized congestion |
| 60 | load=1.2,bg=16 | 60.000 | Hotspot-Moderate | Non-congested |
| 80 | load=1.6,bg=32 | 78.873 | Hotspot-High | Sustained congestion |
| 90 | load=2.2,bg=48 | 91.171 | Hotspot-Severe | Sustained congestion |
| 100 | load=2.4,bg=48 | 99.459 | Hotspot-Severe | Sustained congestion |

PDR 只列在 CSV 與 plots 作 outcome，完全不參與上述 labels 或候選評分。

## 6. Formal candidates

| scenario_id | setting_id | global_offered_isl_load_percent | hotspot_reference_load_percent | hotspot_traffic_load_label | observed_pressure_condition | recommended_for_60s |
| --- | --- | --- | --- | --- | --- | --- |
| H40 | load=1.0,bg=24 | 1.842 | 47.359 | Hotspot-Light | Localized congestion | true |
| H60 | load=1.2,bg=32 | 2.793 | 59.154 | Hotspot-Moderate | Localized congestion | true |
| H80 | load=1.6,bg=32 | 3.725 | 78.873 | Hotspot-High | Sustained congestion | true |
| H90 | load=2.2,bg=48 | 7.028 | 91.171 | Hotspot-Severe | Sustained congestion | true |
| H100+ | load=2.8,bg=48 | 8.944 | 116.036 | Hotspot-Overload | Overloaded | true |

候選使用預先宣告的 hotspot bands、GSL safety 與 observed-pressure
一致性挑選，不依 PDR 高低選點。五點均 `recommended_for_60s=true`，
`recommended_for_200s=false`。

## 7. 是否需要補 simulation

不需要再補 10s calibration 才能建立五級 mapping。Light 的最近點為
47.36%，60%、80%、90% 附近也都有既有點，Overload 有 100% 以上
且 observed condition 為 Overloaded 的候選。若未來要求「精確 40.0%」
而不是 level representative，才需要額外微調點；這不阻擋目前的 60s
formal comparison。

## 8. 新增檔案

- `hotspot_load_mapping.csv`
- `hotspot_vs_global_load_comparison.csv`
- `hotspot_formal_candidate_table.csv`
- `hotspot_mapping_notes.md`
- `analysis_report_zh.md`
- `global_vs_hotspot_load_percent.png`
- `hotspot_load_vs_observed_pressure.png`
- `hotspot_load_vs_pdr_outcome.png`
- `hotspot_load_vs_target_corridor_utilization.png`
- `hotspot_candidate_overview.png`

## 9. 論文敘事建議

### 中文

由於本實驗採用 core-ISL hotspot traffic placement，流量刻意集中於一小段
reference corridor。若以全星座所有 directed ISL capacity 作為分母，
負載比例會被大量未參與該 hotspot 的 links 稀釋。這個 global load 並非
錯誤，而是描述相對於整個 constellation 的資源需求。本文因此同時報告
global offered ISL load 與 hotspot-reference load；前者提供全星座尺度，
後者以相同的 Baseline reference hop demand 除以該 setting 在固定 traffic
window 中實際涉及的 reference ISL subset capacity，作為 hotspot scenario
的主要 x-axis。為避免事後挑選分母，本文固定 reference algorithm、時間窗、
snapshot interval 與 label thresholds，並逐點公開 active-link count，同時
保留 global、fixed-corridor 與 peak-link metrics。PDR 僅作演算法 outcome，
不參與 scenario level definition。

### English

Because the core-ISL hotspot scenario intentionally concentrates traffic on a
limited reference corridor, normalizing offered demand by the capacity of all
directed ISLs in the constellation substantially dilutes the apparent load.
This global metric is not incorrect; it describes demand relative to the full
constellation resource pool. We therefore report both global offered ISL load
and hotspot-reference load. The latter normalizes the same reproducible
Baseline reference-path demand by the capacity of the directed ISL subset
touched during the fixed traffic window and serves as the primary scenario
x-axis. To avoid post-hoc denominator selection, we fix the reference
algorithm, time window, snapshot interval, and load thresholds in advance,
report the active-link count for every setting, and retain global,
fixed-corridor, and peak-link diagnostics. Packet delivery ratio is reported
only as an algorithmic outcome and is never used to define scenario load.

## 10. 下一步建議

只做一件事：使用 `hotspot_formal_candidate_table.csv` 的五個 settings 跑
Baseline、Queue-aware、LoHi、LHTR 四演算法 60s formal experiment。
