# Recommendation

建議把 `forward_progress_hop` 作為 H80 60s formal 的 stabilized Backpressure proxy variant 候選，但在圖表和文字中必須明確標註它是 restricted-route / loop-suppressed queue-proxy Backpressure，不是 original pure Backpressure。

建議 formal 前先跑：

```bash
python run_hotspot_5level_60s_formal.py \
  --scenarios H80 \
  --simulation-end-time-s 60 \
  --traffic-stop-time-s 58 \
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr algorithm_backpressure_over_isls \
  --backpressure-queue-source node_total_bytes \
  --backpressure-fallback shortest_path \
  --backpressure-loop-guard forward_progress_hop \
  --force
```

若要把 queue-source sensitivity 放進 appendix，再補一組：

```bash
python run_hotspot_5level_60s_formal.py \
  --scenarios H80 \
  --simulation-end-time-s 60 \
  --traffic-stop-time-s 58 \
  --algorithms algorithm_backpressure_over_isls \
  --backpressure-queue-source interface_nonreturn_avg_bytes \
  --backpressure-fallback shortest_path \
  --backpressure-loop-guard forward_progress_hop \
  --force
```
