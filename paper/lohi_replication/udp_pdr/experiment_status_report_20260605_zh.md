# UDP/PDR 實驗進度報告

日期：2026-06-05

## 1. 報告摘要

目前最適合向老師報告的主結果，是 `runs/` 中的 60 秒
`core_isl_hotspot_specific` 實驗：

- 2 條 focus flows，加上 24 條 background flows。
- 每條 flow 的 target rate 為 3 Mbps，總 target rate 為 78 Mbps。
- traffic 在 58 秒停止，模擬到 60 秒，保留 2 秒 drain time。
- traffic selector 將 background traffic 集中到 focus middle-ISL corridor。
- 最重 target ISL 的估計 offered load 是 capacity 的 2.7 倍。

在這個案例中：

| Algorithm | Aggregate PDR | Focus-flow PDR | Lost packets | PDR < 0.9 flows | Jain fairness |
|---|---:|---:|---:|---:|---:|
| Free-one-only / static baseline | 56.96% | 33.23% | 162,252 | 17 | 0.7301 |
| Queue-aware | **98.93%** | **96.44%** | **4,040** | **0** | **0.9997** |
| LoHi | 82.58% | 83.39% | 65,680 | 17 | 0.9641 |
| LHTR | 95.24% | 89.30% | 17,959 | 6 | 0.9917 |

相對 static baseline：

| Algorithm | Aggregate PDR gain | Focus PDR gain | Packet-loss reduction |
|---|---:|---:|---:|
| Queue-aware | **+41.97 percentage points** | **+63.21 points** | **97.51%** |
| LoHi | +25.62 points | +50.16 points | 59.52% |
| LHTR | +38.27 points | +56.07 points | 88.93% |

目前可以下的最強結論是：

> 在目前這個刻意集中於 middle-ISL corridor 的單一 60 秒壅塞案例中，
> Queue-aware 的 packet delivery、focus-flow protection 與 fairness 最好；
> LHTR 次之，但仍明顯優於 static baseline 與 LoHi。

若把 Queue-aware 視為使用全網 queue 狀態、每 100 ms 重算全域 SPF 的
global-information reference，LHTR 已取得 Queue-aware 相對 static PDR 改善量的
**91.2%**：

`(95.24 - 56.96) / (98.93 - 56.96) = 91.2%`

這是目前比「LHTR 已經勝過 Queue-aware」更準確、也更能站得住腳的研究表述。

這是「特定案例中的清楚排序」，還不是跨 seed、跨時間窗的統計性結論。

## 2. 目前主案例的流量設計

主案例不是單純增加總流量，而是刻意讓 background flows 經過 focus flows
的 middle-ISL corridor：

| Traffic-selection metric | Value |
|---|---:|
| Background flows | 24 |
| Non-zero-overlap background flows | 22 |
| Zero-overlap fallback flows | 2 |
| Average middle-ISL overlap score | 13.33 |
| Target-corridor maximum load ratio | **2.7x** |
| Top non-focus edge load ratio | 1.8x |
| Top loaded edge on target corridor | Yes |

這代表目前案例確實成功製造出很強的 target-corridor pressure。不過 selector
為了湊足 24 條 background flows，使用了數個 relaxation phase：

- 4 條 strict。
- 4 條放寬 per-source/per-destination limit。
- 4 條放寬 endpoint 與 satellite-interface cap 到 GSL capacity。
- 10 條放寬 edge-conflict 條件。
- 2 條最後使用 zero-overlap fallback。

因此此案例可稱為「高度集中、能拉開演算法差異的壓力測試」，但不能稱為完全
符合所有 strict selector constraints 的純粹 ISL-only bottleneck。

## 3. Focus-flow 結果

兩個方向的 focus-flow 表現不對稱：

| Algorithm | 738 -> 793 PDR | 793 -> 738 PDR | Mean focus PDR |
|---|---:|---:|---:|
| Static baseline | 19.02% | 47.44% | 33.23% |
| Queue-aware | **99.96%** | **92.92%** | **96.44%** |
| LoHi | 91.36% | 75.42% | 83.39% |
| LHTR | 99.97% | 78.63% | 89.30% |

可報告的觀察：

