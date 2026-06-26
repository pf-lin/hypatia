# Backpressure Low PDR Root-cause Analysis

## 1. 總結

PDR 低的主要原因不是 drain time，而是 routing-level Backpressure proxy 產生大量 forwarding-state loop。
node-total 10s smoke 的 diagnostic path loop ratio 是 0.9350 (187/200)，
path replay success ratio 只有 0.0195，t=5 與 t=8 的 focus route replay 都是 loop。

in-flight / drain 目前不是主要證據：traffic 在 8s 停止、simulation 到 10s，`tail_in_flight_possible_loss=0`。
loss attribution 顯示 exact physical queue/phy/routing/send failure loss 目前都是 0，
但有 19221 個 lost packets 和 ISL saturation overlap，另外 36991 個仍是 unclassified。

queue proxy 是關鍵問題之一。`node_total_queue_bytes` 把一個 satellite 的所有 outgoing queue 混成節點壓力，
不分 destination commodity，也不分 candidate outgoing direction，因此可能選到總 queue 比較低但轉送方向錯的 neighbor。

我已實作並跑完 `interface_nonreturn_avg_bytes` 與 `interface_nonreturn_min_bytes` 10s smoke。avg/min aggregate PDR 分別是 0.0633/0.0622，都低於 node-total 的 0.0701；focus PDR 則都只有 0.0006/0.0006，遠低於 node-total 的 0.1122。所以 interface-aware queue source 可行，但 avg/min variants 尚未讓 baseline 變得足夠可比較。

## 2. 使用資料

- node-total run: `/home/pflin/research/hypatia-pf/paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim10s_stop8s_isl10mbps_gsl100mbps_lohi_mgmt_legacy_bp_qauto_fbsp_oneweb_isls_moving_udp_pdr`
- interface avg run: `/home/pflin/research/hypatia-pf/paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim10s_stop8s_isl10mbps_gsl100mbps_lohi_mgmt_legacy_bp_qifnavgbytes_fbsp_oneweb_isls_moving_udp_pdr`
- interface min run: `/home/pflin/research/hypatia-pf/paper/lohi_replication/udp_pdr/runs/run_core_isl_hotspot_specific_src754_dst785_load_1p6x_bg_flow_count_32_sim10s_stop8s_isl10mbps_gsl100mbps_lohi_mgmt_legacy_bp_qifnminbytes_fbsp_oneweb_isls_moving_udp_pdr`
- Backpressure diagnostics: `backpressure_decision_log.csv`, `backpressure_summary.csv`, `backpressure_queue_source_summary.csv`, `backpressure_fallback_summary.csv`, `backpressure_path_stretch_summary.csv`, `backpressure_loop_check.csv`
- delivery diagnostics: `summary_by_algorithm.csv`, `per_flow_delivery.csv`, `loss_attribution_breakdown_v3.csv`, `path_replay_diagnostics.csv`, `udp_focus_rtt_timeseries.csv`, `udp_focus_path_timeseries.csv`

## 3. Root-cause analysis

| cause | evidence | severity | recommendation |
| --- | --- | --- | --- |
| path loop / ping-pong in forwarding state | node-total loop ratio 0.9350 (187/200), path replay success 0.0195, t=5/t=8 focus paths loop | critical | treat loops as the dominant failure mode; consider loop guard only as a separate stabilized proxy |
| node_total_queue_bytes is a weak non-commodity proxy | fallback ratio 0.6835, positive-pressure ratio 0.3144, but positive paths still loop at 0.9740 | high | do not describe it as full multi-commodity Backpressure; keep it as a routing-level approximation |
| missing per-destination commodity queues | queue source summary reports per_destination_queue_available=false | high | true commodity queues are the rigorous fix, but likely too costly for the current thesis schedule |
| forwarding-state pipeline lag | routing is recomputed from previous queue snapshots every 0.1s, then installed as static forwarding state | medium | document this as a routing-level proxy, not packet-level dynamic Backpressure |
| ISL saturation around looped paths | node-total saturation-associated loss 19221/56212; exact physical queue/phy/routing losses are zero | medium | interpret saturation as associated evidence, not exact root attribution |
| in-flight/drain time | traffic stops at 8.0s, simulation ends at 10.0s, tail_in_flight_possible_loss=0 | low | add late_arrivals_after_traffic_stop / estimated_inflight_at_end diagnostics if extending this analysis |
| interface_nonreturn_avg_bytes is feasible but not sufficient | PDR 0.0633 vs node-total 0.0701; focus PDR 0.0006 vs 0.1122; loop ratio 0.9900 | high | do not promote this interface proxy to formal baseline without explicit stabilization or commodity queues |
| interface_nonreturn_min_bytes is feasible but not sufficient | PDR 0.0622 vs node-total 0.0701; focus PDR 0.0006 vs 0.1122; loop ratio 0.9900 | high | do not promote this interface proxy to formal baseline without explicit stabilization or commodity queues |

