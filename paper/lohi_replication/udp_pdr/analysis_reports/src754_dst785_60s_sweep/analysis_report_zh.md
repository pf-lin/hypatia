# src754-dst785 UDP/PDR 60s Sweep 分析報告

分析日期：2026-06-10

## 1. 總結結論

- 四組 run、每組四個 algorithms 全部成功完成。每個 algorithm 都有 `finished.txt`、`BASIC SIMULATION END`、600 個 `fstate_*`、599 個 `queue_stats_*` 與 timing results；console 未發現 fatal、segfault、assertion、traceback 或 missing config。
- 就 controlled ISL congestion 的乾淨度而言，最佳 setting 是 `load=1.4, bg=16`。Baseline aggregate PDR 已降至 `0.682972`，但所有 loss 都是 ISL-associated，沒有 GSL/mixed attribution；Queue-aware PDR 為 `0.999640`，可作為此 setting 的 upper bound。
- `754<->785` 的 flow selection 明顯比先前記錄的 `738<->793` 更適合作為 main scenario 候選：四組均全數由 strict phase 選滿、zero-overlap 為 0、top estimated edge 在 target corridor，target/non-focus load ratio 為 `3.071-3.378`。這個結論是 scenario construction 層面的比較；本 workspace 沒有找到可直接重算的 `738<->793` 對照 run。
- 四組都沒有得到預期的 `Baseline < LoHi < LHTR < Queue-aware`。實際 aggregate PDR 中，LoHi 四組都高於 LHTR。
- Queue-aware 只有 `1.4/bg16` 與 `1.8/bg24` 是最高 PDR；在 `1.4/bg24` 與 `1.8/bg16` 反而低於 LoHi，因此不能把 Queue-aware 在所有 setting 下都描述成 empirical upper bound。
- Baseline loss 四組都是 100% ISL-associated，且 89.0%-100% loss 可只用 target-corridor saturated interfaces 解釋。所有 algorithms 的 loss 幾乎都至少與一個 target-corridor saturated interface 重疊，但 adaptive routing 在高負載下也出現 mixed ISL/GSL evidence。
- GSL 不主導任何 run，`gsl_saturation_associated_loss` 全部為 0；但 `1.8/bg16` 的 LoHi/LHTR mixed loss 分別為 64.5%/54.8%，`1.8/bg24` 的 Queue-aware/LHTR mixed loss分別為 29.2%/21.3%，不適合稱為純 ISL outcome。
- LHTR traffic-light 確實大量觸發 YELLOW/RED，不是因為燈號完全未觸發而退化。然而 run 時 `LHTR_ENABLE_DIAGNOSTICS=0`，沒有 BR/SBR decision CSV，無法證明 SBR 選取次數、觸發原因或是否避開 target corridor。
- 目前不應直接進 200s formal。

**Decision: C**

**Best candidate setting:** `load=1.4, bg=16`，待補齊 LHTR BR/SBR diagnostics 並確認/修正決策後再做 60s validation。

**Reason:** Scenario 本身乾淨且壓力足夠，但 LHTR 四組 aggregate PDR 都輸給 LoHi，且缺少可判斷 BR/SBR 行為的必要 diagnostics。

**Recommended next action:** `lhtr_add_br_sbr_diagnostics.md`。目前 code 已有 diagnostics writer，最重要的是讓實驗明確啟用並保存 `lhtr_traffic_light_color_summary.csv`、`lhtr_qor_tqor_samples.csv`、`lhtr_br_sbr_decision_log.csv`、`lhtr_br_sbr_summary.csv` 與 `lhtr_decision_reason_summary.csv`。

## 2. Run folders

| run_folder | load | bg | duration | traffic_stop | exists | notes |
|---|---:|---:|---:|---:|---|---|
| `run_core_isl_hotspot_specific_src754_dst785_load_1p4x_bg_flow_count_16_oneweb_isls_moving_udp_pdr` | 1.4 | 16 | 60s | 58s | yes | 名稱不含 duration |
| `run_core_isl_hotspot_specific_src754_dst785_load_1p4x_bg_flow_count_24_oneweb_isls_moving_udp_pdr` | 1.4 | 24 | 60s | 58s | yes | 名稱不含 duration |
| `run_core_isl_hotspot_specific_src754_dst785_load_1p8x_bg_flow_count_16_oneweb_isls_moving_udp_pdr` | 1.8 | 16 | 60s | 58s | yes | 名稱不含 duration |
| `run_core_isl_hotspot_specific_src754_dst785_load_1p8x_bg_flow_count_24_oneweb_isls_moving_udp_pdr` | 1.8 | 24 | 60s | 58s | yes | 名稱不含 duration |