- Queue-aware 對兩個方向都提供最穩定的保護。
- LHTR 在 `738 -> 793` 幾乎無 loss，但 `793 -> 738` 仍有明顯退化。
- LoHi 的兩個方向都比 static 好，但弱於 Queue-aware 與 LHTR。
- 路由效果有方向性，不能只看兩條 focus flows 的平均值。

## 4. Per-flow 公平性

Aggregate PDR 之外，Queue-aware 的 tail performance 也最好：

| Algorithm | Median flow PDR | P5 flow PDR | Minimum flow PDR |
|---|---:|---:|---:|
| Static baseline | 60.97% | 12.17% | 4.95% |
| Queue-aware | **99.83%** | **95.98%** | **92.92%** |
| LoHi | 84.82% | 58.34% | 37.21% |
| LHTR | 99.93% | 76.78% | 75.10% |

Queue-aware 不只是提高平均 PDR，也消除了極差 flow：26 條 flows 中沒有任何
一條低於 0.9 PDR。

## 5. 實驗批次演進

### 5.1 早期 `core_hotspot_specific` load sweep

`runs_backup_before_60s_sweep_*` 與 `runs_backup_30s_60s_*` 是早期 10/30/60 秒、
尚未統一 drain time 的探索結果。

主要趨勢：

- 1.1x 以下四種演算法都接近 100% PDR。
- 約 1.3x 開始出現 static baseline 的明顯退化。
- 1.4x 時 static 約 87.9%，動態演算法約 99.8%。
- 1.6x 時 static 約 79.0%，Queue-aware、LoHi、LHTR 約 95.5% 到 95.7%。

這組結果最適合用來說明：

> 當負載跨過壅塞門檻後，動態路由相對 static routing 的優勢開始出現。

但這個 traffic mode 可能混合 ISL 與 access-side effects，不應當作乾淨
ISL bottleneck 的最終證據。

### 5.2 Drain-time validation

`runs_backup_drain_time_*` 驗證 2 秒 drain time 的必要性。以 1.6x、60 秒為例：

| Algorithm | No-drain loss | 2s-drain loss | Reduced tail loss |
|---|---:|---:|---:|
| Static baseline | 16,835 | 15,871 | 964 |
| Queue-aware | 3,583 | 3,189 | 394 |
| LoHi | 3,538 | 3,169 | 369 |
| LHTR | 3,436 | 3,071 | 365 |

Drain time 會移除部分 simulation-end in-flight loss，但不會消除持續壅塞造成的
演算法差異。因此後續 60 秒實驗採用 stop 58 秒、end 60 秒是合理的。

### 5.3 `core_isl_hotspot_specific` with 4 background flows

`runs_backup_isl_hotspot_bf4_*` 使用較乾淨的 ISL-hotspot selector，但只有
4 條 background flows。

- 1.2x 到 2.0x 幾乎全部 100% PDR。
- 2.4x 與 2.8x 主要是 LoHi 先出現退化。
- 到 3.2x，static 與 LoHi 約 95%，Queue-aware 與 LHTR 仍為 100%。

這批結果顯示：只用 4 條 background flows 不容易形成穩定、能區分演算法的
壅塞案例。後續改成固定 per-flow rate，再掃 background-flow count 是必要的。

### 5.4 Background-flow-count sweep

`runs_backup_bg_1p4_1p8_*` 在 1.8x、每 flow 3 Mbps 下掃 8、16、32、64 條
background flows：

| Background flows | Static | Queue-aware | LoHi | LHTR |
|---:|---:|---:|---:|---:|
| 8 | 100.00% | 100.00% | 97.79% | 100.00% |
| 16 | 100.00% | 100.00% | 98.77% | 100.00% |
| 32 | 94.04% | 96.60% | 94.56% | **97.01%** |
| 64 | 89.23% | **97.07%** | 87.85% | 96.36% |

舊版 selector 下，壅塞轉折大約位於 16 到 32 條 background flows 之間。

`runs_backup_transition_1p8_bg20_24_28_*` 再縮小範圍：

| Background flows | Static | Queue-aware | LoHi | LHTR |
|---:|---:|---:|---:|---:|
| 20 | 100.00% | 100.00% | 98.28% | 100.00% |
| 24 | 96.93% | 100.00% | 98.57% | 100.00% |
| 28 | 95.15% | 97.79% | 96.57% | 97.79% |