## 4. Node-total queue source 分析

`node_total_queue_bytes` 的 `Q_i` 和 `Q_j` 都是 satellite-level total backlog。
這會把所有 outgoing interface、所有 flow、所有 destination 的 queue 混在一起。
對 routing decision 來說，它只能回答「哪個節點總體比較塞」，不能回答「A 經由 B 往 destination 轉送是否比較合理」。

node-total smoke 的 weighted fallback ratio 是 0.6835，positive pressure ratio 是 0.3144。
這不是單純 positive pressure 太少；diagnostic path 裡只要路徑包含 positive-pressure decision，
loop rate 是 0.9740。也就是 positive pressure proxy 本身常常把 forwarding state 推進 loop。

selected queue/weight distribution 摘要：

- queue_current mean/p95: 30331.6641 / 147312.0000
- queue_neighbor mean/p95: 8305.4195 / 65050.0000
- queue_diff mean/p95: 28089.5261 / 141536.0000
- selected_weight mean/p95: 280895261400.0000 / 1415360000000.0000

## 5. Interface-aware queue source 評估

interface-aware proxy 可行，因為 `queue_stats` 已經有 directed edge queue (`from,to,packet_max,byte_max`)。
目前沒有直接使用 ns-3 interface id，但 directed edge `A->B` 已能代表 A 對 B 的 outgoing ISL queue；
`B->A` 可視為 return interface，B 的其他 graph neighbors 則可形成 non-return outgoing interfaces。

它與 node-total 不本質相同：node-total 是 coarse node pressure；interface-aware 是 directed link-local pressure。
但它仍然不是 full Backpressure，因為它仍缺 per-destination commodity queue，也沒有 per-packet 動態控制。
這次 avg/min variant smoke 顯示只改 queue source 不足以移除 loop 或提升 PDR。

## 6. 如果有實作 interface-aware variant

已實作：

- `interface_nonreturn_avg_bytes`
- `interface_nonreturn_min_bytes`

定義：

- `Q_i = queue(current->candidate_neighbor)`
- `Q_j = avg/min queue(candidate_neighbor->nonreturn_outgoing_ISL)`
- 若 candidate neighbor 沒有 non-return outgoing interface，fallback reason 記為 `no_forward_interface`

新增 diagnostics 欄位：

- decision log: `current_out_interface`, `neighbor_return_interface`, `neighbor_forward_interfaces`, `queue_current_out_interface`, `queue_neighbor_forward_avg`, `queue_neighbor_forward_min`, `interface_queue_source_available`, `nonreturn_interface_count`
- summary: `interface_source_success_ratio`, `no_forward_interface_count`, `interface_mapping_missing_count`

修改檔案：

- `satgenpy/satgen/dynamic_state/algorithm_backpressure_over_isls.py`
- `paper/lohi_replication/udp_pdr/dynamic_run_list.py`
- `paper/lohi_replication/udp_pdr/analyze_backpressure_root_cause.py`

## 7. Smoke comparison

| queue_source | PDR | focus PDR | bg PDR | fallback | positive | loop | reached | replay success |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| node_total_queue_bytes | 0.0701 | 0.1122 | 0.0675 | 0.6835 | 0.3144 | 0.9350 | 0.0650 | 0.0195 |
| interface_nonreturn_avg_bytes | 0.0633 | 0.0006 | 0.0672 | 0.9741 | 0.0238 | 0.9900 | 0.0100 | 0.0996 |
| interface_nonreturn_min_bytes | 0.0622 | 0.0006 | 0.0661 | 0.9711 | 0.0268 | 0.9900 | 0.0100 | 0.0717 |

node-total focus paths:

```text
t=0.0 754_to_785: success; forward=754;557;558;559;520;521;522;523;563;603;643;683;16;56;96;136;176;216;785; reverse=785;216;176;136;96;56;16;683;643;603;563;523;522;521;520;559;558;557;754
t=0.0 785_to_754: success; forward=785;216;176;136;96;56;16;683;643;603;563;523;522;521;520;559;558;557;754; reverse=754;557;558;559;520;521;522;523;563;603;643;683;16;56;96;136;176;216;785
t=5.0 754_to_785: forward:loop;reverse:loop; forward=754;557;517;518;517; reverse=785;216;217;177;178;138;178
t=5.0 785_to_754: forward:loop;reverse:loop; forward=785;216;217;177;178;138;178; reverse=754;557;517;518;517
t=8.0 754_to_785: forward:loop;reverse:loop; forward=754;557;556;596;636;676;716;717;718;719;680;719; reverse=785;216;256;296;256
t=8.0 785_to_754: forward:loop;reverse:loop; forward=785;216;256;296;256; reverse=754;557;556;596;636;676;716;717;718;719;680;719
```

