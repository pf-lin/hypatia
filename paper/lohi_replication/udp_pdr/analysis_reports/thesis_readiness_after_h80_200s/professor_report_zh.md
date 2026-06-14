# 教授報告：UDP/PDR 論文主實驗就緒度（H80 200s 後）

## 執行摘要

本次只讀取既有結果，沒有重跑 simulation 或修改演算法。結論是：**目前 5-level 60s formal experiment 加上 H80 200s targeted validation，已足以支撐論文主實驗敘事。**

H80 200s 仍維持 `Baseline < LoHi < LHTR < Queue-aware`。LHTR 對 LoHi 的 aggregate-PDR gain 為 **28.85 pp**，與 60s 的 **28.93 pp** 幾乎相同；LHTR 的 mean/p95 estimated RTT 也分別比 LoHi 低 **36.1/64.5 ms**。因此 H80 的核心結論不是 60 秒觀察窗造成的偶然排序。

建議現在進入論文圖表與實驗章節整理，不把 H100+ 200s 視為 blocking experiment。

# Part 1. 實驗設計

## 1.1 實驗目標

本實驗在 OneWeb-like LEO satellite constellation 的 ISL hotspot congestion 下，比較四種 routing approaches 的 PDR、estimated RTT、flow-tail delivery、loss association 與 route behavior：

- Baseline：shortest-path/free-one-only reference。
- Queue-aware：具較完整 queue/congestion information 的 ideal upper-bound reference。
- LoHi：hierarchical/group-based routing，使用 manager-assisted control plane。
- LHTR：在 hierarchical context 中加入 traffic-light 與 BR/SBR decision，希望以有限資訊更接近 Queue-aware。

Queue-aware 不是實際可部署成本相同的對手，也不是 LHTR 必須超越的目標。它回答的是：在相同 traffic demand 下，若可取得更完整資訊與調度能力，網路尚有多少 routing headroom。

## 1.2 Congestion level 定義

`load_level` 是 traffic-rate scaling parameter，不是 hotspot utilization percentage；PDR 是 routing outcome，也不能拿來反向定義 congestion。由於流量刻意集中在少量 ISLs，若用全星座 2,880 條 directed ISLs 的容量作分母，hotspot 壓力會被大量未參與 links 稀釋。

主 x-axis 使用：

```text
hotspot_reference_load_percent =
  100 * reference hop demand
  / (per-setting touched reference directed ISLs * ISL capacity)

reference hop demand =
  sum(flow_rate * baseline reference ISL hop count)
```

同時保留 global offered ISL load 作 constellation-wide context，並以 target-corridor offered load 與 peak reference-link load 作 diagnostics。PDR 不參與 level labeling。

| Scenario | load level | BG flows | Hotspot-reference | Global offered ISL | Label | Observed condition |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| H40 | 1.0 | 24 | 47.359% | 1.842% | Hotspot-Light | Localized congestion |
| H60 | 1.2 | 32 | 59.154% | 2.793% | Hotspot-Moderate | Localized congestion |
| H80 | 1.6 | 32 | 78.873% | 3.725% | Hotspot-High | Sustained congestion |
| H90 | 2.2 | 48 | 91.171% | 7.028% | Hotspot-Severe | Sustained congestion |
| H100+ | 2.8 | 48 | 116.036% | 8.944% | Hotspot-Overload | Overloaded |

H40/H60 代表 localized/moderate pressure，H80 是 sustained high congestion，H90 是 severe，H100+ 的 hotspot-reference load 超過 100%，作 overload stress point。

## 1.3 Flow traffic 大小

程式中的 per-flow rate 為：

```text
aggregate reference rate = load_level * ISL capacity
reference pair count = 2 focus directions + 4 reference background flows = 6
per_flow_rate_mbps = load_level * 10 Mbps / 6
```

`per-flow-rate-reference-background-flow-count=4` 使 per-flow rate 不會因實際 BG flow count 增加而自動下降。因此增加 BG flows 會提高 total offered traffic 與 hotspot pressure。兩條 focus flows 是 Johannesburg 與 Fukuoka 的雙向 traffic；其餘為依 baseline middle-ISL overlap 選出的 background flows。

| Scenario | Per-flow Mbps | Total offered Mbps | Focus total Mbps | Background total Mbps |
| --- | ---: | ---: | ---: | ---: |
| H40 | 1.6667 | 43.3333 | 3.3333 | 40.0000 |
| H60 | 2.0000 | 68.0000 | 4.0000 | 64.0000 |
| H80 | 2.6667 | 90.6667 | 5.3333 | 85.3333 |
| H90 | 3.6667 | 183.3333 | 7.3333 | 176.0000 |
| H100+ | 4.6667 | 233.3333 | 9.3333 | 224.0000 |

60s run 在 58s 停止送流量，200s run 在 198s 停止；最後 2s 都保留給 in-flight packet drain。

## 1.4 為什麼提高 GSL capacity

ISL capacity 固定為 10 Mbps，GSL capacity 提高至 100 Mbps。研究問題是 ISL routing decision，因此需避免 access/GSL 先成為主要瓶頸。H80 200s 中，ISL queue 可達 100 packets，GSL 最大 queue 僅 1-3 packets；所有 synthetic loss 都被歸為 ISL-saturation-associated。這支持結果主要反映 ISL routing behavior，但 associated attribution 仍不可稱為 exact physical drop proof。

# Part 2. 演算法比較

## 2.1 Baseline