未來若要生成 200s run，必須先加入 duration tag 或備份 60s folders，否則 `--force` 會有覆蓋風險。

## 3. Run 完整性

下表的 `errors=-` 表示指定 fatal/error pattern 未命中。四個 algorithms 的 metadata/config 均確認 focus pair `754/785`、simulation end `60s`、traffic stop `58s`；load/bg 由 schedule、flow metadata 與 run name 交叉確認。

| load/bg | algorithm | finished | console_ok | fstate | queue_stats | timing | errors |
|---|---|---|---|---:|---:|---|---|
| 1.4/16 | Baseline | yes | yes | 600 | 599 | yes | - |
| 1.4/16 | Queue-aware | yes | yes | 600 | 599 | yes | - |
| 1.4/16 | LoHi | yes | yes | 600 | 599 | yes | - |
| 1.4/16 | LHTR | yes | yes | 600 | 599 | yes | - |
| 1.4/24 | Baseline | yes | yes | 600 | 599 | yes | - |
| 1.4/24 | Queue-aware | yes | yes | 600 | 599 | yes | - |
| 1.4/24 | LoHi | yes | yes | 600 | 599 | yes | - |
| 1.4/24 | LHTR | yes | yes | 600 | 599 | yes | - |
| 1.8/16 | Baseline | yes | yes | 600 | 599 | yes | - |
| 1.8/16 | Queue-aware | yes | yes | 600 | 599 | yes | - |
| 1.8/16 | LoHi | yes | yes | 600 | 599 | yes | - |
| 1.8/16 | LHTR | yes | yes | 600 | 599 | yes | - |
| 1.8/24 | Baseline | yes | yes | 600 | 599 | yes | - |
| 1.8/24 | Queue-aware | yes | yes | 600 | 599 | yes | - |
| 1.8/24 | LoHi | yes | yes | 600 | 599 | yes | - |
| 1.8/24 | LHTR | yes | yes | 600 | 599 | yes | - |

## 4. Focus selection / corridor diagnostics

兩個 focus directions 均為 `754->785` 與 `785->754`。Per-flow rate 依 reference background count 4 計算：load 1.4 為 `2.333333 Mbps`，load 1.8 為 `3.0 Mbps`。所有 selected background flows 都來自 strict phase。

| load/bg | selected_bg | strict | zero | avg overlap | min/max | target/non-focus | top edge | endpoint max | interface max | flow hash |
|---|---:|---:|---:|---:|---|---:|---|---:|---:|---|
| 1.4/16 | 16 | 16 | 0 | 19.250 | 14/28 | 3.071 | `16->56`, target | 0.233 | 0.700 | `9fb032ccffa6eb89` |
| 1.4/24 | 24 | 24 | 0 | 16.583 | 10/28 | 3.378 | `16->56`, target | 0.233 | 0.700 | `3559cb11db9dd9d5` |
| 1.8/16 | 16 | 16 | 0 | 17.750 | 12/28 | 3.098 | `16->56`, target | 0.300 | 0.600 | `0b7fea4f05f06d87` |
| 1.8/24 | 24 | 24 | 0 | 14.750 | 5/28 | 3.204 | `16->56`, target | 0.300 | 0.600 | `e8c647e9f8225eea` |

四組 endpoint/interface ratios 都低於 cap `0.8`。`bg=24` 仍不需要 fallback，支持新 focus pair 有較寬且可控制的 overlap pool。

## 5. PDR 結果

`background_pdr` 是由 per-flow table 以 background sent/received packets 重新彙整。