interface avg focus paths:

```text
t=0.0 754_to_785: success; forward=754;557;558;559;520;521;522;523;563;603;643;683;16;56;96;136;176;216;785; reverse=785;216;176;136;96;56;16;683;643;603;563;523;522;521;520;559;558;557;754
t=0.0 785_to_754: success; forward=785;216;176;136;96;56;16;683;643;603;563;523;522;521;520;559;558;557;754; reverse=754;557;558;559;520;521;522;523;563;603;643;683;16;56;96;136;176;216;785
t=5.0 754_to_785: forward:loop;reverse:loop; forward=754;557;558;559;520;521;522;523;563;603;643;603; reverse=785;216;176;136;96;56;16;56
t=5.0 785_to_754: forward:loop;reverse:loop; forward=785;216;176;136;96;56;16;56; reverse=754;557;558;559;520;521;522;523;563;603;643;603
t=8.0 754_to_785: forward:loop;reverse:loop; forward=754;557;558;559;520;521;522;523;563;603;643;603; reverse=785;216;176;136;96;56;16;56
t=8.0 785_to_754: forward:loop;reverse:loop; forward=785;216;176;136;96;56;16;56; reverse=754;557;558;559;520;521;522;523;563;603;643;603
```

interface min focus paths:

```text
t=0.0 754_to_785: success; forward=754;557;558;559;520;521;522;523;563;603;643;683;16;56;96;136;176;216;785; reverse=785;216;176;136;96;56;16;683;643;603;563;523;522;521;520;559;558;557;754
t=0.0 785_to_754: success; forward=785;216;176;136;96;56;16;683;643;603;563;523;522;521;520;559;558;557;754; reverse=754;557;558;559;520;521;522;523;563;603;643;683;16;56;96;136;176;216;785
t=5.0 754_to_785: forward:loop;reverse:loop; forward=754;557;558;559;520;521;522;523;563;603;643;603; reverse=785;216;176;136;96;56;16;56
t=5.0 785_to_754: forward:loop;reverse:loop; forward=785;216;176;136;96;56;16;56; reverse=754;557;558;559;520;521;522;523;563;603;643;603
t=8.0 754_to_785: forward:loop;reverse:loop; forward=754;557;558;559;520;521;522;523;563;603;643;603; reverse=785;216;176;136;96;56;16;56
t=8.0 785_to_754: forward:loop;reverse:loop; forward=785;216;176;136;96;56;16;56; reverse=754;557;558;559;520;521;522;523;563;603;643;603
```

## 8. 如何讓 Backpressure 變得可比較

最務實建議：不要直接把目前 node-total、interface-avg 或 interface-min 放進 formal main table 當主 baseline。
短期可做三步：

1. 先不要跑 H80 60s formal；avg/min 都仍 loop，直接 formal 只會把不穩定 proxy 放大。
2. 新增一個明確標註的 loop-suppressed proxy，例如 `--backpressure-loop-guard immediate_reverse`，並把它稱作 practical stabilized proxy。
3. 若論文時間允許，才考慮 true per-destination commodity queue instrumentation；這是最嚴謹但成本最高的方案。

若畢業時程吃緊，我會把 Backpressure 放在「queue-driven routing-level proxy baseline / diagnostic baseline」位置，
主表可只放穩定、可解釋的 baseline；Backpressure 的 low-PDR 結果可在 appendix 或 ablation 解釋。

## 9. Thesis wording suggestion

本研究額外實作了一個 routing-level Backpressure proxy 作為 queue-driven baseline。
由於 Hypatia/ns-3 實驗流程目前沒有 per-destination commodity queue，
此 baseline 使用 node-total 或 directed-interface queue 作為壓力近似，並以週期性 forwarding-state update 取代 packet-level dynamic Backpressure。
10 秒 hotspot smoke 顯示，低 PDR 主要來自 forwarding-state loop 與 proxy pressure mismatch，
而非單純 drain time 不足。interface-aware queue source 能更局部地描述 outgoing link pressure，
但 10 秒結果顯示它仍無法替代真正 commodity queue，因此本文將其定位為可解釋的 proxy baseline，
而非 full multi-commodity Backpressure。

## 10. 下一步命令

暫時不建議直接跑 H80 60s formal。min variant 已跑完，下一步若要繼續 Backpressure baseline，建議做 loop-suppressed smoke 或 no-route diagnostic，而不是直接 formal。

```bash
cd paper/lohi_replication/udp_pdr
python analyze_backpressure_root_cause.py
```

## 11. Commit 建議

```text
analysis(backpressure): diagnose low PDR and add interface queue proxy
```