這批結果找到「開始出現差異」的背景流量區間，但舊 selector 選到的 flows
較分散，24 flows 仍不足以形成強壓力。

### 5.5 Flow-selection improvement

`runs_backup_flow_selection_improvements_*` 和目前 `runs/` 使用相同的實際
source/destination flow pairs；目前 `runs/` 重新產生了 metadata 並完整重跑。

新版選擇把 22/24 條 background flows 放到 non-zero-overlap corridor，將
target edge 推到 2.7x capacity。相同 24 條 background flows 下，static PDR
從舊 transition case 的 96.93% 降到目前的 56.96%，證明：

> Background-flow count 不是唯一控制量；flow placement 與 corridor
> concentration 對案例難度的影響更大。

### 5.6 10-second loss-attribution diagnostic run

`runs_backup_loss_attribution_diagnostics_10s_*` 是新 tracing/analysis 的 smoke run：

| Algorithm | 10s aggregate PDR | 60s aggregate PDR |
|---|---:|---:|
| Static baseline | 72.56% | 56.96% |
| Queue-aware | 96.66% | 98.93% |
| LoHi | 76.94% | 82.58% |
| LHTR | **97.53%** | 95.24% |

10 秒與 60 秒都顯示 Queue-aware/LHTR 明顯領先，但兩者的名次與精確數值會隨
時間窗改變。因此 10 秒結果只適合驗證工具與快速觀察，不適合當正式 ranking。

### 5.7 200-second dirty run

`runs_backup_1p8_bg_24_200s_dirty_*` 的結果為：

| Algorithm | Aggregate PDR | Focus-flow PDR |
|---|---:|---:|
| Static baseline | 77.89% | 100.00% |
| Queue-aware | **99.96%** | 100.00% |
| LoHi | 64.17% | 96.04% |
| LHTR | 95.61% | 99.80% |

這批資料仍支持 Queue-aware 最佳、LHTR 次佳，但資料夾已明確標記為 `dirty`，
而且結果和目前 60 秒案例呈現很強的時間/版本差異。它可作為「長時間行為值得
再跑」的證據，不應直接和目前 60 秒結果合併成正式 duration comparison。

## 6. 為什麼 Queue-aware 在目前案例勝過 LHTR

### 6.1 兩者不是同一資訊範圍的演算法

| Mechanism | Queue-aware | Current LHTR |
|---|---|---|
| Queue-weighted region | 全部 ISLs | 只有 PID/group 內 ISLs |
| Inter-group decision | 全網 queue-weighted SPF | 先由 group graph 決定 `next_pid` |
| Group-edge cost | N/A | 主要是 hop/link-count proxy，不含即時 queue |
| Border choice | 全域 SPF 自然決定 | 只能在既定 `src_pid -> next_pid` 邊界內重排 |
| Undirected-edge queue | 取雙向 queue 最大值 | 目前只取第一個找到的方向 |
| GSL congestion input | 未使用 | 未使用 |

因此 Queue-aware 可以在整張圖考慮壅塞 detour；LHTR 即使看到 queue，也可能因為
`next_pid` 已固定，只能在較小的 admissible candidate set 中調整。這是 hierarchy
帶來的 approximation gap，不代表 Queue-aware 的機制有寫錯。

Queue input 目前是上一個 100 ms 視窗內每個 directional ISL 的最大 queue。
這不是整段歷史最大值，但會把短暫 queue spike 當成下一輪 routing 的狀態。
LHTR 同時使用 queue-weight penalty 與 traffic-light penalty，因此需要做
traffic-light on/off ablation，確認是否對同一個 spike 反應過強。

### 6.2 35.1 秒的路由轉折直接解釋主要差距

從 delta fstate 重建出的 forwarding path 顯示：

1. 在 `t = 35.1 s`，LHTR 將 flows 15、16、17 的 destination attachment
   從 satellite 278 切換到 satellite 277。
2. 這三條 flow 的 LHTR path 變成約 32-33 hops；Queue-aware 仍使用
   satellite 278，約 19-21 hops。
3. satellite 277 原本已承載 flows 1、21、23 的 destination-side traffic。
4. 切換後，LHTR 在 satellite 277 聚集 6 條 3 Mbps flows，估計 offered load
   為 **18 Mbps**，超過 10 Mbps GSL capacity。
