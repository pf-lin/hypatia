# 5-Level UDP/PDR 60s Formal Cross-Level Analysis

## 1. 分析範圍

本報告只讀取既有五個 60 秒 formal runs 的 compact comparison CSV；沒有執行
step 1、step 2、step 3，也沒有修改任何 routing algorithm。X 軸固定為
`H40, H60, H80, H90, H100+`。RTT 是 queue-history-based estimated RTT，
不是 packet-level measured RTT。

## 2. Main result

- 五個 level 構成清楚的性能退化曲線。Baseline aggregate PDR 從
  0.8400 降至
  0.2842；Queue-aware 從
  0.9986 降至
  0.7398；LoHi 從
  0.9266 降至
  0.3363；LHTR 從
  0.9989 降至
  0.5052。
- `Baseline < LoHi < LHTR < Queue-aware` 在
  `H60, H80, H90, H100+` 成立。H40 不成立，因為 LHTR
  (0.998926) 略高於 Queue-aware
  (0.998620)，差距只有
  0.031
  percentage points；沒有重複實驗或信賴區間時，不應把這個微小差距解讀成穩定勝出。
- LHTR 相對 LoHi 的最大 aggregate-PDR 改善出現在
  **H80**，為
  **28.93 percentage points**。
- Queue-aware 相對 LHTR 的最大差距出現在
  **H100+**，為
  **23.46 percentage points**。

## 3. RTT interpretation

- Baseline mean RTT 從 386.7 ms 增至
  1356.6 ms，顯示固定路徑上的 queueing
  隨壓力快速累積。
- Queue-aware 維持最低且最平滑的 RTT，從
  196.1 ms 增至
  285.1 ms。
- LHTR 在 H40/H60 與 Queue-aware 接近，但 H80 之後 gap 擴大。它以較高 RTT
  換得顯著優於 LoHi 的 PDR，但沒有達到 Queue-aware 的全域調適效果。
- LoHi mean RTT 從 226.1 ms 增至
  410.5 ms。從現有資料可推論，manager
  路徑約束與較有限的壅塞繞行使部分路徑承受較長 queue delay；這是 queue/path
  association，不能單獨視為 policy 因果證明。

## 4. LHTR diagnostics

- SBR ratio 隨 congestion level 單調增加：H40=0.000664%、
  H60=0.011735%、H80=0.116142%、
  H90=1.000768%、H100+=1.528517%。
- Yellow/red observations 同步大幅增加，方向與 SBR activation 一致。
- 即使 yellow/red 增加，LHTR 仍落後 Queue-aware，因為 SBR 在全部 BR+SBR
  decisions 中仍是少數；`no_alternative_candidate` 與
  `sbr_stretch_too_high` 也是主要 decision reasons，表示偵測壅塞不等於每次
  都有可接受的替代路徑。
- H40 壓力低，BR 已足以維持近乎完整交付，因此 LHTR 與 Queue-aware 幾乎相同；
  其微小領先不宜過度解讀。
- H90/H100+ 中 LHTR 分別比 LoHi 高
  20.02
  與
  16.89
  percentage points，足以支持「LHTR 在 severe/overload 下優於 LoHi」的敘事；
  但同時必須呈現它仍明顯落後 Queue-aware。

## 5. Queue and loss interpretation

- 所有演算法在各 level 的 dominant loss 都是 ISL-saturation-associated loss。
  GSL max queue 僅為低個位數，支持此實驗主要量測 ISL bottleneck。
- `isl_at_capacity_sample_count` 比 max queue 更有資訊量，因為 max ISL queue
  幾乎都會到 100。
- Loss attribution 是 time/path/queue association，不是 physical drop proof；
  因此 attribution proportion 圖列為 diagnostics only。

## 6. Output tiers

### Tier A
- `analysis_report_zh.md` (report): Primary Traditional Chinese interpretation and recommendation.
- `hotspot_5level_cross_level_summary.csv` (table): Canonical 20-row cross-level dataset.
- `tables/aggregate_pdr_across_hotspot_levels.csv` (table): Data table for the primary aggregate-PDR figure.
- `tables/focus_pdr_across_hotspot_levels.csv` (table): Focus-pair delivery comparison.
- `tables/mean_rtt_across_hotspot_levels.csv` (table): Data table for the primary mean-RTT figure.
- `tables/pdr_algorithm_gaps_by_level.csv` (table): Direct LHTR-LoHi and Queue-aware-LHTR PDR gaps.
- `figures/aggregate_pdr_across_hotspot_levels.png` (figure): Primary thesis result: end-to-end delivery degradation and algorithm separation.
- `figures/focus_pdr_across_hotspot_levels.png` (figure): Shows protection of the Johannesburg-Fukuoka focus pair.
- `figures/mean_rtt_across_hotspot_levels.png` (figure): Primary latency comparison and PDR/RTT tradeoff.
- `figures/lhtr_sbr_ratio_across_hotspot_levels.png` (figure): Connects LHTR behavior to increasing congestion.

