# LHTR BR/SBR Diagnostics 60s 分析報告

分析對象：

```text
run_core_isl_hotspot_specific_src754_dst785_load_1p4x_bg_flow_count_16_oneweb_isls_moving_udp_pdr
```

條件：`src=754`、`dst=785`、`load=1.4`、`background_flow_count=16`、`duration=60s`、`traffic_stop=58s`。

本報告只讀取既有輸出；沒有修改程式、重跑 simulation、重建 run、覆蓋 comparison output 或調整 LHTR policy/threshold。

# 1. 總結結論

- **60s diagnostics 完整。** LHTR simulation 正常結束，600 個 dynamic-state snapshots、六個預期 diagnostics CSV 均存在。Step 3 也成功將新 LHTR 結果與先前的 Baseline、Queue-aware、LoHi 結果整合。
- **LHTR 有選過 SBR。** 全量 summary 中共有 `128` 次 SBR selection，分布於 `12` 個 snapshots；其中 `119` 次因 BR 為 YELLOW，`9` 次因 BR 為 RED。
- **Traffic Light 有實際觸發。** 60 秒內有 `703` 個 YELLOW 與 `242` 個 RED directional link-samples；`367` 個 snapshots 出現 YELLOW，`193` 個 snapshots 出現 RED。
- **BR/SBR 確實不同。** 在 300 萬筆 sampled decision log 中，`2,204,985` 筆有 SBR，這些 SBR 的 next hop 與 path 全部不同於 BR。其 median stretch 為 `1.0200`，p95 為 `1.1406`。
- **不能說「SBR 沒有被選」。** 當 sampled full BR path 比 SBR 更壅塞時，共有 `128` 筆，這 `128` 筆全部選擇 SBR；沒有發現「SBR 明顯更乾淨但仍選 BR」。
- **大多數決策仍看見 GREEN。** 全量 BR candidate color 中 GREEN 佔 `79,088,123 / 79,088,307`；sampled full-path 重建也有 `2,999,776 / 3,000,000` 為全綠。
- **真正的限制是 active-flow relevance。** 128 次 SBR selection 中，只有 `1` 次位於同一時間、同一 destination 的實際 active-flow replay path 上。其餘選擇多屬未承載當下實驗流量的 route-table entry，因此幾乎不會改善 PDR。
- **fstate consistency 整體良好但非完美。** 可直接比較的 `1,773,207` 筆中，`1,772,373` 筆 match、`834` 筆 mismatch，mismatch rate 為 `0.0470%`。另有 `1,226,793` 筆是 conceptual border target，不能用 immediate next hop 直接比較。
- **沒有證據顯示 fstate mismatch 是本次 PDR 主因。** mismatch 全部屬 `cross_pid_next_hop`；雖有 11 筆 destination 742 的 mismatch，但對應 current node 不在該 active flow 的 replay path 上。
- **LHTR 仍低於 LoHi。** LHTR PDR 為 `0.997960631`、loss `414`；LoHi PDR 為 `0.998556679`、loss `293`。LHTR 的 ISL at-capacity rows 為 `384`，高於 LoHi 的 `334`，且 `90.10%` 集中於 target corridor。
- **最可能根因屬 B 類。** Traffic Light 與 SBR selector 都有運作，但真正承載流量的 BR path 很少在 decision context 中看到較差顏色，SBR offload 幾乎沒有落到 active flow。
- **下一步建議：** `lhtr_analyze_br_path_color_vs_network_color.md`。先把 local link color、full path max color、active-flow relevance 與 target-corridor relation 明確分開，再決定是否需要改 policy。

# 2. Diagnostics 檔案檢查

## LHTR diagnostics layout

目錄存在：

```text
algorithm_lhtr/lhtr_diagnostics/
```

| file | exists | data rows | size | interpretation |
|---|---:|---:|---:|---|
| `lhtr_qor_tqor_samples.csv` | yes | 1,728,000 | 166,968,993 B (159.23 MiB) | 600 snapshots × 2,880 directional ISLs，保存 QOR/TQOR 與 final color |
| `lhtr_traffic_light_color_summary.csv` | yes | 600 | 29,458 B (28.77 KiB) | 每 100 ms snapshot 的 GREEN/YELLOW/RED 聚合 |
| `lhtr_br_sbr_decision_log.csv` | yes | 3,000,000 | 1,296,083,436 B (1.21 GiB) | 每 snapshot 最多 5,000 筆的 sampled/priority decision log；不是 79M 全量決策 |
| `lhtr_br_sbr_summary.csv` | yes | 600 | 50,553 B (49.37 KiB) | 每 snapshot 的全量 BR/SBR/reason 計數 |
| `lhtr_decision_reason_summary.csv` | yes | 5 | 259 B | 全 run 的五種 decision reason 聚合 |
| `lhtr_fstate_decision_consistency.csv` | yes | 3,000,000 | 278,818,705 B (265.90 MiB) | 與 sampled decision log 對應的 fstate consistency |

