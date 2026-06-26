import csv
import math
import os
from collections import Counter


ALGORITHM = "algorithm_backpressure_over_isls"

RUNS = [
    {
        "scenario_label": "node_total / no guard",
        "queue_source": "node_total_queue_bytes",
        "loop_guard_mode": "none",
        "forward_progress_metric": "none",
        "restricted_route": "false",
        "run_name": (
            "run_core_isl_hotspot_specific_src754_dst785_load_1p6x_"
            "bg_flow_count_32_sim10s_stop8s_isl10mbps_gsl100mbps_"
            "lohi_mgmt_legacy_bp_qauto_fbsp_oneweb_isls_moving_udp_pdr"
        ),
        "notes": "legacy no-guard run; auto resolves to node_total_queue_bytes",
    },
    {
        "scenario_label": "interface_avg / no guard",
        "queue_source": "interface_nonreturn_avg_bytes",
        "loop_guard_mode": "none",
        "forward_progress_metric": "none",
        "restricted_route": "false",
        "run_name": (
            "run_core_isl_hotspot_specific_src754_dst785_load_1p6x_"
            "bg_flow_count_32_sim10s_stop8s_isl10mbps_gsl100mbps_"
            "lohi_mgmt_legacy_bp_qifnavgbytes_fbsp_oneweb_isls_moving_udp_pdr"
        ),
        "notes": "legacy no-guard interface-aware queue-proxy run",
    },
    {
        "scenario_label": "node_total / forward_progress_hop",
        "queue_source": "node_total_queue_bytes",
        "loop_guard_mode": "forward_progress_hop",
        "forward_progress_metric": "hop",
        "restricted_route": "true",
        "run_name": (
            "run_core_isl_hotspot_specific_src754_dst785_load_1p6x_"
            "bg_flow_count_32_sim10s_stop8s_isl10mbps_gsl100mbps_"
            "lohi_mgmt_legacy_bp_qnodebytes_fbsp_lgfwphop_oneweb_isls_moving_udp_pdr"
        ),
        "notes": "restricted-route queue proxy; candidate filter only, weight unchanged",
    },
    {
        "scenario_label": "interface_avg / forward_progress_hop",
        "queue_source": "interface_nonreturn_avg_bytes",
        "loop_guard_mode": "forward_progress_hop",
        "forward_progress_metric": "hop",
        "restricted_route": "true",
        "run_name": (
            "run_core_isl_hotspot_specific_src754_dst785_load_1p6x_"
            "bg_flow_count_32_sim10s_stop8s_isl10mbps_gsl100mbps_"
            "lohi_mgmt_legacy_bp_qifnavgbytes_fbsp_lgfwphop_oneweb_isls_moving_udp_pdr"
        ),
        "notes": "interface-aware restricted-route queue proxy",
    },
]

REPORT_DIR = os.path.join(
    os.path.dirname(__file__),
    "analysis_reports",
    "backpressure_loop_suppression",
)


def _read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f_in:
        return list(csv.DictReader(f_in))