| load/bg | algorithm | aggregate | focus | background | min | p5 | lost | failed |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1.4/16 | Baseline | 0.682972 | 0.534004 | 0.701593 | 0.159514 | 0.235108 | 64,358 | 0 |
| 1.4/16 | Queue-aware | 0.999640 | 0.999778 | 0.999623 | 0.998936 | 0.999011 | 73 | 0 |
| 1.4/16 | LoHi | 0.998557 | 0.998493 | 0.998565 | 0.996099 | 0.996325 | 293 | 0 |
| 1.4/16 | LHTR | 0.997961 | 0.998094 | 0.997944 | 0.994591 | 0.994817 | 414 | 0 |
| 1.4/24 | Baseline | 0.473246 | 0.386505 | 0.480475 | 0.093102 | 0.103720 | 154,459 | 0 |
| 1.4/24 | Queue-aware | 0.990789 | 0.994769 | 0.990457 | 0.987498 | 0.987697 | 2,701 | 0 |
| 1.4/24 | LoHi | 0.995515 | 0.996897 | 0.995400 | 0.989448 | 0.989737 | 1,315 | 0 |
| 1.4/24 | LHTR | 0.992576 | 0.993572 | 0.992493 | 0.983153 | 0.983907 | 2,177 | 0 |
| 1.8/16 | Baseline | 0.601238 | 0.754172 | 0.582121 | 0.091448 | 0.254824 | 104,077 | 0 |
| 1.8/16 | Queue-aware | 0.992379 | 0.995931 | 0.991935 | 0.987103 | 0.987221 | 1,989 | 0 |
| 1.8/16 | LoHi | 0.995264 | 0.995724 | 0.995207 | 0.986552 | 0.987900 | 1,236 | 0 |
| 1.8/16 | LHTR | 0.994467 | 0.996931 | 0.994159 | 0.988207 | 0.988266 | 1,444 | 0 |
| 1.8/24 | Baseline | 0.432698 | 0.388724 | 0.436362 | 0.021172 | 0.074966 | 213,873 | 0 |
| 1.8/24 | Queue-aware | 0.976814 | 0.990759 | 0.975652 | 0.965241 | 0.966948 | 8,741 | 0 |
| 1.8/24 | LoHi | 0.968812 | 0.977276 | 0.968106 | 0.951862 | 0.954397 | 11,758 | 0 |
| 1.8/24 | LHTR | 0.965056 | 0.971586 | 0.964511 | 0.946000 | 0.946345 | 13,174 | 0 |

排序：

- `1.4/16`: Baseline < LHTR < LoHi < Queue-aware
- `1.4/24`: Baseline < Queue-aware < LHTR < LoHi
- `1.8/16`: Baseline < Queue-aware < LHTR < LoHi
- `1.8/24`: Baseline < LHTR < LoHi < Queue-aware

LHTR 在 `1.8/bg16` 的 focus PDR 比 LoHi 高 `0.001207`，但 aggregate/background PDR 較低；不能據此宣稱整體優於 LoHi。

## 6. Queue / congestion 結果

`Icap/Gcap` 是 at-capacity timeline rows；`Tcap` 是其中位於 target corridor 的 ISL rows。所有 queue capacity 為 100 packets。

| load/bg | algorithm | max ISL/GSL | Icap | Gcap | Tcap | top congested interface | target? |
|---|---|---:|---:|---:|---:|---|---|
| 1.4/16 | Baseline | 100/0 | 181,190 | 0 | 181,190 | `ISL:136->96` | yes |
| 1.4/16 | Queue-aware | 100/0 | 74 | 0 | 52 | `ISL:15->55` | yes |
| 1.4/16 | LoHi | 100/0 | 334 | 0 | 323 | `ISL:15->55` | yes |
| 1.4/16 | LHTR | 100/0 | 384 | 0 | 346 | `ISL:563->603` | yes |
| 1.4/24 | Baseline | 100/0 | 230,656 | 0 | 230,656 | `ISL:136->96` | yes |
| 1.4/24 | Queue-aware | 100/100 | 2,646 | 24 | 1,003 | `ISL:136->96` | yes |
| 1.4/24 | LoHi | 100/0 | 1,316 | 0 | 780 | `ISL:684->15` | yes |
| 1.4/24 | LHTR | 100/0 | 2,053 | 0 | 1,119 | `ISL:603->643` | yes |
| 1.8/16 | Baseline | 100/0 | 212,754 | 0 | 203,680 | `ISL:136->96` | yes |
| 1.8/16 | Queue-aware | 100/100 | 1,837 | 26 | 863 | `ISL:176->136` | yes |
| 1.8/16 | LoHi | 100/100 | 1,104 | 145 | 853 | `GSL:176->-1` | no |
| 1.8/16 | LHTR | 100/100 | 1,160 | 118 | 788 | `ISL:564->604` | yes |
| 1.8/24 | Baseline | 100/0 | 292,745 | 0 | 283,671 | `ISL:136->96` | yes |
| 1.8/24 | Queue-aware | 100/100 | 7,499 | 156 | 2,561 | `ISL:176->136` | yes |
| 1.8/24 | LoHi | 100/0 | 10,776 | 0 | 3,945 | `ISL:136->96` | yes |
| 1.8/24 | LHTR | 100/100 | 11,542 | 56 | 3,347 | `ISL:603->643` | yes |

結論：

- Baseline congestion 幾乎完全落在 target corridor，證明 traffic generation 確實建立 target ISL bottleneck。
- `1.4/bg16` 最乾淨：所有 algorithms 的 GSL queue max 都是 0，Queue-aware 將 ISL at-capacity rows 從 181,190 降至 74。
- LoHi/LHTR 仍會經過 saturated target links。LHTR 的 Icap 在四組都高於 LoHi，沒有顯示 queue advantage。
- 高負載的 adaptive routing 會把部分壓力移到 non-target ISL 或 GSL；`1.8/bg16` 的 LoHi top interface 已是 GSL。