檢查結果：

- `dynamic_state/` 沒有 `lhtr_*.csv`。
- `logs_ns3/` 沒有 `lhtr_*.csv`。
- `comparison_packet_delivery/diagnostics/` 有 Traffic-Light summary、BR/SBR summary、reason summary 與 fstate consistency。
- source 與 comparison summary 的 counts 相符；reason percentage 只有浮點序列化末位差異，沒有計數差異。
- comparison 端沒有複製 1.21 GiB decision log 與 159 MiB QOR/TQOR samples；這符合避免重複大型 raw diagnostics 的目的。
- 其他三個 algorithms 沒有 LHTR diagnostics，Step 3 仍正常完成，沒有看到 diagnostics 對其他 algorithms 造成影響的證據。

## Run 完整性與 overwrite 風險

四個 algorithms 都有 `60.0s` simulation end、`58.0s` traffic stop、18 flows，flow hash 均為 `9fb032ccffa6eb89`。每個 algorithm 都有 600 個 fstate snapshots，console tail 均有 `BASIC SIMULATION END`。

| algorithm | folder exists | finished | console ok | modified time | likely from current run? | notes |
|---|---:|---:|---:|---|---:|---|
| Baseline | yes | yes | yes | metadata 2026-06-10 02:17；console 02:36 | no | 保留自先前四演算法 sweep |
| Queue-aware | yes | yes | yes | metadata 2026-06-10 02:17；console 02:56 | no | 保留自先前四演算法 sweep |
| LoHi | yes | yes | yes | metadata 2026-06-10 02:17；console 03:26 | no | 保留自先前四演算法 sweep |
| LHTR | yes | yes | yes | metadata 2026-06-10 21:52；console 22:52 | yes | 本次 diagnostics rerun |

Step 3 的 comparison output 於約 23:08 更新，成功整合舊三組結果與新 LHTR。需注意：

- `--force --algorithms algorithm_lhtr` 看起來只重建 LHTR algorithm folder。
- Step 3 仍會更新 analysis-derived files，例如各 algorithm 的 `udp_flows.csv`、`link_drops.csv` 與 comparison outputs。
- run name 不含 duration；若未來用相同 traffic/load/bg 但不同 duration，仍有覆蓋同一 run folder 的風險。

# 3. Traffic-Light color 分析

## 全 run 統計

| metric | value | interpretation |
|---|---:|---|
| snapshots | 600 | 0.1 秒間隔的 60 秒 run |
| directional links per snapshot | 2,880 | 每個 snapshot 的 directional ISL 數 |
| total link-samples | 1,728,000 | 600 × 2,880 |
| green_link_samples | 1,727,055 | final color GREEN |
| yellow_link_samples | 703 | final color YELLOW |
| red_link_samples | 242 | final color RED |
| yellow_snapshots | 367 | 61.17% snapshots 至少有一個 YELLOW |
| red_snapshots | 193 | 32.17% snapshots 至少有一個 RED |
| snapshots with both YELLOW and RED | 135 | 同一 snapshot 同時存在兩種壅塞色 |
| QOR yellow count | 701 | 幾乎所有 final YELLOW 都由 directional queue 觸發 |
| QOR red count | 242 | 所有 RED 都可由 QOR 解釋 |
| TQOR yellow count | 4 | 僅 1.6 秒 snapshot 的四個 incoming links |
| TQOR red count | 0 | TQOR 從未達 RED |
| TQOR escalated count | 2 | 只有兩筆 final color 被 TQOR 提升 |

每個 snapshot 的分布範圍：

| color | min | max | mean per snapshot |
|---|---:|---:|---:|
| GREEN | 2,874 | 2,880 | 2,878.425 |
| YELLOW | 0 | 5 | 1.1717 |
| RED | 0 | 3 | 0.4033 |
| YELLOW + RED | 0 | 6 | 1.5750 |