5. GSL 277 queue 在 `t = 35.2 s` 開始達到 100 packets，時間上緊接在路由切換後。
6. Queue-aware 在 satellite 277 只有 3 條 flows，約 **9 Mbps**，低於 capacity。

| Algorithm at about 40 s | Flows using destination-side sat 277 | Estimated load | Path for flows 15-17 |
|---|---|---:|---:|
| Queue-aware | 1, 21, 23 | 9 Mbps | 19-21 hops, exit via sat 278 |
| LHTR | 1, 15, 16, 17, 21, 23 | 18 Mbps | 32-33 hops, exit via sat 277 |

其中 flow 1 就是 PDR 較差的 focus flow `793 -> 738`。它在 LHTR 下的 PDR
是 78.63%，Queue-aware 則是 92.92%。

這個時間順序和 capacity calculation 是目前最強的因果證據，但在 physical
drop trace 修好以前，仍應稱為「高度一致的 congestion explanation」，不稱為
已直接觀測到的 queue-drop proof。

### 6.3 最值得優先檢查的 LHTR 實作不一致

LHTR 目前用全圖 multi-source Dijkstra 估計每個 source satellite 應選哪個
destination attachment satellite；但選定 attachment 後，真正 forwarding path
仍由 hierarchical group path、border restriction 與 traffic-light decision 建構。

也就是：

> attachment selection 使用的 cost model，和實際能走出的 hierarchical path
> 並不完全相同。

這個 cost-model mismatch 是一個需要優先做 ablation 的風險；目前 trace 已證明
LHTR 的實際 hierarchical path 為 32-33 hops，而 Queue-aware 到 satellite 278
只需 19-21 hops，但尚未單獨證明 attachment-cache mismatch 就是這次 switch
的唯一原因。

目前較直接的問題是：attachment decision 完全沒有計入 GSL capacity 或已匯入
flow count。即使 satellite 277 的 ISL-side route cost略低，把第 4-6 條 flow
繼續送入同一個 10 Mbps GSL，仍會讓 end-to-end PDR 惡化。

另外還有三個待驗證問題：

- Inter-group graph 沒有把 queue/capacity 放進 `next_pid` cost。
- 無向 ISL 權重只取其中一個 directional queue；Queue-aware 則取雙向最大值。
- Routing 只看 ISL queue，沒有抑制多條 flow 匯入同一個 GSL/access satellite。

### 6.4 暫時不能用 control overhead 宣稱 LHTR 已較好

目前輸出反而顯示 LHTR 的實作成本較高：

| Current implementation metric | Queue-aware | LHTR |
|---|---:|---:|
| Mean changed fstate entries/update | 604 | 1,941 |
| Total delta fstate lines | 443,769 | 1,244,374 |
| Dynamic-iteration wall-clock proxy | 2.06 s | 4.50 s |

wall-clock proxy 包含 Python route calculation、該輪 simulation 與 queue log
輸出，不是純 routing microbenchmark；但至少目前沒有證據支持「LHTR 已經有較低
runtime/control overhead」。正式報告不應先使用這個優勢。

### 6.5 LHTR 並非所有案例都輸給 Queue-aware

- 10 秒 diagnostic：LHTR 97.53%，Queue-aware 96.66%。
- 舊 selector、32 background flows：LHTR 97.01%，Queue-aware 96.60%。
- 目前 60 秒 concentrated case：Queue-aware 98.93%，LHTR 95.24%。

因此比較合理的解讀是：

> LHTR 並非普遍失效；目前差距主要在長時間、高集中負載下出現，且可追到
> destination attachment 與 GSL concentration 的特定轉折。

## 7. Loss attribution 現況

目前 tracing 已有：

- Interface/queue drop trace file。
- PHY drop trace coverage。
- UDP send failure trace。
- Routing/no-route drop trace。
- ISL/GSL queue occupancy。
- Queue-saturation-associated loss analysis。

但目前 60 秒主案例中，四種演算法的以下 event 都是 0：

- Physical queue drop packets。
- Physical PHY drop packets。
- UDP send failures。
- Routing/no-route drops。

IPv4 L3 generic drop hook 尚未提供。

目前的 associated attribution：