### Tier B
- `hotspot_5level_algorithm_rankings.csv` (table): Per-level PDR and RTT rankings with an explicitly defined composite.
- `tables/background_pdr_across_hotspot_levels.csv` (table): Background-flow delivery support.
- `tables/p95_rtt_across_hotspot_levels.csv` (table): Tail-latency support.
- `tables/lhtr_diagnostics_across_hotspot_levels.csv` (table): SBR, yellow/red, fallback, and decision-reason support.
- `tables/flow_tail_pdr_across_hotspot_levels.csv` (table): Minimum and fifth-percentile flow PDR support.
- `tables/rtt_components_across_hotspot_levels.csv` (table): Propagation and estimated queueing components.
- `tables/lost_packets_across_hotspot_levels.csv` (table): Absolute lost-packet counts.
- `figures/background_pdr_across_hotspot_levels.png` (figure): Checks whether focus-flow gains are accompanied by background degradation.
- `figures/p95_rtt_across_hotspot_levels.png` (figure): Tail-latency support for the mean RTT result.
- `figures/lost_packets_across_hotspot_levels.png` (figure): Absolute loss magnitude on a logarithmic scale.
- `figures/lhtr_yellow_red_across_hotspot_levels.png` (figure): Supports the SBR activation interpretation; logarithmic count axis.
- `figures/flow_tail_pdr_across_hotspot_levels.png` (figure): Appendix fairness and worst-flow evidence.
- `figures/rtt_components_across_hotspot_levels.png` (figure): Separates path propagation from estimated queueing.

### Tier C
- `tables/isl_at_capacity_samples_across_hotspot_levels.csv` (table): Sample-dependent internal queue-pressure diagnostic.
- `tables/loss_attribution_proportions.csv` (table): Association breakdown; not physical drop proof.
- `hotspot_5level_plot_manifest.csv` (manifest): Machine-readable figure inventory.
- `hotspot_5level_output_catalog.csv` (manifest): Machine-readable tier classification for all final outputs.
- `figures/isl_at_capacity_samples_across_hotspot_levels.png` (figure): Internal congestion diagnostic; counts depend on sampled interfaces and routing paths.
- `figures/loss_attribution_proportions_across_hotspot_levels.png` (figure): Diagnostic association, not physical drop proof.

## 7. Recommendation

1. **Main figure candidate: H80。** 四個演算法排序完整，且 LHTR 相對 LoHi
   改善最大，最適合說明 traffic-light rerouting 的價值。
2. **Stress-test candidate: H100+。** 它最能顯示 overload 下的性能邊界，
   也是 Queue-aware 與 LHTR gap 最大的 level。
3. 建議做 targeted 200s，而不是五個 level 全跑。優先順序是 **H80 first**，
   確認主要敘事在長時間下穩定；資源允許時再跑 **H100+** 作 stress test。
4. 在改 LHTR/LoHi policy 前，應先做更深入的 path/decision diagnostics：
   分析 `no_alternative_candidate`、stretch rejection、SBR 生效時間與 focus-flow
   loss/RTT 的時間對齊。現有結果不足以直接支持 policy 修改。
5. 若只選兩個後續 level，選 **H80 + H100+**。

## 8. Ranking definition

`hotspot_5level_algorithm_rankings.csv` 分別計算 aggregate PDR（高者較佳）、
mean RTT 與 p95 RTT（低者較佳）的 level-internal rank。Composite score 是三個
rank 的等權總和；它只用於摘要，不取代個別 PDR/RTT 指標。

## 9. Limitations

- 每個 scenario 目前只有一個 60s run，沒有重複實驗與 confidence interval。
- BG flow count 在 level 間改變，因此這是一條 formal scenario severity curve，
  不是只改單一連續自變數的 controlled sweep。
- Estimated RTT 包含 replayed path 與 queue history，不能宣稱為封包實測 RTT。
- H40 的 Queue-aware/LHTR 差距太小，需重複或長時間 run 才能判斷穩定性。
