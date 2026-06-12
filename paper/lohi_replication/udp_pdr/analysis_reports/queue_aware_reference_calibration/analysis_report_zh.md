# Queue-aware-reference ISL-focused Calibration 分析報告

日期：2026-06-12

## 1. 總結結論

- Queue-aware-reference calibration 已成功執行，共涵蓋 30 個 10 秒 settings。
- scenario congestion level 完全由 Queue-aware 的同 setting 實測結果決定；Baseline 只用於 improvement-space 驗證。
- 現行「只看全體 active-link p95」的 mapping 只產生 `Light` 與 `Moderate`，但這不代表實驗沒有進入 High、Severe 或 Overload。
- 30 點結果證明現行 p95 門檻失去高壓力辨識力：最高 p95 僅 `0.567`，但 Queue-aware PDR 已降到 `0.641`，且出現跨越大部分 traffic window 的 ISL queue saturation。
- 正式候選為 `Light: 1.0x/bg16`、`Moderate: 2.0x/bg40`。
- 兩個候選的 Baseline 都是 `Overload`，且 `improvement_space=true`。
- 所有 Queue-aware settings 均為 `GSL bottleneck=false`、`safe_for_isl_focused_experiment=true`。
- 不建議繼續增加 load 或 background-flow count。下一步應先重新定義 congestion level，再用既有 30 點重做 mapping。

最高壓力點 `3.0x/bg56` 的 Queue-aware `p95=0.567`、target-corridor p95 `0.712`、PDR `0.641`，現行輸出仍標為 Moderate。高負載時 active directed ISLs 從 `481` 增加到 `2,879/2,880`，Queue-aware 幾乎啟用整個 ISL network；全體 active-link p95 的母體同步擴大，因此大量低 utilization 的繞行鏈路會稀釋局部壅塞。這是指標結構問題，不是 load 還不夠高。

## 2. 執行的 Commands

既有 `1.0x/bg16` 結果直接重用；其餘實際使用的主要 commands 如下：

```bash
cd paper/lohi_replication/udp_pdr

python run_isl_focused_calibration_sweep.py \
  --algorithms algorithm_queue_aware_over_isls \
  --src-node-id 754 --dst-node-id 785 \
  --isl-data-rate-megabit-per-s 10 \
  --gsl-data-rate-megabit-per-s 100 \
  --duration-s 10 --traffic-stop-s 8 \
  --per-flow-rate-reference-background-flow-count 4 \
  --load-levels 1.2 1.4 --background-flow-counts 16 --force

python run_isl_focused_calibration_sweep.py \
  --algorithms algorithm_queue_aware_over_isls \
  --src-node-id 754 --dst-node-id 785 \
  --isl-data-rate-megabit-per-s 10 \
  --gsl-data-rate-megabit-per-s 100 \
  --duration-s 10 --traffic-stop-s 8 \
  --per-flow-rate-reference-background-flow-count 4 \
  --load-levels 1.0 1.2 1.4 --background-flow-counts 24 --force

python run_isl_focused_calibration_sweep.py \
  --algorithms algorithm_queue_aware_over_isls \
  --src-node-id 754 --dst-node-id 785 \
  --isl-data-rate-megabit-per-s 10 \
  --gsl-data-rate-megabit-per-s 100 \
  --duration-s 10 --traffic-stop-s 8 \
  --per-flow-rate-reference-background-flow-count 4 \
  --load-levels 1.0 1.2 1.4 --background-flow-counts 32 --force

python run_isl_focused_calibration_sweep.py \
  --algorithms algorithm_queue_aware_over_isls \
  --src-node-id 754 --dst-node-id 785 \
  --isl-data-rate-megabit-per-s 10 \
  --gsl-data-rate-megabit-per-s 100 \
  --duration-s 10 --traffic-stop-s 8 \
  --per-flow-rate-reference-background-flow-count 4 \
  --load-levels 1.6 1.8 2.0 \
  --background-flow-counts 24 32 40 --force

python run_isl_focused_calibration_sweep.py \
  --algorithms algorithm_queue_aware_over_isls \
  --src-node-id 754 --dst-node-id 785 \
  --isl-data-rate-megabit-per-s 10 \
  --gsl-data-rate-megabit-per-s 100 \
  --duration-s 10 --traffic-stop-s 8 \
  --per-flow-rate-reference-background-flow-count 4 \
  --load-levels 2.2 2.4 \
  --background-flow-counts 32 40 48 --force

python run_isl_focused_calibration_sweep.py \
  --algorithms algorithm_queue_aware_over_isls \
  --src-node-id 754 --dst-node-id 785 \
  --isl-data-rate-megabit-per-s 10 \
  --gsl-data-rate-megabit-per-s 100 \
  --duration-s 10 --traffic-stop-s 8 \
  --per-flow-rate-reference-background-flow-count 4 \
  --load-levels 2.6 2.8 3.0 \
  --background-flow-counts 48 56 --force

python run_isl_focused_calibration_sweep.py \
  --algorithms algorithm_free_one_only_over_isls \
  --src-node-id 754 --dst-node-id 785 \
  --isl-data-rate-megabit-per-s 10 \
  --gsl-data-rate-megabit-per-s 100 \
  --duration-s 10 --traffic-stop-s 8 \
  --per-flow-rate-reference-background-flow-count 4 \
  --load-levels 2.0 --background-flow-counts 40 --force

python step_3_generate_plots.py \
  --traffic-mode core_isl_hotspot_specific \
  --load-level 2.0 \
  --algorithms algorithm_free_one_only_over_isls \
               algorithm_queue_aware_over_isls \
  --src-node-id 754 --dst-node-id 785 \
  --simulation-end-time-s 10 --traffic-stop-time-s 8 \
  --isl-data-rate-megabit-per-s 10 \
  --gsl-data-rate-megabit-per-s 100 \
  --background-flow-count 40 \
  --per-flow-rate-reference-background-flow-count 4 \
  --no-rtt-analysis

python analyze_isl_focused_calibration.py \
  --traffic-mode core_isl_hotspot_specific \
  --load-level 1.0 1.2 1.4 1.6 1.8 2.0 2.2 2.4 2.6 2.8 3.0 \
  --algorithms algorithm_free_one_only_over_isls \
               algorithm_queue_aware_over_isls \
  --src-node-id 754 --dst-node-id 785 \
  --simulation-end-time-s 10 --traffic-stop-time-s 8 \
  --isl-data-rate-megabit-per-s 10 \
  --gsl-data-rate-megabit-per-s 100 \
  --background-flow-count 16 24 32 40 48 56 \
  --per-flow-rate-reference-background-flow-count 4 \
  --no-rtt-analysis
```