## 常見 YELLOW/RED links

| directional link | color | samples | target corridor? |
|---|---|---:|---:|
| 17→57 | YELLOW | 49 | no |
| 176→136 | YELLOW | 48 | yes |
| 644→684 | YELLOW | 48 | yes |
| 683→16 | YELLOW | 46 | yes |
| 563→603 | RED | 44 | yes |
| 684→15 | YELLOW | 37 | yes |
| 564→604 | YELLOW | 34 | yes |
| 603→643 | YELLOW | 31 | yes |
| 16→56 | YELLOW | 30 | yes |
| 524→564 | YELLOW | 28 | yes |
| 176→136 | RED | 22 | yes |
| 603→643 | RED | 21 | yes |
| 644→684 | RED | 21 | yes |
| 564→604 | RED | 20 | yes |

flow selection 定義了 25 個 undirected target edges；轉成方向後是 50 個 directional links。這些 links 在 600 snapshots 中共有 30,000 個 samples：

- Target YELLOW：`500 / 703 = 71.12%`
- Target RED：`198 / 242 = 81.82%`
- Target colored samples：`698 / 945 = 73.86%`

因此 YELLOW/RED 高度集中於 target corridor，而不是均勻散布全網。

## QOR / TQOR 定義驗證

| metric | intended definition | observed evidence | matches? | notes |
|---|---|---|---:|---|
| QOR | current directional ISL queue / interface buffer capacity | 1,728,000 筆均與 `queue_packets / queue_capacity` 相符 | yes | observed GREEN 0–0.59、YELLOW 0.60–0.79、RED 0.80–1.00 |
| TQOR | next-hop satellite total outgoing queue / total outgoing capacity | 均與 `next_hop_total_queue_packets / next_hop_total_queue_capacity` 相符 | yes | denominator 即 degree × per-interface buffer |
| TQOR semantics | spatial next-hop aggregate，不是 temporal quantity | 同一 snapshot 聚合 next-hop 的 outgoing queues | yes | 名稱中的 T 不是時間平均 |
| final color | `max_severity(QOR_color, TQOR_color)` | 所有 samples 均一致 | yes | 沒有 color mismatch |
| thresholds | QOR 0.6/0.8；TQOR 1/3、2/3 | observed color ranges 與邊界一致 | yes | 沒有 threshold anomaly |

TQOR escalation 確實發生，但極少：

- `t=1.6s`，`135→136`：QOR `0.31` GREEN、TQOR `0.39` YELLOW，final YELLOW。
- `t=1.6s`，`137→136`：QOR `0.00` GREEN、TQOR `0.39` YELLOW，final YELLOW。
- 同一時間 `96→136`、`176→136` 的 TQOR 也為 YELLOW，但 QOR 已達同等或更高嚴重度，因此不計為 escalation。

結論是本 run 幾乎完全由 QOR 驅動；TQOR 定義正確，但對選色的實際貢獻只有兩筆。

# 4. BR/SBR decision 分析

## 全量 summary

總 decision count 為 `79,088,307`。

| metric | value | percentage | interpretation |
|---|---:|---:|---|
| BR selected | 79,088,179 | 99.999838% | 幾乎所有 route-table decisions 選 BR |
| SBR selected | 128 | 0.000162% | 不是零，但非常罕見 |
| fallback | 0 | 0% | 沒有 fallback route selection |
| no route | 0 | 0% | 沒有 route construction failure |
| SBR due to YELLOW | 119 | 0.000150% | BR YELLOW 且 SBR 較乾淨 |
| SBR due to RED | 9 | 0.000011% | BR RED 且 SBR 較乾淨 |
| no alternative candidate | 20,653,205 | 26.114107% | BR 被保留，因沒有可用替代候選 |
| SBR red fallback | 0 | 0% | 沒有因 SBR RED 進入 fallback |
| SBR stretch too high | 770,566 | 0.974311% | 有替代路徑概念，但超過 stretch filter |

`fallback_due_to_no_sbr` 在此 diagnostics 中對應的是 `no_alternative_candidate` reason，不代表 selected route type 是 fallback；實際 selected route 仍是 BR。

Decision reasons：

| reason | count | percentage |
|---|---:|---:|
| `br_green` | 57,664,408 | 72.911420% |
| `no_alternative_candidate` | 20,653,205 | 26.114107% |
| `sbr_stretch_too_high` | 770,566 | 0.974311% |
| `sbr_due_to_yellow` | 119 | 0.000150% |
| `sbr_due_to_red` | 9 | 0.000011% |