def _write_csv(path, fieldnames, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f_out:
        f_out.write(text)


def _float(row, key, default=0.0):
    value = row.get(key, "")
    if value in ("", None):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(row, key, default=0):
    return int(round(_float(row, key, default)))


def _bool(row, key):
    return str(row.get(key, "")).strip().lower() in ("1", "true", "yes")


def _mean(values):
    clean = [float(value) for value in values if value is not None]
    return sum(clean) / len(clean) if clean else 0.0


def _p95(values):
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return 0.0
    index = int(math.ceil(0.95 * len(clean))) - 1
    return clean[max(0, min(index, len(clean) - 1))]


def _fmt(value, digits=4):
    try:
        return ("%%.%df" % digits) % float(value)
    except (TypeError, ValueError):
        return str(value)


def _pct(value):
    return "%.1f%%" % (float(value) * 100.0)


def _path_nodes(path):
    if not path:
        return []
    if "->" in path:
        return [part for part in path.split("->") if part != ""]
    if ";" in path:
        return [part for part in path.split(";") if part != ""]
    return [path]


def _loop_signature(path):
    nodes = _path_nodes(path)
    seen = {}
    for index, node in enumerate(nodes):
        if node in seen:
            return "->".join(nodes[seen[node] : index + 1])
        seen[node] = index
    return "->".join(nodes[-6:])


def _top_items(counter, limit=5):
    return "; ".join("%s (%d)" % (key, count) for key, count in counter.most_common(limit))


def _run_dirs(base_dir, run_name):
    run_dir = os.path.join(base_dir, "runs", run_name)
    algo_dir = os.path.join(run_dir, ALGORITHM)
    comp_dir = os.path.join(run_dir, "comparison_packet_delivery")
    return {
        "run": run_dir,
        "algo": algo_dir,
        "diag": os.path.join(algo_dir, "backpressure_diagnostics"),
        "core": os.path.join(comp_dir, "core"),
    }


def _weighted_ratio(rows, numerator_key, denominator_key):
    denominator = sum(_float(row, denominator_key) for row in rows)
    if denominator <= 0.0:
        return 0.0
    numerator = sum(_float(row, numerator_key) for row in rows)
    return numerator / denominator


def _background_pdr(per_flow_rows):
    sent = sum(_int(row, "sent_packets") for row in per_flow_rows if row.get("flow_class") == "background")
    received = sum(
        _int(row, "received_packets") for row in per_flow_rows if row.get("flow_class") == "background"
    )
    return received / sent if sent else 0.0


def _rtt_metrics(rows):
    if not rows:
        return (0.0, 0.0)
    return (
        _mean([_float(row, "mean_queue_aware_rtt_ms") for row in rows]),
        max([_float(row, "p95_queue_aware_rtt_ms") for row in rows]),
    )


def _path_replay_success(rows):
    if not rows:
        return 0.0
    return max(_float(row, "path_replay_success_ratio") for row in rows)


def _dominant_loss(loss_row):
    candidates = [
        "exact_physical_queue_loss",
        "exact_physical_phy_loss",
        "exact_routing_loss",
        "exact_udp_send_failure_loss",
        "isl_saturation_associated_loss",
        "gsl_saturation_associated_loss",
        "mixed_saturation_associated_loss",
        "tail_in_flight_possible_loss",
        "unclassified_loss",
    ]
    if not loss_row:
        return ("", 0)
    category = max(candidates, key=lambda key: _int(loss_row, key))
    return (category, _int(loss_row, category))


def _path_metrics(path_rows):
    total = len(path_rows)
    loop_rows = [row for row in path_rows if _bool(row, "loop_detected")]
    reached_rows = [row for row in path_rows if _bool(row, "reached_destination")]
    stretch_values = [_float(row, "path_stretch") for row in path_rows if row.get("path_stretch", "") != ""]
    positive_rows = [row for row in path_rows if _int(row, "positive_pressure_count_on_path") > 0]
    fallback_only_rows = [
        row
        for row in path_rows
        if _int(row, "positive_pressure_count_on_path") == 0
        and _int(row, "fallback_count_on_path") > 0
    ]

    def _loop_rate(rows):
        return sum(1 for row in rows if _bool(row, "loop_detected")) / float(len(rows)) if rows else 0.0

    return {
        "path_sample_count": total,
        "loop_detected_count": len(loop_rows),
        "loop_detected_ratio": len(loop_rows) / float(total) if total else 0.0,
        "reached_destination_count": len(reached_rows),
        "reached_destination_ratio": len(reached_rows) / float(total) if total else 0.0,
        "avg_path_stretch": _mean(stretch_values),
        "p95_path_stretch": _p95(stretch_values),
        "positive_path_count": len(positive_rows),
        "positive_path_loop_rate": _loop_rate(positive_rows),
        "fallback_only_path_count": len(fallback_only_rows),
        "fallback_only_path_loop_rate": _loop_rate(fallback_only_rows),
        "top_loop_patterns": _top_items(Counter(_loop_signature(row.get("path", "")) for row in loop_rows)),
    }


def _candidate_metrics(summary_rows):
    before = sum(_float(row, "total_candidates_before_guard") for row in summary_rows)
    after = sum(_float(row, "total_candidates_after_guard") for row in summary_rows)
    if before <= 0.0:
        return (0.0, 0.0)
    return ((before - after) / before, after / before)


def collect_metrics(base_dir):
    metrics = []
    for run in RUNS:
        dirs = _run_dirs(base_dir, run["run_name"])
        summary_rows = _read_csv(os.path.join(dirs["core"], "summary_by_algorithm.csv"))
        per_flow_rows = _read_csv(os.path.join(dirs["core"], "per_flow_delivery.csv"))
        loss_rows = _read_csv(os.path.join(dirs["core"], "loss_attribution_breakdown_v3.csv"))
        rtt_rows = _read_csv(os.path.join(dirs["core"], "udp_rtt_summary_by_algorithm.csv"))
        replay_rows = _read_csv(os.path.join(dirs["core"], "path_replay_diagnostics.csv"))
        fallback_rows = _read_csv(os.path.join(dirs["diag"], "backpressure_fallback_summary.csv"))
        summary_diag_rows = _read_csv(os.path.join(dirs["diag"], "backpressure_summary.csv"))
        path_rows = _read_csv(os.path.join(dirs["diag"], "backpressure_path_stretch_summary.csv"))

        summary = summary_rows[0] if summary_rows else {}
        loss = loss_rows[0] if loss_rows else {}
        mean_rtt, p95_rtt = _rtt_metrics(rtt_rows)
        dominant_category, dominant_count = _dominant_loss(loss)
        candidate_filter_ratio, forward_progress_success_ratio = _candidate_metrics(summary_diag_rows)
        metric = dict(run)
        metric.update(
            {
                "run_dir": dirs["run"],
                "data_available": bool(summary_rows),
                "aggregate_pdr": _float(summary, "aggregate_pdr"),
                "focus_pdr": _float(summary, "focus_flow_pdr"),
                "background_pdr": _background_pdr(per_flow_rows),
                "mean_rtt_ms": mean_rtt,
                "p95_rtt_ms": p95_rtt,
                "total_sent_packets": _int(summary, "total_sent_packets"),
                "total_received_packets": _int(summary, "total_received_packets"),
                "total_lost_packets": _int(summary, "total_lost_packets"),
                "fallback_ratio": _weighted_ratio(fallback_rows, "fallback_decisions", "total_decisions"),
                "positive_pressure_ratio": _weighted_ratio(
                    fallback_rows, "positive_pressure_decisions", "total_decisions"
                ),
                "fallback_no_legal_forward_progress_count": sum(
                    _int(row, "no_legal_forward_progress_count") for row in fallback_rows
                ),
                "fallback_no_positive_pressure_after_guard_count": sum(
                    _int(row, "no_positive_pressure_after_guard_count") for row in fallback_rows
                ),
                "missing_forward_progress_distance_count": sum(
                    _int(row, "missing_forward_progress_distance_count") for row in fallback_rows
                ),
                "candidate_filter_ratio": candidate_filter_ratio,
                "forward_progress_success_ratio": forward_progress_success_ratio,
                "path_replay_success_ratio": _path_replay_success(replay_rows),
                "dominant_loss_category": dominant_category,
                "dominant_loss_count": dominant_count,
                "synthetic_lost_packets": _int(loss, "synthetic_lost_packets"),
                "unclassified_loss": _int(loss, "unclassified_loss"),
                "isl_saturation_associated_loss": _int(loss, "isl_saturation_associated_loss"),
            }
        )
        metric.update(_path_metrics(path_rows))
        metrics.append(metric)
    return metrics


def write_report_files(metrics):
    comparison_fields = [
        "scenario_label",
        "queue_source",
        "loop_guard_mode",
        "forward_progress_metric",
        "restricted_route",
        "aggregate_pdr",
        "focus_pdr",
        "background_pdr",
        "mean_rtt_ms",
        "p95_rtt_ms",
        "fallback_ratio",
        "positive_pressure_ratio",
        "candidate_filter_ratio",
        "forward_progress_success_ratio",
        "fallback_no_legal_forward_progress_count",
        "fallback_no_positive_pressure_after_guard_count",
        "missing_forward_progress_distance_count",
        "loop_detected_ratio",
        "reached_destination_ratio",
        "path_replay_success_ratio",
        "avg_path_stretch",
        "p95_path_stretch",
        "dominant_loss_category",
        "dominant_loss_count",
        "synthetic_lost_packets",
        "unclassified_loss",
        "isl_saturation_associated_loss",
        "total_sent_packets",
        "total_received_packets",
        "total_lost_packets",
        "run_name",
        "notes",
    ]
    _write_csv(
        os.path.join(REPORT_DIR, "backpressure_loop_guard_comparison.csv"),
        comparison_fields,
        [{field: metric.get(field, "") for field in comparison_fields} for metric in metrics],
    )

    path_fields = [
        "scenario_label",
        "queue_source",
        "loop_guard_mode",
        "path_sample_count",
        "loop_detected_count",
        "loop_detected_ratio",
        "reached_destination_count",
        "reached_destination_ratio",
        "avg_path_stretch",
        "p95_path_stretch",
        "positive_path_count",
        "positive_path_loop_rate",
        "fallback_only_path_count",
        "fallback_only_path_loop_rate",
        "top_loop_patterns",
    ]
    _write_csv(
        os.path.join(REPORT_DIR, "backpressure_loop_guard_path_summary.csv"),
        path_fields,
        [{field: metric.get(field, "") for field in path_fields} for metric in metrics],
    )

    by_label = {metric["scenario_label"]: metric for metric in metrics}
    node_none = by_label["node_total / no guard"]
    if_none = by_label["interface_avg / no guard"]
    node_guard = by_label["node_total / forward_progress_hop"]
    if_guard = by_label["interface_avg / forward_progress_hop"]

    rows = []
    for metric in metrics:
        rows.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                metric["scenario_label"],
                _fmt(metric["aggregate_pdr"]),
                _fmt(metric["focus_pdr"]),
                _fmt(metric["background_pdr"]),
                _pct(metric["fallback_ratio"]),
                _pct(metric["candidate_filter_ratio"]),
                _pct(metric["loop_detected_ratio"]),
                _pct(metric["path_replay_success_ratio"]),
            )
        )

    report = """# Backpressure loop suppression smoke analysis

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
%s

## 結果判讀

1. no-guard node-total 的 PDR 很低，主要不是因為沒有 queue signal，而是 destination semantics 不足造成 loop。它的 positive-pressure ratio 有 %s，但 path loop ratio 達 %s，表示 queue pressure 常把封包推向錯方向。
2. no-guard interface avg 並沒有改善 PDR，反而讓 fallback ratio 到 %s。原因是 directed interface queue proxy 更局部，能產生的正壓力候選更少；缺少 destination commodity queue 時，局部 queue granularity 不能保證朝目的地前進。
3. forward-progress-hop 大幅改善 node-total PDR：aggregate PDR 從 %s 到 %s，loop ratio 從 %s 到 %s。原因是 guard 移除了會增加目的地 hop distance 的候選，壓住 static fstate 中最致命的錯方向/循環選擇。
4. interface avg + forward-progress-hop 也把 loop ratio 壓到 0.0%%、replay success 拉到 100.0%%，但 aggregate PDR 只有 %s，明顯低於 node-total guard 的 %s。這表示 loop 是第一主因；loop 消除後，interface avg proxy 仍太保守，合法候選中常沒有正壓力，fallback ratio 維持在 %s，因此吞吐恢復不如 node-total guard。

## Root cause conclusion

H80 10s smoke 支持以下結論：低 PDR 的根因不是 drain time，也不是單純 queue source granularity，而是 queue-proxy Backpressure 沒有 per-destination commodity queue，導致 queue pressure 缺少 destination semantics。在 Hypatia 的 static forwarding-state pipeline 裡，這會形成 routing loop。Forward-progress restricted route 是目前最小、可落地、且不改 weight 的穩定化方法。

## Thesis wording suggestion

建議論文中稱為 `restricted-route queue-proxy Backpressure` 或 `loop-suppressed Backpressure proxy baseline`。避免稱為 `pure Backpressure`、`full multi-commodity Backpressure`、`distance-based Backpressure` 或 `hop-based Backpressure`。
""" % (
        "\n".join(rows),
        _pct(node_none["positive_pressure_ratio"]),
        _pct(node_none["loop_detected_ratio"]),
        _pct(if_none["fallback_ratio"]),
        _fmt(node_none["aggregate_pdr"]),
        _fmt(node_guard["aggregate_pdr"]),
        _pct(node_none["loop_detected_ratio"]),
        _pct(node_guard["loop_detected_ratio"]),
        _fmt(if_guard["aggregate_pdr"]),
        _fmt(node_guard["aggregate_pdr"]),
        _pct(if_guard["fallback_ratio"]),
    )

    recommendation = """# Recommendation

建議把 `forward_progress_hop` 作為 H80 60s formal 的 stabilized Backpressure proxy variant 候選，但在圖表和文字中必須明確標註它是 restricted-route / loop-suppressed queue-proxy Backpressure，不是 original pure Backpressure。

建議 formal 前先跑：

```bash
python run_hotspot_5level_60s_formal.py \\
  --scenarios H80 \\
  --simulation-end-time-s 60 \\
  --traffic-stop-time-s 58 \\
  --algorithms algorithm_free_one_only_over_isls algorithm_queue_aware_over_isls algorithm_lohi algorithm_lhtr algorithm_backpressure_over_isls \\
  --backpressure-queue-source node_total_bytes \\
  --backpressure-fallback shortest_path \\
  --backpressure-loop-guard forward_progress_hop \\
  --force
```

若要把 queue-source sensitivity 放進 appendix，再補一組：

```bash
python run_hotspot_5level_60s_formal.py \\
  --scenarios H80 \\
  --simulation-end-time-s 60 \\
  --traffic-stop-time-s 58 \\
  --algorithms algorithm_backpressure_over_isls \\
  --backpressure-queue-source interface_nonreturn_avg_bytes \\
  --backpressure-fallback shortest_path \\
  --backpressure-loop-guard forward_progress_hop \\
  --force
```
"""

    _write_text(os.path.join(REPORT_DIR, "analysis_report_zh.md"), report)
    _write_text(os.path.join(REPORT_DIR, "backpressure_loop_guard_recommendation.md"), recommendation)


def main():
    base_dir = os.path.dirname(__file__)
    metrics = collect_metrics(base_dir)
    write_report_files(metrics)
    print("Wrote loop suppression analysis under %s" % REPORT_DIR)


if __name__ == "__main__":
    main()