Runner 的實際 CLI 沒有 task 範例中的 `--traffic-mode`、`--simulation-end-time-s` 與單數 `--background-flow-count`，因此 sweep commands 使用其實際參數 `--duration-s`、`--traffic-stop-s` 與 `--background-flow-counts`；runner 內部固定產生本任務的 ISL-focused traffic mode。

## 3. Queue-aware-reference Results

| setting | QA p95 ISL | QA max ISL | QA target p95 | QA PDR | scenario | GSL bottleneck | safe |
|---|---:|---:|---:|---:|---|---|---|
| 1.0x / 16 | 0.339 | 0.550 | 0.445 | 1.000 | Light | false | true |
| 1.2x / 16 | 0.381 | 0.599 | 0.508 | 1.000 | Light | false | true |
| 1.4x / 16 | 0.379 | 0.644 | 0.523 | 0.999 | Light | false | true |
| 1.0x / 24 | 0.371 | 0.617 | 0.541 | 0.999 | Light | false | true |
| 1.2x / 24 | 0.399 | 0.670 | 0.547 | 0.996 | Light | false | true |
| 1.4x / 24 | 0.398 | 0.661 | 0.515 | 0.992 | Light | false | true |
| 1.6x / 24 | 0.403 | 0.692 | 0.537 | 0.990 | Light | false | true |
| 1.8x / 24 | 0.415 | 0.730 | 0.510 | 0.978 | Light | false | true |
| 2.0x / 24 | 0.440 | 0.702 | 0.576 | 0.952 | Light | false | true |
| 1.0x / 32 | 0.370 | 0.635 | 0.496 | 0.994 | Light | false | true |
| 1.2x / 32 | 0.417 | 0.636 | 0.542 | 0.986 | Light | false | true |
| 1.4x / 32 | 0.413 | 0.680 | 0.537 | 0.971 | Light | false | true |
| 1.6x / 32 | 0.443 | 0.700 | 0.555 | 0.951 | Light | false | true |
| 1.8x / 32 | 0.450 | 0.770 | 0.567 | 0.933 | Light | false | true |
| 2.0x / 32 | 0.470 | 0.785 | 0.586 | 0.905 | Light | false | true |
| 2.2x / 32 | 0.482 | 0.829 | 0.614 | 0.872 | Light | false | true |
| 2.4x / 32 | 0.491 | 0.795 | 0.618 | 0.856 | Light | false | true |
| 1.6x / 40 | 0.458 | 0.768 | 0.580 | 0.919 | Light | false | true |
| 1.8x / 40 | 0.478 | 0.790 | 0.604 | 0.905 | Light | false | true |
| 2.0x / 40 | 0.502 | 0.776 | 0.607 | 0.856 | Moderate | false | true |
| 2.2x / 40 | 0.507 | 0.869 | 0.633 | 0.820 | Moderate | false | true |
| 2.4x / 40 | 0.519 | 0.973 | 0.646 | 0.802 | Moderate | false | true |
| 2.2x / 48 | 0.519 | 0.819 | 0.665 | 0.833 | Moderate | false | true |
| 2.4x / 48 | 0.521 | 0.893 | 0.656 | 0.797 | Moderate | false | true |
| 2.6x / 48 | 0.531 | 0.863 | 0.684 | 0.761 | Moderate | false | true |
| 2.8x / 48 | 0.530 | 0.912 | 0.705 | 0.742 | Moderate | false | true |
| 3.0x / 48 | 0.548 | 0.920 | 0.705 | 0.717 | Moderate | false | true |
| 2.6x / 56 | 0.544 | 0.937 | 0.708 | 0.698 | Moderate | false | true |
| 2.8x / 56 | 0.557 | 0.920 | 0.738 | 0.670 | Moderate | false | true |
| 3.0x / 56 | 0.567 | 0.894 | 0.712 | 0.641 | Moderate | false | true |