BR candidate 的 recorded local color：

| BR color | total | selected BR | selected SBR | interpretation |
|---|---:|---:|---:|---|
| GREEN | 79,088,123 | 79,088,123 | 0 | policy 合理保留 BR |
| YELLOW | 173 | 54 | 119 | 51 筆沒有 alternative；3 筆 stretch too high |
| RED | 11 | 2 | 9 | 2 筆 stretch too high |

因此：

- policy 並非在 YELLOW/RED 時拒絕乾淨且 admissible 的 SBR。
- recorded non-green BR 且存在 admissible cleaner SBR 時，`119 + 9 = 128` 筆全部切到 SBR。
- 未切換的 56 筆 non-green BR 都有具體原因：沒有 alternative 或 stretch 過高。

# 5. BR vs SBR 差異分析

`lhtr_br_sbr_decision_log.csv` 是每 snapshot 最多 5,000 筆的 diagnostics sample，總計 300 萬筆。以下 path-level 統計代表 sampled decisions，不能直接當作 79M 全量分布。

| metric | value | interpretation |
|---|---:|---|
| sampled decisions | 3,000,000 | 600 × 5,000 |
| SBR available count | 2,204,985 | sampled log 的 73.4995% |
| different next-hop count | 2,204,985 | 所有 available SBR 都與 BR next hop 不同 |
| different path count | 2,204,985 | 所有 available SBR path 都與 BR path 不同 |
| SBR available but BR selected | 2,204,857 | 多數 BR/SBR 同為 GREEN，保留較短 BR |
| SBR selected | 128 | 都是 SBR 比 BR 更乾淨 |
| SBR cost > BR cost | 2,204,985 | 所有 available SBR 成本都較高 |
| min path stretch | 1.000000 | 幾乎等成本的替代路徑存在 |
| median path stretch | 1.020005 | 典型額外成本約 2% |
| p95 path stretch | 1.140642 | 95% admitted SBR 在約 14.1% 內 |
| p99 path stretch | 1.346583 | tail 較長，但仍在 threshold 內 |
| max path stretch | 1.499957 | 接近既有 1.5 threshold |
| full-summary stretch-too-high | 770,566 | 僅佔全部 decisions 0.9743%，不是主導原因 |
| full-summary no alternative | 20,653,205 | 26.1141%，比 stretch filter 更重要 |

常見 available-SBR current nodes 為 28（102,406）、27（100,725）、26（97,217）、25（91,253）、24（89,599）。常見 destination 包含 749（29,498）、810（28,561）、732（27,945）、770（27,890）、746（27,318）。

最高頻的 `(src,dst,current_node)` 組合有多組並列 1,200 次，例如：

```text
(0,724,0), (0,728,0), (0,731,0), (0,734,0), (0,741,0)
```

這些排行是全 route-table construction 的結果，不代表實際實驗流量最常經過這些節點。

`no_alternative_candidate` 表示 candidate generation/filtering 後沒有可用 SBR，但現有欄位無法再細分成：

- topology 上真的沒有不同路徑；
- hierarchy/case generation 沒產生候選；
- 候選在其他 admissibility rule 被排除。

因此可以說 candidate availability 是次要限制，但不能只憑此檔判定「SBR generation condition 一定太嚴格」。Stretch filter 只佔 0.9743%，不支持把 threshold 當成首要問題。

# 6. BR/SBR 與 Traffic Light 關係

## Recorded color 與 full-path color 的差異

diagnostics 欄位 `br_max_color` / `sbr_max_color` 實際對應 candidate decision context 的 local next-hop link 或 border ISL color，不是任意長度 path 的完整 maximum。以 `br_path` / `sbr_path` 逐 hop 對照同時間 QOR/TQOR samples 後：

| path color source | GREEN | YELLOW | RED |
|---|---:|---:|---:|
| recorded BR candidate color（全量） | 79,088,123 | 173 | 11 |
| reconstructed full BR path（300 萬 sample） | 2,999,776 | 213 | 11 |
| reconstructed full SBR path（2,204,985 available） | 2,204,957 | 28 | 0 |

Sampled BR 有 40 筆 recorded color 與 reconstructed full-path max 不同；其中 28 筆 decision reason 是 `br_green`，但 full BR path 為 YELLOW。沒有發現 full BR path RED 而 reason 仍是 `br_green`。