## 7. Loss Attribution v3

表中 `I/G/M/T/U` 分別是 ISL-associated、GSL-associated、mixed、tail、unclassified。Exact physical queue/PHY、routing 與 send failure 在全部 16 組均為 0；path replay success 與 attribution coverage 都是 1.0，unclassified 都是 0。這些是 saturation association，不是 physical drop proof。

| load/bg | algorithm | synthetic | I | G | M | T | U | target-intersect |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1.4/16 | Baseline | 64,358 | 64,358 | 0 | 0 | 0 | 0 | 100.0% |
| 1.4/16 | Queue-aware | 73 | 73 | 0 | 0 | 0 | 0 | 100.0% |
| 1.4/16 | LoHi | 293 | 293 | 0 | 0 | 0 | 0 | 100.0% |
| 1.4/16 | LHTR | 414 | 414 | 0 | 0 | 0 | 0 | 99.8% |
| 1.4/24 | Baseline | 154,459 | 154,459 | 0 | 0 | 0 | 0 | 100.0% |
| 1.4/24 | Queue-aware | 2,701 | 2,312 | 0 | 389 | 0 | 0 | 100.0% |
| 1.4/24 | LoHi | 1,315 | 1,315 | 0 | 0 | 0 | 0 | 99.8% |
| 1.4/24 | LHTR | 2,177 | 2,177 | 0 | 0 | 0 | 0 | 100.0% |
| 1.8/16 | Baseline | 104,077 | 104,077 | 0 | 0 | 0 | 0 | 100.0% |
| 1.8/16 | Queue-aware | 1,989 | 1,772 | 0 | 217 | 0 | 0 | 100.0% |
| 1.8/16 | LoHi | 1,236 | 439 | 0 | 797 | 0 | 0 | 100.0% |
| 1.8/16 | LHTR | 1,444 | 653 | 0 | 791 | 0 | 0 | 98.2% |
| 1.8/24 | Baseline | 213,873 | 213,873 | 0 | 0 | 0 | 0 | 100.0% |
| 1.8/24 | Queue-aware | 8,741 | 6,185 | 0 | 2,556 | 0 | 0 | 100.0% |
| 1.8/24 | LoHi | 11,758 | 11,758 | 0 | 0 | 0 | 0 | 100.0% |
| 1.8/24 | LHTR | 13,174 | 10,371 | 0 | 2,803 | 0 | 0 | 100.0% |

Baseline 的 target-only association 比例為 `100.0%, 100.0%, 89.6%, 89.0%`。Adaptive algorithms 的 target-intersect 很高，但常同時重疊 non-target saturated ISL，因此只能說 target corridor 明確參與，不能說所有 loss 都只由 target corridor 造成。

## 8. LHTR Traffic-light / BR-SBR

Console 中的 YELLOW/RED 是每個 snapshot 的 final directional link-color observations 加總，不是 BR/SBR decision counts。

| load/bg | TL summaries | yellow link obs | red link obs | yellow snapshots | red snapshots | BR selected | SBR selected |
|---|---:|---:|---:|---:|---:|---|---|
| 1.4/16 | 583 | 702 | 242 | 367 | 193 | unavailable | unavailable |
| 1.4/24 | 583 | 2,434 | 823 | 564 | 435 | unavailable | unavailable |
| 1.8/16 | 583 | 1,952 | 495 | 548 | 296 | unavailable | unavailable |
| 1.8/24 | 584 | 7,360 | 2,818 | 582 | 574 | unavailable | unavailable |

目前實作中的 TQOR 是 next-hop satellite 的 outgoing queue sum，除以 `degree * buffer_size`，符合 next-hop satellite total queue occupancy rate，而不是 temporal queue occupancy ratio。Final color 取 current-link QOR color 與 next-hop TQOR color 中較嚴重者。

Run 沒有 diagnostics CSV，因為 diagnostics 由 `LHTR_ENABLE_DIAGNOSTICS` 控制且預設為 0。因此無法回答 SBR selected、yellow/red 原因、fallback count、SBR 是否避開 target corridor，以及 LHTR 是否實際 BR-only。LHTR 與 LoHi 的 594/600 個 fstate snapshots 不同，表示輸出沒有簡單退化成與 LoHi 完全相同，但這仍不是 SBR selection proof。