### 3.1 30 點趨勢診斷

| 指標 | 低壓力 | 最高壓力 | 解讀 |
|---|---:|---:|---|
| total offered rate | 30 Mbps | 290 Mbps | 增加約 9.7 倍 |
| active directed ISLs | 481 | 2,879 / 2,880 | Queue-aware 幾乎擴散到全網 |
| global active-link p95 | 0.339 | 0.567 | 只增加 0.228，出現明顯壓縮 |
| global active-link p99 | 0.429 | 0.692 | 仍未跨入現行 High |
| target-corridor p95 | 0.445 | 0.712 | 比 global p95 更能反映壓力 |
| aggregate PDR | 1.000 | 0.641 | 已有 35.9% packet loss |
| minimum flow PDR | 1.000 | 0.395 | tail flow 已嚴重失效 |
| ISL capacity samples | 0 | 41,915 | 飽和事件大量增加 |
| GSL capacity samples | 0 | 0 | 排除 GSL bottleneck |

在 `2.6x/bg56`，aggregate PDR 已降至 `0.698`；650 個 ISL interfaces 曾達 queue capacity，其中 157 個的 first/last saturation span 超過 4 秒。到了 `3.0x/bg56`，相應數字增至 770 與 192。這符合「Queue-aware begins sustained saturation/loss」的 Overload 敘述，即使 global p95 沒有達到 1.0。

### 3.2 為何不應繼續盲目加壓

1. global p95 與 offered rate 雖有相關性，但其數值被路徑擴散壓縮，無法產生原先預設的 `0.70–1.00` High/Severe bands。
2. 新增 load 已主要表現在 packet loss、滿 queue interfaces 與 route churn，而不是 global p95。
3. 高壓力 run 已觸發 satellite-originated ICMP，顯示動態路由 transient loop 出現；再加壓會混入更多 routing-instability effect。
4. GSL 始終沒有飽和，因此觀察到的 degradation 確實是 ISL-focused，不需要更高 load 來證明 bottleneck 類型。

## 4. Baseline Improvement-space Results

| setting | scenario | Baseline PDR | Baseline p95 ISL | Baseline outcome | improvement_space |
|---|---|---:|---:|---|---|
| 1.0x / 16 | Light | 0.788 | 1.000 | Overload | true |
| 2.0x / 40 | Moderate | 0.392 | 1.000 | Overload | true |

Baseline 在 Light setting 已因 shortest-path concentration 過載；這不會把 scenario 改標為 Overload。Moderate setting 中 Queue-aware PDR 為 `0.856`，比 Baseline 高約 `0.464`。

## 5. Scenario Recommendations

### 5.1 現行 p95-only mapping

| scenario | load | bg | QA p95 | QA PDR | Baseline PDR | safe | reason |
|---|---:|---:|---:|---:|---:|---|---|
| Light | 1.0 | 16 | 0.339 | 1.000 | 0.788 | true | 低壓力、無 QA loss，且 Baseline 已顯示 improvement space |
| Moderate | 2.0 | 40 | 0.502 | 0.856 | 0.392 | true | 最低 load/bg 的 Moderate，避免選擇更極端且 QA PDR 更低的點 |

候選安全檢查：

| setting | max GSL proxy | GSL full samples | GSL-associated loss | mixed loss ratio | target active | safe |
|---|---:|---:|---:|---:|---|---|
| 1.0x / 16 | 0.01 | 0 | 0 | 0.000 | true | true |
| 2.0x / 40 | 0.03 | 0 | 0 | 0.000 | true | true |