這 28 筆的 SBR full path 也為 YELLOW，因此沒有漏掉 cleaner SBR；它們暴露的是 diagnostics 命名/可觀測範圍問題，而不是本 run 中明確的錯誤 route choice。

## Full-path relation 與 selection

| case | count | selected BR | selected SBR | interpretation |
|---|---:|---:|---:|---|
| full BR GREEN | 2,999,776 | 2,999,776 | 0 | BR path 本身無較差顏色 |
| full BR YELLOW | 213 | 94 | 119 | 119 筆有 cleaner SBR；其餘沒有 cleaner admissible SBR |
| full BR RED | 11 | 2 | 9 | 9 筆有 cleaner SBR；2 筆 stretch too high |
| SBR cleaner than BR | 128 | 0 | 128 | cleaner SBR 全部被選 |
| SBR same color as BR | 2,204,857 | 2,204,857 | 0 | 保留較低成本 BR |
| SBR worse than BR | 0 | 0 | 0 | sampled admitted SBR 中未見 |

所以：

- 全網存在 YELLOW/RED，但大多數 BR decision path 仍是 GREEN，兩者並不矛盾。
- sampled full BR path 非 GREEN 僅 `224 / 3,000,000 = 0.00747%`。
- policy 對真正 cleaner 的 SBR 並不保守：128/128 都切換。
- 必須在 diagnostics 中明確區分 local candidate color 與 full-path max color，否則 `br_max_color` 容易被誤讀。

## Target corridor 與 active-flow relevance

128 次 SBR selection 的 BR path 全部與 target corridor 相交：

- BR intersects target corridor：128/128
- SBR intersects target corridor：60/128
- SBR 避開 target corridor：68/128
- BR full color：119 YELLOW、9 RED
- SBR full color：128 GREEN

這證明 SBR 機制確實能在某些 route-table entries 上避開 hotspot。

但把 decision 與 `flow_path_timeline.csv` 以 `time_ns + dst + current_node` 對齊後：

- 128 次 SBR selection 只有 **1 次**位於當下 active-flow replay path。
- 唯一事件為 `t=38.9s`、flow 6、`176→736`。
- current node 176 的 BR 為 `176→136→135→95→55→15`，local color YELLOW。
- SBR 為 `176→175→135→95→55→15`，color GREEN。
- stretch 為 `1.030677`，selected next hop 175，且 `selected_applied=True`。

這是 LHTR 正確工作的直接證據，也同時指出效益不足的原因：127/128 次 switch 沒有位於實際 active-flow path。

# 7. fstate consistency

| metric | value | interpretation |
|---|---:|---|
| total sampled consistency rows | 3,000,000 | 對應 sampled decision log |
| match | 1,772,373 | selected next hop 與 final fstate 一致 |
| mismatch | 834 | 可直接比較資料的 0.0470% |
| conceptual border target | 1,226,793 | hierarchical border target，不是 immediate next hop，不能直接比較 |
| unknown beyond conceptual target | 0 | 沒有額外未知類型 |
| exact next-hop checks | 1,568,725 | immediate next-hop comparison |
| exact border-ISL checks | 204,482 | border edge comparison |

所有 834 筆 mismatch 都是 `cross_pid_next_hop`，分布於 276 snapshots，時間從 0.6 秒到 58.1 秒。destination 分布：

| dst | mismatch count | active experiment destination? |
|---|---:|---:|
| 723 | 424 | no |
| 783 | 398 | no |
| 742 | 11 | yes |
| 721 | 1 | no |

範例由 consistency row 與 decision log join 取得：

| time_ns | current_node | dst | selected_next_hop | fstate_next_hop | decision_reason | notes |
|---:|---:|---:|---:|---:|---|---|
| 600000000 | 404 | 721 | 403 | 405 | `br_green` | `exact_next_hop_check` |
| 9000000000 | 138 | 723 | 137 | 139 | `no_alternative_candidate` | `exact_next_hop_check` |
| 9000000000 | 139 | 723 | 138 | 140 | `no_alternative_candidate` | `exact_next_hop_check` |
| 9000000000 | 217 | 723 | 216 | 218 | `br_green` | `exact_next_hop_check` |
| 9000000000 | 218 | 723 | 217 | 219 | `br_green` | `exact_next_hop_check` |