| Algorithm | Synthetic loss | GSL-saturation-associated | Unclassified | Associated coverage |
|---|---:|---:|---:|---:|
| Static baseline | 162,252 | 0 | 162,252 | 0.00% |
| Queue-aware | 4,040 | 2,972 | 1,068 | 73.56% |
| LoHi | 65,680 | 30,320 | 35,360 | 46.16% |
| LHTR | 17,959 | 17,780 | 179 | 99.00% |

重要解讀：

1. Queue-aware、LoHi、LHTR 都觀察到 GSL queue 達到 100 packets。
2. Static baseline 的 GSL queue 最大值只有 2 packets，但多個 ISL queue
   occupancy 達到 100 packets。
3. 現有 association analysis 沒有把 static loss 對應成
   `isl_queue_saturation_associated_loss`，因此 static 的 162,252 losses
   仍全部是 unclassified。
4. 所有 physical drop trace 都是 0，所以 queue saturation 只能稱為
   correlation/association，不能稱為已證明的 physical queue drop。

另外確認到一個 instrumentation asymmetry：

- `ResetQueueTrackers()` 目前只 reset ISL trackers，沒有 reset GSL trackers。
- ISL CSV 每輪用 `w+` 重寫，因此模擬結束後只保留最後一個 100 ms 視窗。
- GSL tracker 未 reset，所以每輪雖然也重寫檔案，內容仍累積整段歷史。

這代表目前 loss attribution 擁有完整 GSL history，卻沒有完整 ISL history；
它很可能是 static saturated-ISL loss 全部無法關聯的重要原因。這個問題不會直接
改變 routing PDR，因為 routing queue input 只讀上一輪 ISL CSV，但會影響
loss-cause comparison，也會增加後期 GSL log 輸出時間。

目前較合理但仍需保守的系統性假說是：

> Static routing 將 traffic 留在高壓 ISL corridor；動態演算法把 traffic
> 分散後大幅改善 PDR，但部分壓力轉移到 GSL/access queues。Queue-aware
> 在這個 trade-off 中得到最佳 end-to-end delivery。

其中「壓力轉移」有 queue occupancy 與 associated-loss 證據；「實際 packet
在哪一層被 drop」仍未被 physical trace 完整證明。

## 8. 可以與不可以對老師說的話

### 可以直接說

- 目前已建出一個能明顯區分 routing algorithms 的 ISL-corridor stress case。
- 在這個 60 秒案例中，Queue-aware aggregate PDR 98.93%，static 只有 56.96%。
- Queue-aware 將 packet loss 相對 static 降低 97.51%。
- Queue-aware 的 focus-flow PDR 96.44%，LHTR 89.30%，LoHi 83.39%。
- Queue-aware 的 minimum per-flow PDR 仍有 92.92%，fairness 接近 1。
- LHTR aggregate PDR 95.24%，取得 Queue-aware 相對 static PDR 改善量的 91.2%。
- Queue-aware 是每 100 ms 使用全網 queue 狀態重算全域 SPF 的強 reference；
  LHTR 的 queue decision 受到 hierarchy 與固定 `next_pid` candidate set 限制。
- LHTR 的主要 60 秒退化可追到 35.1 秒的 attachment switch：satellite 277
  的估計 destination-side offered load 從 9 Mbps 等級升到 18 Mbps。
- 這個結果指出的是可修正的 attachment/GSL-load design gap，而不是已證明
  LHTR 架構沒有研究價值。
- Background-flow placement 比 background-flow count 本身更影響壅塞強度。
- Drain time 可以移除 simulation-tail 誤差，但不會消除真正的壅塞差異。

### 目前不宜直接說

- 不宜說已經證明所有 loss 都是 ISL queue overflow。
- 不宜說 physical queue drop trace 已完整解釋 `sent - received`。
- 不宜說 LHTR 在所有情況一定優於 LoHi，或 Queue-aware 在所有時間窗都第一。
- 不宜說目前數據已證明 LHTR 的 PDR 比 Queue-aware 好。
- 不宜宣稱目前 LHTR implementation 的 runtime 或 routing-update overhead 較低。
- 不宜把 Queue-aware 描述成「做錯」；它較好的主要原因是更強的全域資訊與
  unrestricted SPF。真正可疑的是 LHTR 自己的 attachment cost 與實際階層路徑
  不一致。