GSL utilization 是 queue-occupancy proxy，不是 measured throughput；ISL utilization 則來自 measured throughput。

### 5.2 建議的新 composite mapping

scenario 仍由 Queue-aware reference 定義，但不再只看 global p95。先通過 safety gate：

```text
Queue-aware result exists
GSL bottleneck = false
mixed loss does not dominate
target corridor is active
```

再分別計算 delivery-loss band 與 ISL-pressure band，最後取較嚴重者。

Delivery-loss band：

```text
Light:    PDR >= 0.99
Moderate: 0.95 <= PDR < 0.99
High:     0.85 <= PDR < 0.95
Severe:   0.70 <= PDR < 0.85
Overload: PDR < 0.70
```

ISL-pressure band：

```text
Light:
  target-corridor p95 < 0.60 and links_over_80 = 0

Moderate:
  target-corridor p95 >= 0.60 or links_over_80 >= 1

High:
  target-corridor p95 >= 0.70 or links_over_80 >= 6
  or links_over_90 >= 1

Severe:
  target-corridor p95 >= 0.80 or links_over_80 >= 15
  or links_over_90 >= 3

Overload override:
  PDR < 0.70 or links_over_100 >= 3
  or clearly sustained ISL saturation/loss
```

這個 mapping 套用既有 30 點後，可得到：

| proposed scenario | settings 數 | 建議代表點 | QA PDR | target p95 | 理由 |
|---|---:|---|---:|---:|---|
| Light | 7 | 1.0x / 16 | 1.000 | 0.445 | 無 loss、無高 utilization links |
| Moderate | 6 | 1.8x / 24 | 0.978 | 0.510 | 約 2.2% loss，仍維持大部分 delivery |
| High | 7 | 2.0x / 32 | 0.905 | 0.586 | 約 9.5% loss，tail flow 已明顯下降 |
| Severe | 7 | 2.4x / 40 | 0.802 | 0.646 | 約 19.8% loss，局部 max 0.973 |
| Overload | 3 | 2.8x / 56 | 0.670 | 0.738 | 33% loss、22 條 links over 80% |

這些是待驗證的 operational bands，不應直接視為 routing-independent capacity。

## 6. Calibration Coverage

- 現行 p95-only mapping：只有 Light、Moderate。
- 建議 composite mapping：既有 30 點已涵蓋 Light、Moderate、High、Severe、Overload。
- `2.6x/bg56` 起 PDR 低於 0.70，已滿足具體化後的 sustained-loss Overload。
- 不需要再增加 load/bg 尋找 High/Severe；需要的是驗證 mapping 的穩定性與可重現性。
- 在 mapping 定案前，不宜直接啟動四演算法 60 秒 full sweep。

## 7. Updated CSV / Plots

聚合輸出位於：

```text
runs/comparison_calibration/src754_dst785_isl10mbps_gsl100mbps_10s/
```

主要檔案：

- `isl_focused_scenario_summary.csv`
- `isl_focused_calibration_summary.csv`
- `isl_focused_calibration_by_algorithm.csv`
- `isl_gsl_bottleneck_check.csv`
- `congestion_level_mapping.csv`
- `formal_scenario_recommendations.csv`
- `algorithm_congestion_outcomes.png`
- `congestion_level_summary.png`
- `gsl_vs_isl_saturation.png`
- `isl_utilization_vs_pdr.png`

## 8. 論文敘事建議

中文：本文以 Queue-aware routing 在相同 traffic setting 下的實測壓力與 delivery outcome 作為 scenario congestion level 的 adaptive reference anchor。Baseline shortest-path routing 的結果只用來判斷是否存在可改善空間，不參與 scenario label 的定義。此標定不是與 routing 無關的網路容量上限，也不假設 Queue-aware 在任意負載下都是理想演算法；高壓力下觀察到的 sustained loss 與 transient route instability 仍屬於 reference outcome 的一部分。

English: We define each scenario congestion level using the measured pressure and delivery outcome of Queue-aware routing under the same traffic setting. The shortest-path Baseline is used only as an improvement-space indicator and does not determine the scenario label. This calibration is neither a routing-independent capacity bound nor an assumption that Queue-aware remains ideal at arbitrary load; sustained loss and transient route instability at high pressure are part of the observed reference outcome.

## 9. 下一步建議

只執行一個下一步：先不要再增加 load/bg；先將 scenario label 改為「Queue-aware delivery-loss band 與 ISL-pressure band 取較嚴重者」的 composite mapping，使用既有 30 點重新產生 labels 與 formal candidates。完成這一步後，再用較長 duration 或多 seed 驗證候選穩定性。