11 筆 destination 742 mismatch 均發生在 current node 459，selected next hop 458、final fstate next hop 460；但 flow 11（807→742）的 replay path 在這些時間都沒有經過 node 459。因此沒有證據顯示這些 mismatch 影響本次封包。

從模式看，mismatch 很可能發生在 decision 後的全域 fstate cleanup，例如 2-cycle breaking 改寫 final next hop；這是根據輸出模式的推論，不是 diagnostics 直接記錄的原因。

selected next hop 寫入 fstate 的證據充分：

- 1,772,373 筆直接 match。
- 唯一 active-path SBR event 在 node 176 選 175，final fstate 也為 175。

仍建議後續 diagnostics 記錄 post-processing rewrite reason，讓 834 筆差異可被確定分類；但它不是目前 LHTR 低於 LoHi 的主要證據。

# 8. PDR / queue / loss attribution 關聯

## Aggregate delivery

| algorithm | aggregate PDR | lost packets | ISL at-capacity rows |
|---|---:|---:|---:|
| Baseline | 0.682971764 | 64,358 | 181,190 |
| Queue-aware | 0.999640401 | 73 | 74 |
| LoHi | 0.998556679 | 293 | 334 |
| LHTR | 0.997960631 | 414 | 384 |

LHTR focus flow（754→785）PDR 為 `0.998093634`。本次 diagnostics rerun 的 aggregate PDR 與先前報告的 `0.997961` 相符，沒有觀察到 diagnostics enabled 改變 forwarding behavior。

相較 LoHi：

- LHTR 多 loss `121` packets。
- LHTR loss count 相對高約 `41.3%`。
- LHTR aggregate PDR 低 `0.000596048`。
- LHTR ISL at-capacity rows 多 `50`，高約 `14.97%`。

## Queue hotspot

LHTR 有 15 個 congested interfaces、384 個 at-capacity rows；其中 12 個 target-corridor interfaces 貢獻 346 rows，即 `90.10%`。

| LHTR directional interface | at-capacity rows | target corridor? |
|---|---:|---:|
| 563→603 | 73 | yes |
| 603→643 | 68 | yes |
| 564→604 | 51 | yes |
| 683→16 | 38 | yes |
| 644→684 | 27 | yes |
| 602→642 | 21 | no |
| 16→56 | 18 | yes |
| 96→136 | 17 | yes |
| 95→135 | 16 | yes |

Traffic-Light 的 top RED/YELLOW links 與 queue saturation 的 top interfaces 高度重合，表示 color signal 有捕捉到 target-corridor hotspot。

## Loss attribution

LHTR 的 414 個 losses 在 v3 attribution 中全部是 **ISL-saturation-associated synthetic losses**，confidence 為 medium：

- exact attributed physical drops：0
- GSL-associated：0
- mixed：0
- unclassified：0

這只能說 losses 與 replay path 上的 ISL saturation 關聯，不能稱為已觀測到的 physical link drops。

## 綜合解釋

- SBR 並非完全沒選，也不是 policy 面對 cleaner SBR 時過度保守。
- Stretch-too-high 只有 0.9743%，不足以解釋主要差距。
- No-alternative 佔 26.1%，表示 candidate availability 有改善空間，但不是唯一問題。
- 最直接的問題是 128 次 SBR switch 只有 1 次落在 active-flow path；因此 target corridor 仍有 384 個 at-capacity rows 與 414 個 associated losses。
- 這與 LHTR 低於 LoHi 的結果一致：Traffic Light 看見 hotspot，但 offload decisions 大多沒有作用在實際承載流量的 forwarding entries。

# 9. Root cause classification

```text
Diagnosis category: B
```

**Evidence：**

1. Traffic-Light arithmetic、threshold 與 final max-severity 在 1,728,000 筆 samples 中全部一致。
2. 全網有 703 YELLOW、242 RED，且 73.86% colored samples 位於 target corridor。
3. 但 sampled full BR path 有 99.9925% 為 GREEN；recorded local BR color 更接近全綠。
4. 只要 SBR full path 比 BR 更乾淨，128/128 都選 SBR，故 A「policy 過度保守」不是主要診斷。
5. Stretch-too-high 只佔 0.9743%，故 D 不是主要診斷。
6. No-alternative 佔 26.1%，C 是次要限制，但 sampled log 仍有 220 萬筆不同 SBR，不能說 SBR generation 全面失效。
7. 128 次 SBR selection 只有 1 次命中 active-flow replay path，最符合 B 類的「network 有壅塞色，但實際 BR decision context 很少經過該壅塞色」。
8. `br_max_color` 實際是 local/border color，而非 full-path maximum；這是 diagnostics 語意限制。fstate 也有 0.0470% mismatch，但沒有 active-path PDR 影響證據，因此 E 目前是次要風險，不是主分類。