Baseline 使用 shortest-path/free-one-only routing。優點是簡單、path propagation 較短；缺點是沒有足夠 congestion adaptation，hotspot traffic 容易集中到少數 ISLs。60s 五個 levels 中 aggregate PDR 從 H40 的 0.8400 降至 H100+ 的 0.2842。H80 200s 為 0.4696，mean estimated RTT 達 982.1 ms，是四者最差，適合作為 naive/lower-bound reference。

## 2.2 Queue-aware

Queue-aware 使用較完整的 queue/congestion information，在 H80 200s 達 0.9631 aggregate PDR、226.1 ms mean estimated RTT，兩項均最佳。它證明相同 offered demand 下仍存在更好的 routing 空間。其角色是 ideal upper bound；LHTR 的價值在於有限、局部、hierarchical information 下縮小與此上限的差距。

## 2.3 LoHi

LoHi 使用 hierarchical/group-based routing；formal run 的 8,000 筆 diagnostics 全為 `control_plane_only`。實體路徑只有 8.96% 包含 manager，因此 LoHi 不是 strict physical manager waypoint。manager-assisted control plane 提供 border selection，但不等於 global queue-aware optimization。

H80 200s LoHi aggregate PDR 為 0.6114、mean RTT 286.7 ms。其限制可由結果合理解讀為 group abstraction 較粗、border selection 對瞬時 congestion 反應有限，以及 path 較長：平均 focus round-trip path 的單向 hop count 指標為 24.30，較 LHTR 的 21.45 高。這是 diagnostics-supported interpretation，不宣稱單一欄位已證明完整因果鏈。

## 2.4 LHTR

LHTR 加入 traffic-light 與 BR/SBR decision。在 60s curve 中，H60-H100+ 都優於 LoHi；H80 gain 最大。H80 200s 仍有 0.9000 aggregate PDR，較 LoHi 高 28.85 pp，且 mean/p95 RTT 低 36.1/64.5 ms。

LHTR 未達 Queue-aware 是合理且可解釋的：200s 只有 0.1048% decisions 選 SBR；`no_alternative_candidate` 占 24.51%，`sbr_stretch_too_high` 占 2.24%。有限 candidate coverage、stretch constraint 與 local/hierarchical knowledge 限制了可用替代路徑。

# Part 3. 原因分析

## 3.1 核心量化結果

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

- LHTR-LoHi gain：60s=28.93 pp；200s=28.85 pp。
- Queue-aware-LHTR remaining gap：60s=7.32 pp；200s=6.32 pp。
- 200s LHTR 比 LoHi mean/p95 RTT 低 36.1/64.5 ms。
- 200s Queue-aware 仍為 upper bound；Baseline 仍為 aggregate PDR 與 RTT 最差者。

## 3.2 LHTR 為什麼比 LoHi 好

1. LHTR 的 path 平均 hop count 比 LoHi 短，且 estimated queue delay 較低（LHTR 22.6 ms；LoHi 37.8 ms）。
2. SBR usage 雖低，但與 traffic-light congestion signal 高度同步：SBR 與 yellow+red correlation=0.896；最壅塞的 25% 時窗承載 50.9% SBR decisions。
3. 這代表 LHTR 的優勢不需要大量改路，而可能來自少量但有時機性的 alternate selection，以及較直接的 local congestion reaction。
4. fstate eligible match rate=99.883% 且 fallback=0，降低「結果來自 implementation inconsistency」的疑慮。

## 3.3 為什麼 LHTR 仍輸 Queue-aware

Queue-aware 可在更廣泛的 candidate space 上使用較完整 congestion information；LHTR 則受 BR/SBR candidate availability、stretch rejection 與 hierarchical knowledge 邊界限制。200s 中 `br_green` 占 73.14%，`no_alternative_candidate` 占 24.51%，SBR ratio 僅 0.1048%。因此 remaining gap 應寫成有限資訊部署成本的代價與未來 headroom，而不是實驗失敗。

建議論文用語：

> Queue-aware 代表理想化 upper bound；LHTR 的貢獻是，在不具備全域理想資訊的 hierarchical routing context 下，顯著縮小 LoHi 與 Queue-aware 之間的距離。

## 3.4 200s 是否支持 60s

支持。PDR 與 RTT 排序完全相同；LHTR-LoHi gain 幾乎不變；Queue-aware-LHTR gap 反而縮小。SBR ratio 未隨 duration 增加，yellow/red 也不是單調累積，表示系統呈現的是持續負載下的 recurring congestion bursts，而非 diagnostics count 隨時間機械式上升。這個結果比「200s 只是累積更多 SBR」更有說服力。

## 3.5 論文圖表配置

Main figures：

1. Aggregate PDR across H40-H100+。
2. Mean estimated RTT across H40-H100+。
3. LHTR vs LoHi PDR gain。
4. Queue-aware upper-bound gap。
5. H80 60s vs 200s PDR stability。

Supporting：focus/background PDR、H80 duration RTT、SBR ratio、yellow/red、loss attribution、H80 routes。

Diagnostics only：raw decision reasons、fstate consistency、queue-at-capacity samples。

## 結論與建議

目前證據足以支撐固定 formal scenario 下的論文主結果；尚不足以宣稱跨 seed、跨 topology 的統計普遍性。基於畢業時程，最合理的決策不是擴張成完整 200s sweep，而是**立即開始整理論文實驗章節與圖表**。H100+ 200s 僅在主文完成且資源有餘時作 optional stress-test backup。
