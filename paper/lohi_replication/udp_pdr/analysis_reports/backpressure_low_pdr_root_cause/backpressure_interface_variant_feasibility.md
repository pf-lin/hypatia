# Backpressure Interface-aware Queue Variant Feasibility

## Feasibility

目前 `queue_stats/queue_stats_*.csv` 提供 directed ISL edge queue，欄位是 `from,to,packet_max,byte_max`。
這足以把 `A->B` 當作 A 的 outgoing interface queue，也足以把 `B->A` 視為 B 的 return interface。
在 route-calculation 時，satellite graph 已知道 B 的其他 ISL neighbors，因此可取 `B->C` directed queue，
並排除 `C == A` 的 return interface。

現有資料沒有暴露 ns-3 interface id 本身，也沒有 per-destination commodity queue。
因此這個 variant 是 directed-link queue proxy，而不是 full multi-commodity Backpressure。

## Method comparison

| Method | Q_i | Q_j | Meaning | Expected risk |
| --- | --- | --- | --- | --- |
| node_total_queue_bytes | current node total backlog | neighbor node total backlog | coarse node pressure | mixes unrelated outgoing directions and commodities |
| interface_nonreturn_avg_bytes | current->neighbor directed queue | avg neighbor outgoing ISL queues excluding return | link-local forwarding pressure | can still choose wrong destination direction |
| interface_nonreturn_min_bytes | current->neighbor directed queue | min neighbor outgoing ISL queues excluding return | most optimistic forward interface | may chase an empty but irrelevant interface |

## Recommendation

`interface_nonreturn_avg_bytes` is more local and less identical to `node_total_queue_bytes`, but it remains a proxy.
It should be evaluated as a candidate baseline, not presented as true Backpressure.

## 10s smoke result

| queue_source | PDR | focus PDR | bg PDR | fallback | positive | loop | reached | replay success |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| node_total_queue_bytes | 0.0701 | 0.1122 | 0.0675 | 0.6835 | 0.3144 | 0.9350 | 0.0650 | 0.0195 |
| interface_nonreturn_avg_bytes | 0.0633 | 0.0006 | 0.0672 | 0.9741 | 0.0238 | 0.9900 | 0.0100 | 0.0996 |
| interface_nonreturn_min_bytes | 0.0622 | 0.0006 | 0.0661 | 0.9711 | 0.0268 | 0.9900 | 0.0100 | 0.0717 |

結果：`interface_nonreturn_avg_bytes` 和 `interface_nonreturn_min_bytes` 都可行且 diagnostics 有成功寫出，
但兩者都沒有改善 PDR。avg/min 的 focus PDR 都接近 0，loop ratio 也高於 node-total。
因此 interface-aware proxy 有助於說明 queue source 設計差異，但不足以直接升為 formal main baseline。
