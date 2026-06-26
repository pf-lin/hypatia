# Backpressure loop suppression smoke analysis

## 方法定位

這次新增的是 restricted-route / loop-suppressed queue-proxy Backpressure variant。它受到 Backpressure literature 中 desirable-route restriction 的啟發，但不是 full multi-commodity Backpressure scheduler，也不是把 hop/distance 加進 weight 的 distance-based 或 hop-based Backpressure。

實作中的 queue-differential weight 保持不變：

```text
weight(i, j) = max(Q_i - Q_j, 0) * C_ij
```

`forward_progress_hop` 只做候選過濾：對目的地 `d`，只有 `dist_hop(j, d) < dist_hop(i, d)` 的 neighbor `j` 才合法。若過濾後沒有正壓力候選，仍依 fallback policy 使用 shortest path，並在 diagnostics 中記錄原因。

## Feasibility audit

- Immediate reverse guard：目前 fstate 是 `current_node + destination -> next_hop`，不是 `previous_hop + current_node + destination -> next_hop`。ns-3 routing pipeline 也沒有用這個 fstate 表達 per-packet previous-hop-dependent decision。因此 immediate reverse guard 可以在 path replay diagnostics 中觀察，但不適合作為目前 pipeline 的真正 forwarding guard；若要實作，需要改 routing state/interface，成本過高。
- Forward-progress hop guard：route generation 已知道 current node、candidate neighbor、destination、snapshot topology，並可用 satellite-only ISL graph 算 hop shortest path。因此 Level 2 可行，而且與 forwarding-state graph 最一致。

## Smoke comparison

| method | aggregate PDR | focus PDR | bg PDR | fallback | candidate filtered | loop | replay success |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| node_total / no guard | 0.0701 | 0.1122 | 0.0675 | 68.4% | 0.0% | 93.5% | 1.9% |
| interface_avg / no guard | 0.0633 | 0.0006 | 0.0672 | 97.4% | 0.0% | 99.0% | 10.0% |
| node_total / forward_progress_hop | 0.7237 | 0.4685 | 0.7397 | 96.5% | 51.8% | 0.0% | 100.0% |
| interface_avg / forward_progress_hop | 0.4661 | 0.0135 | 0.4944 | 97.9% | 52.4% | 0.0% | 100.0% |

## 結果判讀

1. no-guard node-total 的 PDR 很低，主要不是因為沒有 queue signal，而是 destination semantics 不足造成 loop。它的 positive-pressure ratio 有 31.4%，但 path loop ratio 達 93.5%，表示 queue pressure 常把封包推向錯方向。
2. no-guard interface avg 並沒有改善 PDR，反而讓 fallback ratio 到 97.4%。原因是 directed interface queue proxy 更局部，能產生的正壓力候選更少；缺少 destination commodity queue 時，局部 queue granularity 不能保證朝目的地前進。
3. forward-progress-hop 大幅改善 node-total PDR：aggregate PDR 從 0.0701 到 0.7237，loop ratio 從 93.5% 到 0.0%。原因是 guard 移除了會增加目的地 hop distance 的候選，壓住 static fstate 中最致命的錯方向/循環選擇。
4. interface avg + forward-progress-hop 也把 loop ratio 壓到 0.0%、replay success 拉到 100.0%，但 aggregate PDR 只有 0.4661，明顯低於 node-total guard 的 0.7237。這表示 loop 是第一主因；loop 消除後，interface avg proxy 仍太保守，合法候選中常沒有正壓力，fallback ratio 維持在 97.9%，因此吞吐恢復不如 node-total guard。

## Root cause conclusion

H80 10s smoke 支持以下結論：低 PDR 的根因不是 drain time，也不是單純 queue source granularity，而是 queue-proxy Backpressure 沒有 per-destination commodity queue，導致 queue pressure 缺少 destination semantics。在 Hypatia 的 static forwarding-state pipeline 裡，這會形成 routing loop。Forward-progress restricted route 是目前最小、可落地、且不改 weight 的穩定化方法。

## Thesis wording suggestion

建議論文中稱為 `restricted-route queue-proxy Backpressure` 或 `loop-suppressed Backpressure proxy baseline`。避免稱為 `pure Backpressure`、`full multi-commodity Backpressure`、`distance-based Backpressure` 或 `hop-based Backpressure`。
