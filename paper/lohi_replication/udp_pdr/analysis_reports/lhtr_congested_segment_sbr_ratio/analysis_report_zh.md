# LHTR 壅塞 corridor segment SBR ratio 分析

## 1. 任務範圍

本次分析改用 corridor segment 作為分母：先找出 target corridor 上最壅塞的 directed ISL segments，再統計 BR path 會經過這些 segments 的 LHTR 決策裡，最後選 SBR 的比例。

本分析沒有重新執行 ns-3，也沒有修改 LHTR routing algorithm；所有結果都來自既有 formal run 輸出。

## 2. 壅塞 segment 定義

- Candidate segments：`isl_corridor_load_summary.csv` 中 `on_target_focus_corridor=true` 的 directed ISL edges。
- 壅塞分數：`algorithm_lhtr/logs_ns3/isl_utilization.csv` 在 traffic window 內的 weighted p95 utilization。
- Top segments：依 p95 utilization 由高到低取 `--top-fraction`，預設為 top 25%。
- 平手排序：mean utilization、max utilization、排程估計 load ratio、red/yellow sample count。

## 3. 決策分母定義

- Formal global ratio：來自 `lhtr_br_sbr_summary.csv` 的全部 LHTR decision counter。
- Sample global ratio：來自 `lhtr_br_sbr_decision_log.csv` 的診斷樣本。
- Target corridor ratio：BR path intersect 任一 target corridor segment 的診斷樣本。
- Top25 segment ratio：BR path intersect 任一 top congested segment 的診斷樣本，這是本次主分母。
- Selected-path top25 ratio：selected path intersect top congested segment 的輔助分母。
- BR-or-selected top25 ratio：BR path 或 selected path 任一者 intersect top congested segment 的輔助分母。

## 4. 主要結果

H80 200s 的核心數字如下：

| 分母 | SBR ratio | 決策數 |
|---|---:|---:|
| Formal global | 0.105% | 265031557 |
| Sample global | 2.779% | 10000000 |
| Target corridor by BR path | 13.927% | 840805 |
| Top25 congested segments by BR path | 13.530% | 515017 |
| Selected path intersects top25 | 12.180% | 507102 |
| BR or selected path intersects top25 | 18.134% | 543986 |

H80 200s 的 top segment 數量為 13 / 50；top segments 為 `176->136;135->175;175->135;136->176;135->95;95->135;96->136;136->96;55->95;15->55;643->683;603->643;644->684`。

跨負載摘要如下；這裡只列 60s 的五個 Hotspot scenario，H80 200s 不放進跨負載趨勢圖。

| Scenario | Global | Target Corridor |
|---|---:|---:|
| H40 | 0.001% | 0.330% |
| H60 | 0.012% | 3.117% |
| H80 | 0.116% | 14.679% |
| H90 | 1.001% | 43.260% |
| H100+ | 1.529% | 49.387% |

## 5. 為什麼 segment 分母仍可能不高

若 top25 segment ratio 仍然偏低，代表 LHTR 的 SBR 選擇並不只是由「BR path 是否穿過最壅塞 corridor segment」決定。從 log 欄位來看，常見限制包括：BR/SBR 兩條候選路徑的 traffic-light 顏色同時是 GREEN、SBR stretch 或 score 沒有優勢、或當下沒有 admissible SBR candidate。

換句話說，這個分析縮小了分母，但仍然保留 LHTR 原始決策邏輯；它不能把「路徑碰到壅塞 segment」自動解讀成「必然要選 SBR」。

## 6. `SBR share on top segments` 與 `SBR ratio` 的差異

- `SBR ratio` 是條件機率：在某個分母內，有多少比例的決策選了 SBR。例如 top25 segment ratio = top25 segment 相關決策中的 SBR / top25 segment 相關決策總數。
- `SBR share on top segments` 是集中度：所有 SBR 決策中，有多少比例落在 top25 segments 相關分母內。

因此 share 高不代表該分母內 SBR ratio 高；它只表示 SBR 決策是否集中在那些 segments 上。

## 7. 100ms window 與 segment 分析的關係

100ms window 會讓時間定位更細，但它仍然是時間分母；本分析改成 path/segment 分母，回答的是另一個問題：決策的 BR path 是否真的穿過壅塞 corridor。若要比較 1s 與 100ms，建議把它作為輔助圖，而不是取代 segment 分母。

## 8. 產出檔案

- `tables/lhtr_congested_segment_sbr_ratio_summary.csv`
- `tables/h80_200s_top_congested_segments.csv`
- `tables/h80_200s_congested_segment_decision_samples.csv`
- `figures/lhtr_sbr_ratio_by_denominator_across_levels.png`
- `figures/lhtr_global_vs_target_corridor_sbr_ratio_60s_hotspot_levels.png`
- `figures/h80_200s_sbr_ratio_by_denominator.png`
- `figures/h80_200s_top_congested_segments_sbr_ratio.png`
- `figures/h80_200s_sbr_decision_concentration_on_segments.png`

## 9. 注意事項

`lhtr_br_sbr_decision_log.csv` 是 diagnostic sample log；因此 segment-specific ratio 是 sample-based。報告同時列出 formal global ratio 與 sample global ratio，避免把不同來源的分母誤讀為同一個母體。