由結果只能保守判斷：traffic light 有觸發，但 LHTR queue saturation 與 loss 都沒有優於 LoHi，可能是 SBR 沒被有效選中、admissible SBR 不足、或 SBR 將壓力移到其他 interfaces；必須先補 decision diagnostics 才能選擇修正 policy 的方向。

## 9. Delay-based cost mode

四組設定一致：

| algorithm | queue cost mode | source | ISL capacity | packet size | transmission delay | confidence |
|---|---|---|---:|---:|---|---|
| Baseline | N/A | N/A | N/A | N/A | N/A | high |
| Queue-aware | delay | queue_bytes | 10,000,000 bps | 1500 B | true | high |
| LoHi | delay | queue_bytes | 10,000,000 bps | 1500 B | true | high |
| LHTR | delay | queue_bytes | 10,000,000 bps | 1500 B | true | high |

Console 沒有 NaN/inf。Shared cost helper 以 floating-point seconds 計算 propagation + transmission + queueing delay；queue bytes 本身轉成整數是資料型別需要，最後除法不會做整數截斷。沒有觀察到 scale、NaN、inf 或 final-cost truncation 證據。

本 sweep 的三個 adaptive algorithms 已是 delay-mode apples-to-apples comparison。Legacy Alpha Penalty 可留作後續 paper ablation，用來隔離 cost-model change 的影響，但不是目前 scenario selection 的第一優先。

## 10. 四組 setting 橫向排名

| rank | load/bg | cleanliness | baseline stress | LHTR vs LoHi | QA upper bound | ISL dominance | 200s |
|---:|---|---|---|---|---|---|---|
| 1 | 1.4/16 | 最乾淨，無 GSL/mixed | 足夠，PDR 0.683 | LHTR 較差 0.000596 | yes | 最強 | 暫不 |
| 2 | 1.8/24 | 壓力最大，但有 mixed | 很強，PDR 0.433 | LHTR 較差 0.003756 | yes | 強 | 暫不 |
| 3 | 1.4/24 | selection 乾淨，QA 有少量 mixed | 很強，PDR 0.473 | LHTR 較差 0.002939 | no | 強 | 暫不 |
| 4 | 1.8/16 | LoHi/LHTR mixed GSL evidence 高 | 足夠，PDR 0.601 | LHTR 較差 0.000797 | no | 較弱 | no |

`1.4/bg16` 最適合保留為 formal candidate，因為它已產生明顯 Baseline loss，同時避免高 load/bg 下的 GSL/mixed spillover。`1.8/bg24` 可作 stress-test setting，但不應取代乾淨主場景。

## 11. 下一階段 task

只推薦一個下一步：

```text
lhtr_add_br_sbr_diagnostics.md
```

具體目標是啟用既有 LHTR diagnostics，先以 `load=1.4, bg=16, 60s` 驗證：

- BR/SBR selected counts。
- SBR due to YELLOW/RED counts。
- no-admissible-SBR 與 fallback counts。
- selected SBR 是否避開 target corridor。
- selected route 是否實際安裝到 fstate。

在這一步完成前，不提供 200s command。

## 12. 論文敘事建議

中文：

> 我們先以固定、可重現的 flow-selection constraints，在候選 ground-station pairs 中選擇能形成集中 ISL corridor load、同時限制 endpoint 與 satellite-interface load 的 pair。Johannesburg-Fukuoka (`754<->785`) 在 16 與 24 個 background flows 下均可由 strict phase 完整選流，沒有 zero-overlap flow，且 target/non-focus estimated load ratio 穩定高於 3。60 秒 sweep 進一步顯示 Baseline loss 與 target-corridor ISL saturation 高度重疊，而低負載設定沒有 GSL-associated 或 mixed loss。正式場景的選擇因此依照事先定義的 corridor concentration、spillover risk、Baseline stress 與 attribution criteria，而不是依照哪個 routing algorithm 得到較有利的結果，以降低 cherry-picking 風險。

English:

> We selected the controlled-congestion pair using fixed, reproducible flow-selection constraints that favor concentrated ISL-corridor load while bounding endpoint and satellite-interface load. The Johannesburg-Fukuoka pair (`754<->785`) filled both 16- and 24-background-flow scenarios entirely in the strict phase, selected no zero-overlap flows, and maintained a target-to-non-focus estimated load ratio above 3. The 60-second sweep further showed that baseline loss strongly overlapped saturation on the target ISL corridor, while the lower-load setting exhibited no GSL-associated or mixed loss. We therefore select the formal scenario using pre-declared corridor concentration, spillover risk, baseline stress, and attribution criteria rather than choosing the setting that produces the most favorable ranking for any routing algorithm, reducing the risk of cherry-picking.