**Most likely root cause：**

LHTR 的 Traffic-Light signal 能正確辨識 target-corridor congestion，SBR selector 也能在 eligible case 正確切換；但 decision color 與 route-table selection 的作用範圍大多沒有對齊當下 active traffic。下游 hotspot 沒有被充分傳遞成 active-flow forwarding entry 上的非 GREEN BR decision，導致實際 offload 幾乎為零。

**Recommended next action：**

先明確分析並記錄 local link color、full candidate path max color、network hotspot 與 active-flow path 的關係，再決定是否需要修改 path-level signal propagation、candidate generation 或 policy。現在直接調 threshold/stretch 缺乏證據。

# 10. 下一步 task

唯一建議：

```text
lhtr_analyze_br_path_color_vs_network_color.md
```

**為什麼選它：**

目前已排除 Traffic-Light 算錯、完全沒有 SBR、或 cleaner SBR 被 policy 忽略。最大缺口是 diagnostics 的 `br_max_color` 名稱與實際 local/border scope 不一致，而且 SBR selection 幾乎未落在 active flow。先把這個關係量化，才能知道之後應改 signal propagation、candidate generation，或只需改善實驗情境。

**應修改的地方：**

- 在 LHTR diagnostics 明確分欄：
  - `br_local_link_color`
  - `br_full_path_max_color`
  - `sbr_local_link_color`
  - `sbr_full_path_max_color`
  - `color_scope`
- 在 packet-delivery analysis 加入：
  - `decision_on_active_flow_path`
  - `active_flow_id`
  - `br/sbr_intersects_target_corridor`
  - active-flow decision 的完整 reason/color 聚合
- 對 decision 後的 fstate rewrite 記錄明確原因，例如 cycle cleanup。
- 增加 diagnostics schema、color reconstruction 與 active-path join 的測試。

**不應修改的地方：**

- 不改 BR/SBR selection policy。
- 不改 QOR/TQOR threshold。
- 不改 delay-based cost。
- 不改 1.5 stretch threshold。
- 不直接改 SBR candidate generation。
- 不直接跑 200s。

**修改後如何驗證：**

1. 先用 unit tests 驗證 local/full-path color 與 final fstate rewrite reason。
2. 用短 10s diagnostics smoke run 確認 schema、row count、disabled mode 與其他 algorithms 不受影響。
3. 再以相同 `src754-dst785, load=1.4, bg=16, 60s` 做 controlled rerun。
4. 驗證 active-flow path 上每個 non-green BR 是否有 SBR、是否切換、是否避開 target corridor。
5. 最後才比較 PDR、384 at-capacity rows 與 414 associated losses是否下降。

# 11. 論文敘事影響

**中文：**

本次 diagnostics 顯示，LHTR 的 Traffic-Light 計算與 BR/SBR 選擇規則在機制層面是有效的：target corridor 的壅塞可被辨識，且當 admissible SBR 比 BR 更乾淨時，LHTR 會一致地切換。然而，這些切換幾乎都發生在未承載當下實驗流量的 route-table entries，因此未能轉化為較低的 queue saturation 或較高的 PDR。論文不應將結果敘述為「LHTR 不會選 SBR」，而應表述為「local traffic-light decisions 與 active-flow congestion exposure 之間存在作用範圍落差」。這也解釋了為何 LHTR 在此 controlled hotspot 下略低於 LoHi。

**English:**

The diagnostics show that LHTR's traffic-light computation and BR/SBR selection rule are mechanically sound: congestion on the target corridor is detected, and every sampled admissible SBR that is cleaner than its BR is selected. However, almost all SBR selections occur on routing-table entries that are not carrying the active experiment flows at that time, so the mechanism does not translate into lower queue saturation or higher PDR. The paper should therefore avoid claiming that LHTR fails to select SBRs; the more accurate interpretation is a scope mismatch between local traffic-light decisions and active-flow exposure to downstream congestion, which explains why LHTR remains slightly below LoHi in this controlled hotspot scenario.
