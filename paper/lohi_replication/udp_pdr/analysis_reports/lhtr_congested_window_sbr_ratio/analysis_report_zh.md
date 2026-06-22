# LHTR Congested-Window SBR Ratio Analysis

## 核心結論

原本的 global SBR ratio 會把整個網路中所有 routing decisions 放進分母，其中大多數發生在 green 或非擁塞 context，所以比例會被大量非擁塞決策稀釋。本分析改用固定規則：先以 1 秒 time window 聚合 LHTR traffic-light diagnostics，再用 `Yellow + 2 x Red` 選出每個 scenario 最擁塞的前 25% windows，最後只在這些 windows 內計算 SBR selection ratio。

H80 200s 的 global SBR ratio 是 0.1048%，top-25% congested-window SBR ratio 是 0.1356%；最擁塞的 50/200 個 windows 承載 32.3% 的 SBR decisions。這表示 H80 200s 不是「沒有觸發 SBR」，而是全網平均分母稀釋；SBR 決策集中在 congestion-critical windows。

## 5-Level 60s 對照

| scenario | global | top25 | share |
| --- | --- | --- | --- |
| H40 | 0.0007% | 0.0007% | 25.7% |
| H60 | 0.0117% | 0.0167% | 35.7% |
| H80 | 0.1161% | 0.1415% | 30.5% |
| H90 | 1.0008% | 1.2269% | 30.7% |
| H100+ | 1.5285% | 1.7403% | 28.5% |

主圖位於 `figures/lhtr_top25_congested_window_sbr_ratio.png`。圖中保留 global ratio 作 baseline，並用相同 top-25% rule 比較每個 hotspot level。

## H80 200s 重點

- `global_sbr_ratio_no_fallback`: 0.1048%
- `top25_congested_window_sbr_ratio_no_fallback`: 0.1356%
- `sbr_decision_share_in_top25`: 32.3%
- `top25_window_time_ranges`: 3-5s; 11-13s; 16-18s; 19-21s; 23-27s; 30-31s; 32-34s; 35-38s; 40-42s; 43-45s; 48-52s; 53-54s; 65-66s; 72-73s; 76-78s; 95-96s; 100-104s; 113-116s; 126-127s; 142-143s; 146-148s; 167-168s; 169-170s; 171-172s; 178-181s; 187-188s
- top-25% windows 中有 SBR 的 window 數量：50/50
- LHTR vs LoHi aggregate PDR gain: 28.85 pp
- Queue-aware vs LHTR remaining PDR gap: 6.32 pp
- Mean RTT: LHTR=250.6 ms, LoHi=286.7 ms, Queue-aware=226.1 ms

關於「top 25% most congested windows carry 50.9% of SBR decisions」：50.9% 來自既有 `thesis_readiness_after_h80_200s` 報告：H80 200s 以 0.1s diagnostics rows、decision-summary colored count (`yellow_count + red_count`) 的 top quartile threshold >= 367 選窗；因 tie 包含 502/2000 rows，SBR share=50.9%。 這個值和本任務主規格不同；本任務主規格改成 1s windows、traffic-light link samples、`Yellow + 2 x Red` score，因此 H80 200s 的 primary share 是 32.3%。本報告的 `tables/lhtr_congested_window_sbr_ratio_summary.csv` 會列出所有 scenario/duration 的實際值，H80 200s detailed windows 則在 `tables/h80_200s_congested_windows.csv`。

## 為什麼原圖 ratio 這麼低？

原本 global SBR ratio 的分母包含整個網路中所有 routing decisions，其中大多數發生在非擁塞區域或 green 狀態。因此，雖然 SBR 在局部壅塞時有觸發，但在全網統計下會被大量非擁塞決策稀釋。

## 新圖如何修正？

新圖只針對 traffic-light signal 最強的前 25% 時窗計算 SBR ratio。這些時窗代表 LHTR 實際偵測到 congestion 的主要區段，因此更能反映 SBR decision 是否在需要時被啟用。Top window 的 congestion score 只使用 `lhtr_traffic_light_color_summary.csv` 中的 yellow/red link samples；BR/SBR/fallback counts 則來自 `lhtr_br_sbr_summary.csv`。

## 如何避免 cherry-picking？

1. top 25% rule 是固定比例，不是人工挑時間點。
2. congestion score 只使用 yellow/red traffic-light signal，不使用 PDR。
3. 所有 scenarios 使用相同 rule：`Yellow + 2 x Red`，排序 tie-breaker 為 score desc, red desc, yellow desc, time asc。
4. 同時保留 global ratio 作 baseline comparison。
5. 輸出所有 H80 200s windows 的 CSV，包含是否被選入 top 25%，可重現。

## 如何解釋 LHTR 效能改善？

LHTR 的改善不需要來自大量全網 SBR switching，而是來自於在少數關鍵擁塞時窗與 bottleneck corridor 中，將部分 traffic 從主要 BR path 切換到替代 SBR path。由於 hotspot loss 往往由少數關鍵 links 或 time windows 主導，即使全域 SBR ratio 很低，若 SBR decision 集中在 congestion-critical windows，仍可能帶來明顯 PDR / RTT 改善。

H80 200s 中，LHTR aggregate PDR=0.9000，LoHi=0.6114，Queue-aware=0.9631；LHTR 比 LoHi 高 28.85 pp，但仍距 Queue-aware 6.32 pp。RTT 上 LHTR mean RTT=250.6 ms，低於 LoHi 的 286.7 ms，但高於 Queue-aware 的 226.1 ms。

## Sensitivity

Primary top-25% rule 與 `Yellow + Red` top-25% 的 overlap 為 90.0%，與 `Red only` top-25% 的 overlap 為 70.0%。若後續要更細緻區分 bottleneck corridor，可把 focus-flow/corridor-only SBR ratio 作為 diagnostics-only future work；目前資料已足夠支持 time-window concentration 的重畫圖。