- 不宜把 10 秒、60 秒與 `dirty` 200 秒資料視為完全相同條件的 duration sweep。
- 不宜宣稱有統計顯著性；目前沒有多 seed/repetition 與 confidence interval。
- 不宜稱目前 scenario 為完全沒有 GSL bottleneck，因為動態演算法已有 GSL
  queue saturation evidence。

## 9. 建議下一步

優先順序建議如下：

1. 針對 `t = 35.1 s` 建立 deterministic regression case，確認 flows 15-17
   為何從 destination satellite 278 切到 277。
2. 將 destination attachment cost 改成與實際 hierarchical path 一致，或先做
   `closest-GSL-only` 與 `hierarchical-realized-cost` 兩個 ablation。
3. 在 attachment selection 加入 GSL capacity/estimated flow count，避免 6 條
   3 Mbps flows 匯入單一 10 Mbps GSL。
4. 將 LHTR 無向 ISL queue aggregation 改成和 Queue-aware 一致的雙向最大值，
   再做公平比較。
5. 做 traffic-light off、queue-penalty only、traffic-light only 三組 ablation，
   判斷是否有 double reaction 與 route churn。
6. 修正後用相同 24-flow schedule 重跑 10 秒與 60 秒；再跑乾淨 200 秒案例。
7. 完成真正能記到 queue overflow 的 per-interface drop hook，並補 IPv4
   L3/forwarding drop coverage。
8. 增加多個 start time / orbital window，確認 Queue-aware 與 LHTR 的排序是否穩定。
9. 增加至少 3 次 repetition 或 seed/config variation，再報 mean、range 或
   confidence interval。
10. 再做 20/24/28 background-flow sweep，但固定使用新版 concentrated selector，
   取得新版 scenario 的 transition curve。

## 10. 建議報告主線

建議對老師用以下順序報告：

1. 先說明早期 load sweep 已看到 dynamic routing 的優勢。
2. 說明 drain-time correction 與 traffic selector 改進。
3. 展示新版 scenario 的 2.7x target-corridor pressure。
4. 展示目前 60 秒 aggregate PDR，誠實承認 Queue-aware 98.93% 高於 LHTR 95.24%。
5. 立刻補充 Queue-aware 是 global-information reference，而 LHTR 取得其
   relative PDR gain 的 91.2%。
6. 展示 35.1 秒 attachment switch 與 18 Mbps / 10 Mbps GSL concentration，
   說明差距已有具體、可修正的來源。
7. 說明目前不能用 runtime/control overhead 當優勢，下一步會先完成 ablation
   與 objective alignment。
8. 最後補充 loss attribution instrumentation gap、多時間窗與 repetition。

建議口頭收尾：

> 我目前不會宣稱 LHTR 的 PDR 已經勝過全域 Queue-aware SPF。現有結果顯示，
> LHTR 在保留階層限制下取得了 global reference 相對 static 改善的 91.2%；
> 剩餘差距集中在 35.1 秒後的 destination attachment 決策，它把六條流量匯入
> 單一 10 Mbps GSL。這已經把問題從「LHTR 為什麼全面較差」縮小成一個可重現、
> 可做 ablation、也可修正的 attachment 與 GSL-load design gap。

## 11. 主要資料來源

- Current summary:
  `runs/run_core_isl_hotspot_specific_load_1p8x_bg_flow_count_24_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/summary_by_algorithm.csv`
- Focus flows:
  `runs/run_core_isl_hotspot_specific_load_1p8x_bg_flow_count_24_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/focus_flow_delivery.csv`
- Flow-selection concentration:
  `runs/run_core_isl_hotspot_specific_load_1p8x_bg_flow_count_24_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/corridor_concentration_summary.csv`
- Detailed loss attribution:
  `runs/run_core_isl_hotspot_specific_load_1p8x_bg_flow_count_24_oneweb_isls_moving_udp_pdr/comparison_packet_delivery/loss_attribution_breakdown_v2.csv`
- Background-flow sweep:
  `runs_backup_bg_1p4_1p8_20260602_003003/`
- Transition sweep:
  `runs_backup_transition_1p8_bg20_24_28_20260602_173557/`
- Drain-time validation:
  `runs_backup_drain_time_20260528_222541/`
- 10-second diagnostic smoke run:
  `runs_backup_loss_attribution_diagnostics_10s_20260605_024940/`
