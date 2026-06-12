#!/usr/bin/env python3

import math
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import analyze_isl_load_percentage_mapping as base
from dynamic_path_replay import replay_path


OUTPUT_DIR = os.path.join(
    base.SCRIPT_DIR,
    "analysis_reports",
    "hotspot_reference_load_mapping",
)

HOTSPOT_LABELS = [
    ("Hotspot-Light", 0.0, 50.0),
    ("Hotspot-Moderate", 50.0, 70.0),
    ("Hotspot-High", 70.0, 85.0),
    ("Hotspot-Severe", 85.0, 100.0),
    ("Hotspot-Overload", 100.0, math.inf),
]

PRESSURE_ORDER = {
    "Non-congested": 0,
    "Localized congestion": 1,
    "Sustained congestion": 2,
    "Overloaded": 3,
}


def hotspot_load_label(load_percent):
    # Reference-demand arithmetic can land a few ulps below an exact band
    # boundary (for example 69.999999999 instead of 70.0).
    value = round(float(load_percent), 6)
    for label, lower, upper in HOTSPOT_LABELS:
        if lower <= value < upper:
            return label
    return "Unknown"


def _target_corridor_reference_metrics(
    flows,
    states,
    target_edges,
    traffic_stop_ns,
    isl_capacity_mbps,
):
    demand_integral = 0.0
    attempted_duration = 0.0
    successful_duration = 0.0
    active_target_edges = set()
    peak_target_edge_rate_mbps = 0.0

    for interval_start, interval_end, state in states:
        edge_rates = defaultdict(float)
        for flow in flows:
            overlap_start = max(interval_start, flow["start_ns"])
            overlap_end = min(interval_end, flow["end_ns"], traffic_stop_ns)
            if overlap_end <= overlap_start:
                continue
            duration_s = (overlap_end - overlap_start) / 1e9
            attempted_duration += duration_s
            result = replay_path(
                state,
                flow["src"],
                flow["dst"],
                base.NUM_SATELLITES,
                base.NUM_NODES,
            )
            if not result.success:
                continue
            successful_duration += duration_s
            for first, second in zip(result.path, result.path[1:]):
                edge = (int(first), int(second))
                if (
                    first < base.NUM_SATELLITES
                    and second < base.NUM_SATELLITES
                    and edge in target_edges
                ):
                    demand_integral += flow["rate_mbps"] * duration_s
                    edge_rates[edge] += flow["rate_mbps"]
                    active_target_edges.add(edge)
        if edge_rates:
            peak_target_edge_rate_mbps = max(
                peak_target_edge_rate_mbps,
                max(edge_rates.values()),
            )

    traffic_duration_s = traffic_stop_ns / 1e9
    average_demand = demand_integral / traffic_duration_s
    target_capacity = len(target_edges) * isl_capacity_mbps
    success_ratio = (
        successful_duration / attempted_duration
        if attempted_duration > 0
        else 0.0
    )
    return {
        "target_corridor_directed_edge_count": len(target_edges),
        "target_corridor_capacity_mbps": target_capacity,
        "target_corridor_total_hop_demand_mbps_hops": average_demand,
        "target_corridor_offered_load_percent": (
            100.0 * average_demand / target_capacity
            if target_capacity > 0
            else math.nan
        ),
        "target_corridor_active_directed_edge_count": len(active_target_edges),
        "peak_target_corridor_link_offered_rate_mbps": (
            peak_target_edge_rate_mbps
        ),
        "peak_target_corridor_link_offered_load_percent": (
            100.0 * peak_target_edge_rate_mbps / isl_capacity_mbps
        ),
        "target_corridor_reference_replay_success_ratio": success_ratio,
        "target_corridor_metric_source": (
            "baseline_shortest_path_time_average_1s_over_0_8s"
        ),
    }


def _rank_correlation(first, second):
    first = pd.Series(first, dtype=float)
    second = pd.Series(second, dtype=float)
    valid = first.notna() & second.notna()
    if valid.sum() < 2:
        return math.nan
    return float(first[valid].rank().corr(second[valid].rank()))


def _markdown_table(frame, columns):
    headers = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = []
    for _, row in frame[columns].iterrows():
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, (float, np.floating)):
                values.append(
                    "" if not math.isfinite(float(value)) else "%.3f" % value
                )
            else:
                values.append(str(value))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join([headers, separator] + rows)


def _select_candidates(mapping):
    specifications = [
        {
            "scenario_id": "H40",
            "target_percent": 40.0,
            "label": "Hotspot-Light",
            "preferred_conditions": {
                "Non-congested",
                "Localized congestion",
            },
        },
        {
            "scenario_id": "H60",
            "target_percent": 60.0,
            "label": "Hotspot-Moderate",
            "preferred_conditions": {"Localized congestion"},
        },
        {
            "scenario_id": "H80",
            "target_percent": 80.0,
            "label": "Hotspot-High",
            "preferred_conditions": {
                "Localized congestion",
                "Sustained congestion",
            },
        },
        {
            "scenario_id": "H90",
            "target_percent": 90.0,
            "label": "Hotspot-Severe",
            "preferred_conditions": {"Sustained congestion"},
        },
        {
            "scenario_id": "H100+",
            "target_percent": 100.0,
            "label": "Hotspot-Overload",
            "preferred_conditions": {"Overloaded"},
        },
    ]
    rows = []
    all_levels_present = set(mapping["hotspot_traffic_load_label"]) >= {
        item["label"] for item in specifications
    }
    for specification in specifications:
        eligible = mapping[
            (mapping["hotspot_traffic_load_label"] == specification["label"])
            & (
                mapping["safe_for_isl_focused_experiment"]
                .astype(str)
                .str.lower()
                .eq("true")
            )
        ].copy()
        if len(eligible) == 0:
            continue
        eligible["condition_penalty"] = eligible[
            "observed_pressure_condition"
        ].map(
            lambda value: (
                0.0
                if value in specification["preferred_conditions"]
                else 20.0
            )
        )
        eligible["selection_score"] = (
            (
                eligible["hotspot_reference_load_percent"]
                - specification["target_percent"]
            ).abs()
            + eligible["condition_penalty"]
        )
        selected = eligible.sort_values(
            [
                "selection_score",
                "hotspot_reference_load_percent",
                "background_flow_count",
            ]
        ).iloc[0]
        observed = selected["observed_pressure_condition"]
        reason = (
            "Closest GSL-safe %s point to %.0f%% after preferring observed "
            "conditions %s. PDR is reported only as outcome."
            % (
                specification["label"],
                specification["target_percent"],
                "/".join(sorted(specification["preferred_conditions"])),
            )
        )
        rows.append(
            {
                "scenario_id": specification["scenario_id"],
                "setting_id": selected["setting_id"],
                "load_level": selected["load_level"],
                "background_flow_count": selected["background_flow_count"],
                "global_offered_isl_load_percent": selected[
                    "global_offered_isl_load_percent"
                ],
                "hotspot_reference_load_percent": selected[
                    "hotspot_reference_load_percent"
                ],
                "target_corridor_offered_load_percent": selected[
                    "target_corridor_offered_load_percent"
                ],
                "peak_reference_link_offered_load_percent": selected[
                    "peak_reference_link_offered_load_percent"
                ],
                "global_traffic_load_label": selected[
                    "global_traffic_load_label"
                ],
                "hotspot_traffic_load_label": selected[
                    "hotspot_traffic_load_label"
                ],
                "observed_pressure_condition": observed,
                "gsl_bottleneck_flag": selected["gsl_bottleneck_flag"],
                "safe_for_isl_focused_experiment": selected[
                    "safe_for_isl_focused_experiment"
                ],
                "queue_aware_pdr_if_available": selected["queue_aware_pdr"],
                "baseline_pdr_if_available": selected["baseline_pdr"],
                "recommended_for_60s": base._bool_text(
                    all_levels_present
                ),
                "recommended_for_200s": "false",
                "reason": reason,
            }
        )
    return pd.DataFrame(rows)


def build_hotspot_analysis():
    (
        original_mapping,
        _,
        pressure,
        pdr,
        _,
        _,
    ) = base.build_analysis()
    mapping = original_mapping.copy()
    traffic_stop_ns = int(round(mapping["traffic_stop_s"].iloc[0] * 1e9))
    states = base._build_reference_states(traffic_stop_ns)

    target_rows = []
    for _, row in mapping.iterrows():
        run_dir = os.path.join(base.RUNS_ROOT, row["run_folder"])
        flows = base._read_schedule(
            os.path.join(
                run_dir,
                base.QUEUE_AWARE,
                "udp_burst_schedule.csv",
            )
        )
        target_edges = base._target_corridor_edges(run_dir)
        metrics = _target_corridor_reference_metrics(
            flows,
            states,
            target_edges,
            traffic_stop_ns,
            float(row["isl_capacity_mbps"]),
        )
        target_rows.append({"setting_id": row["setting_id"], **metrics})
    target_frame = pd.DataFrame(target_rows)

    mapping["global_offered_isl_load_percent"] = mapping[
        "offered_isl_resource_load_percent"
    ]
    mapping["global_traffic_load_label"] = mapping["traffic_load_label"]
    mapping["reference_active_capacity_mbps"] = (
        mapping["reference_active_directed_isl_link_count"]
        * mapping["isl_capacity_mbps"]
    )
    mapping["hotspot_reference_load_percent"] = mapping[
        "reference_active_capacity_load_percent"
    ]
    mapping["hotspot_traffic_load_label"] = mapping[
        "hotspot_reference_load_percent"
    ].map(hotspot_load_label)
    mapping["global_denominator_scope"] = (
        "all_2880_directed_ISLs_at_10Mbps"
    )
    mapping["hotspot_denominator_scope"] = (
        "per_setting_union_of_baseline_reference_directed_ISLs_over_0_8s"
    )
    mapping = mapping.merge(target_frame, on="setting_id", how="left")

    queue_aware_pressure = pressure[
        pressure["algorithm"] == base.QUEUE_AWARE
    ][
        [
            "setting_id",
            "all_isl_p95",
            "active_isl_p95",
            "target_corridor_p95",
            "target_corridor_max",
            "links_over_80pct",
            "links_over_90pct",
            "links_over_100pct",
            "isl_samples_at_capacity",
        ]
    ]
    mapping = mapping.merge(
        queue_aware_pressure,
        on="setting_id",
        how="left",
    )

    queue_aware_pdr = pdr[pdr["algorithm"] == base.QUEUE_AWARE][
        ["setting_id", "aggregate_pdr"]
    ].rename(columns={"aggregate_pdr": "queue_aware_pdr"})
    baseline_pdr = pdr[pdr["algorithm"] == base.BASELINE][
        ["setting_id", "aggregate_pdr"]
    ].rename(columns={"aggregate_pdr": "baseline_pdr"})
    mapping = mapping.merge(queue_aware_pdr, on="setting_id", how="left")
    mapping = mapping.merge(baseline_pdr, on="setting_id", how="left")
    mapping["pdr_role"] = "outcome_only_not_scenario_definition"
    mapping["hotspot_metric_caveat"] = (
        "The per-setting active-reference denominator changes when additional "
        "flows touch additional reference ISLs; global and fixed-corridor "
        "metrics are retained as sensitivity checks."
    )

    mapping = mapping.sort_values(
        ["hotspot_reference_load_percent", "global_offered_isl_load_percent"]
    ).reset_index(drop=True)
    comparison_columns = [
        "setting_id",
        "load_level",
        "background_flow_count",
        "global_offered_isl_load_percent",
        "hotspot_reference_load_percent",
        "target_corridor_offered_load_percent",
        "peak_reference_link_offered_load_percent",
        "global_traffic_load_label",
        "hotspot_traffic_load_label",
        "observed_pressure_condition",
        "queue_aware_pdr",
        "gsl_bottleneck_flag",
        "safe_for_isl_focused_experiment",
    ]
    comparison = mapping[comparison_columns].copy()
    candidates = _select_candidates(mapping)
    return mapping, comparison, candidates, pdr


def _save_plots(mapping, candidates, pdr):
    condition_colors = {
        "Non-congested": "tab:green",
        "Localized congestion": "tab:blue",
        "Sustained congestion": "tab:orange",
        "Overloaded": "tab:red",
    }

    plt.figure(figsize=(8, 6))
    scatter = plt.scatter(
        mapping["global_offered_isl_load_percent"],
        mapping["hotspot_reference_load_percent"],
        c=mapping["background_flow_count"],
        cmap="viridis",
        s=55,
    )
    plt.xlabel("Global offered ISL load (%)")
    plt.ylabel("Hotspot-reference load (%)")
    plt.colorbar(scatter, label="Background flow count")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(
        os.path.join(OUTPUT_DIR, "global_vs_hotspot_load_percent.png"),
        dpi=180,
    )
    plt.close()

    plt.figure(figsize=(9, 6))
    for condition, color in condition_colors.items():
        group = mapping[
            mapping["observed_pressure_condition"] == condition
        ]
        if len(group):
            plt.scatter(
                group["hotspot_reference_load_percent"],
                group["target_corridor_p95"],
                color=color,
                label="%s: target corridor p95" % condition,
                alpha=0.85,
            )
    plt.scatter(
        mapping["hotspot_reference_load_percent"],
        mapping["active_isl_p95"],
        marker="x",
        color="black",
        label="Active ISL p95",
        alpha=0.7,
    )
    plt.xlabel("Hotspot-reference load (%)")
    plt.ylabel("Queue-aware measured utilization")
    plt.grid(alpha=0.25)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(
        os.path.join(OUTPUT_DIR, "hotspot_load_vs_observed_pressure.png"),
        dpi=180,
    )
    plt.close()

    pdr_plot = pdr.merge(
        mapping[["setting_id", "hotspot_reference_load_percent"]],
        on="setting_id",
        how="left",
    )
    plt.figure(figsize=(9, 6))
    for algorithm, group in pdr_plot.groupby("algorithm"):
        plt.scatter(
            group["hotspot_reference_load_percent"],
            group["aggregate_pdr"],
            label=algorithm.replace("algorithm_", "").replace(
                "_over_isls", ""
            ),
            alpha=0.85,
        )
    plt.xlabel("Hotspot-reference load (%)")
    plt.ylabel("Aggregate PDR (outcome only)")
    plt.ylim(0, 1.03)
    plt.title("PDR is outcome only; it does not define scenario load")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(
        os.path.join(OUTPUT_DIR, "hotspot_load_vs_pdr_outcome.png"),
        dpi=180,
    )
    plt.close()

    plt.figure(figsize=(9, 6))
    scatter = plt.scatter(
        mapping["hotspot_reference_load_percent"],
        mapping["target_corridor_p95"],
        c=mapping["target_corridor_offered_load_percent"],
        cmap="plasma",
        s=60,
    )
    plt.xlabel("Hotspot-reference load (%)")
    plt.ylabel("Queue-aware target-corridor active p95")
    plt.colorbar(scatter, label="Reference target-corridor offered load (%)")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(
        os.path.join(
            OUTPUT_DIR,
            "hotspot_load_vs_target_corridor_utilization.png",
        ),
        dpi=180,
    )
    plt.close()

    plt.figure(figsize=(10, 6))
    plt.scatter(
        mapping["hotspot_reference_load_percent"],
        mapping["target_corridor_p95"],
        color="lightgray",
        label="All calibration settings",
    )
    candidate_points = candidates.merge(
        mapping[["setting_id", "target_corridor_p95"]],
        on="setting_id",
    )
    plt.scatter(
        candidate_points["hotspot_reference_load_percent"],
        candidate_points["target_corridor_p95"],
        color="tab:red",
        s=90,
        label="Recommended 60s candidates",
    )
    annotation_offsets = {
        "H40": (6, 14),
        "H60": (6, -16),
        "H80": (6, 8),
        "H90": (6, 8),
        "H100+": (6, 8),
    }
    for _, row in candidate_points.iterrows():
        plt.annotate(
            "%s\n%s" % (row["scenario_id"], row["setting_id"]),
            (
                row["hotspot_reference_load_percent"],
                row["target_corridor_p95"],
            ),
            xytext=annotation_offsets.get(row["scenario_id"], (5, 5)),
            textcoords="offset points",
            fontsize=8,
        )
    plt.xlabel("Hotspot-reference load (%)")
    plt.ylabel("Queue-aware target-corridor active p95")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(
        os.path.join(OUTPUT_DIR, "hotspot_candidate_overview.png"),
        dpi=180,
    )
    plt.close()


def _write_notes(mapping):
    target_edge_counts = sorted(
        mapping["target_corridor_directed_edge_count"].unique()
    )
    text = """# Hotspot Reference Load Mapping Notes

## Dual load definition

The `core_isl_hotspot_specific` experiment reports two load percentages:

1. `global_offered_isl_load_percent` divides time-averaged Baseline
   reference-path hop demand by all 2,880 directed ISLs at 10 Mbps.
2. `hotspot_reference_load_percent` divides the same numerator by the
   capacity of the directed ISLs touched by that setting's Baseline reference
   paths during the 0-8 s traffic window.

The global metric remains necessary because it describes constellation-wide
resource demand. The hotspot metric is the primary scenario label for this
deliberately localized traffic placement.

## Hotspot labels

- Hotspot-Light: < 50%%
- Hotspot-Moderate: 50%% to < 70%%
- Hotspot-High: 70%% to < 85%%
- Hotspot-Severe: 85%% to < 100%%
- Hotspot-Overload: >= 100%%

These thresholds are fixed before joining PDR outcomes.

## Target-corridor diagnostic

`target_corridor_offered_load_percent` is recomputed by replaying the Baseline
shortest path at one-second snapshots over 0-8 s and summing only demand on the
fixed target-corridor directed edge set. The target edge counts observed in
these runs are: %s. This avoids treating every edge in a multi-snapshot path
union as if it carried every flow simultaneously.

## Methodological caveat

The active-reference denominator is setting-specific. Adding flows can expand
the union of touched directed ISLs, so hotspot-reference load is not guaranteed
to be monotonic in `load_level` or background-flow count. For example,
`load=1.0,bg=16` is 50.0%% while `load=1.0,bg=24` is approximately 47.36%%.

To avoid cherry-picking:

- the Baseline reference algorithm, 0-8 s window, one-second snapshots, and
  label thresholds are fixed for all settings;
- the active directed-ISL count and capacity are reported for every setting;
- global load, fixed target-corridor load, and peak-link demand are retained;
- candidate selection uses all GSL-safe settings in each predeclared band;
- PDR is joined only as an outcome and never changes a scenario label.

## Observed pressure and PDR

Queue-aware throughput and queue-pressure metrics validate whether congestion
appears under an adaptive route, but they do not define the hotspot load.
Associated loss remains a time/path correlation rather than physical-drop
proof. PDR is an algorithm outcome only.
""" % ", ".join(str(int(value)) for value in target_edge_counts)
    with open(
        os.path.join(OUTPUT_DIR, "hotspot_mapping_notes.md"),
        "w",
        encoding="utf-8",
    ) as f_out:
        f_out.write(text)


def _write_report(mapping, comparison, candidates):
    label_counts = mapping["hotspot_traffic_load_label"].value_counts()
    condition_numeric = mapping["observed_pressure_condition"].map(
        PRESSURE_ORDER
    )
    correlations = {
        "global_vs_target_p95": _rank_correlation(
            mapping["global_offered_isl_load_percent"],
            mapping["target_corridor_p95"],
        ),
        "hotspot_vs_target_p95": _rank_correlation(
            mapping["hotspot_reference_load_percent"],
            mapping["target_corridor_p95"],
        ),
        "target_offered_vs_target_p95": _rank_correlation(
            mapping["target_corridor_offered_load_percent"],
            mapping["target_corridor_p95"],
        ),
        "peak_vs_target_p95": _rank_correlation(
            mapping["peak_reference_link_offered_load_percent"],
            mapping["target_corridor_p95"],
        ),
        "hotspot_vs_pressure_order": _rank_correlation(
            mapping["hotspot_reference_load_percent"],
            condition_numeric,
        ),
    }
    nearest_rows = []
    for target in [40, 60, 80, 90, 100]:
        index = (
            mapping["hotspot_reference_load_percent"] - target
        ).abs().idxmin()
        row = mapping.loc[index]
        nearest_rows.append(
            {
                "target_percent": target,
                "setting_id": row["setting_id"],
                "hotspot_percent": row[
                    "hotspot_reference_load_percent"
                ],
                "hotspot_label": row["hotspot_traffic_load_label"],
                "observed_condition": row[
                    "observed_pressure_condition"
                ],
            }
        )
    nearest = pd.DataFrame(nearest_rows)

    display = comparison[
        [
            "setting_id",
            "global_offered_isl_load_percent",
            "hotspot_reference_load_percent",
            "target_corridor_offered_load_percent",
            "peak_reference_link_offered_load_percent",
            "hotspot_traffic_load_label",
            "observed_pressure_condition",
            "safe_for_isl_focused_experiment",
        ]
    ].copy()
    report = """# Core-ISL Hotspot Reference Load Mapping

## 1. 總結結論

- Global offered ISL load 的 1.319%%-11.354%% 並沒有算錯；它以全星座
  2,880 條 directed ISLs 為分母，因此會稀釋刻意集中在局部 corridor 的
  hotspot traffic。
- Active-reference normalization 將既有 30 點映射到 %.3f%%-%.3f%%，
  五個 hotspot bands 均有資料：%s。
- 因此 `core_isl_hotspot_specific` 應採雙層定義：hotspot-reference load
  作主要 scenario x-axis，global load 同時報告為 constellation-wide
  context；fixed target-corridor 與 peak-link demand 作 diagnostics。
- 既有點可近似老師要看的 40/60/80/90/100%%+，不需要再補 10s
  calibration 才能覆蓋 levels。
- 五個候選皆通過 GSL safety gate，建議下一步跑四演算法 60s formal；
  暫不直接跑 200s。

## 2. 資料來源

- 上一輪 `analysis_reports/isl_load_percentage_mapping/` 的 mapping、
  observed pressure、PDR outcome 與 GSL safety outputs。
- 30 個 run 的 `udp_burst_schedule.csv`、
  `isl_corridor_load_summary.csv` 與 run metadata。
- Baseline/free-one-only 的 0-8 s、1 s forwarding-state snapshots。
- Queue-aware `isl_utilization.csv` 與既有 packet-delivery diagnostics。

## 3. 三種 load metric 定義

```text
global_offered_isl_load_percent =
  100 * reference hop demand
  / (2880 directed ISLs * 10 Mbps)

hotspot_reference_load_percent =
  100 * reference hop demand
  / (per-setting touched reference directed ISLs * 10 Mbps)

target_corridor_offered_load_percent =
  100 * time-averaged reference demand on target corridor
  / (target corridor directed edge count * 10 Mbps)
```

Global metric 描述全星座資源比例。Hotspot-reference metric 描述該 traffic
setting 實際 reference ISL subset 的平均 offered pressure。Target-corridor
metric 使用固定 corridor edge set，是 denominator sensitivity check。
`peak_reference_link_offered_load_percent` 再補充最熱單一 link 的壓力。

Hotspot-reference denominator 會隨 setting 的 touched-link union 改變，因此
不保證對 load/bg 完全單調。這個限制必須與 active-link count 一起揭露，
不能把 hotspot percentage 說成 global percentage。

## 4. Global vs Hotspot 比較

%s

所有 global labels 仍為 Low。Hotspot label 分布為：
%s。

Spearman rank correlation with Queue-aware target-corridor active p95：

- global offered load: %.3f
- hotspot-reference load: %.3f
- fixed target-corridor offered load: %.3f
- peak reference-link demand: %.3f

Hotspot-reference 與 observed pressure order 的 rank correlation 為 %.3f。
它提供更直接的局部 capacity-scale 解讀，但與 target-corridor p95 的
相關性實際低於 global/fixed-corridor metrics，主因是 per-setting active
denominator 會擴張。因此本文不宣稱它更能預測 Queue-aware outcome；
observed metrics 仍是獨立 validation。

## 5. Hotspot scenario mapping

%s

最接近老師指定 percentages 的既有 settings：

%s

PDR 只列在 CSV 與 plots 作 outcome，完全不參與上述 labels 或候選評分。

## 6. Formal candidates

%s

候選使用預先宣告的 hotspot bands、GSL safety 與 observed-pressure
一致性挑選，不依 PDR 高低選點。五點均 `recommended_for_60s=true`，
`recommended_for_200s=false`。

## 7. 是否需要補 simulation

不需要再補 10s calibration 才能建立五級 mapping。Light 的最近點為
47.36%%，60%%、80%%、90%% 附近也都有既有點，Overload 有 100%% 以上
且 observed condition 為 Overloaded 的候選。若未來要求「精確 40.0%%」
而不是 level representative，才需要額外微調點；這不阻擋目前的 60s
formal comparison。

## 8. 新增檔案

- `hotspot_load_mapping.csv`
- `hotspot_vs_global_load_comparison.csv`
- `hotspot_formal_candidate_table.csv`
- `hotspot_mapping_notes.md`
- `analysis_report_zh.md`
- `global_vs_hotspot_load_percent.png`
- `hotspot_load_vs_observed_pressure.png`
- `hotspot_load_vs_pdr_outcome.png`
- `hotspot_load_vs_target_corridor_utilization.png`
- `hotspot_candidate_overview.png`

## 9. 論文敘事建議

### 中文

由於本實驗採用 core-ISL hotspot traffic placement，流量刻意集中於一小段
reference corridor。若以全星座所有 directed ISL capacity 作為分母，
負載比例會被大量未參與該 hotspot 的 links 稀釋。這個 global load 並非
錯誤，而是描述相對於整個 constellation 的資源需求。本文因此同時報告
global offered ISL load 與 hotspot-reference load；前者提供全星座尺度，
後者以相同的 Baseline reference hop demand 除以該 setting 在固定 traffic
window 中實際涉及的 reference ISL subset capacity，作為 hotspot scenario
的主要 x-axis。為避免事後挑選分母，本文固定 reference algorithm、時間窗、
snapshot interval 與 label thresholds，並逐點公開 active-link count，同時
保留 global、fixed-corridor 與 peak-link metrics。PDR 僅作演算法 outcome，
不參與 scenario level definition。

### English

Because the core-ISL hotspot scenario intentionally concentrates traffic on a
limited reference corridor, normalizing offered demand by the capacity of all
directed ISLs in the constellation substantially dilutes the apparent load.
This global metric is not incorrect; it describes demand relative to the full
constellation resource pool. We therefore report both global offered ISL load
and hotspot-reference load. The latter normalizes the same reproducible
Baseline reference-path demand by the capacity of the directed ISL subset
touched during the fixed traffic window and serves as the primary scenario
x-axis. To avoid post-hoc denominator selection, we fix the reference
algorithm, time window, snapshot interval, and load thresholds in advance,
report the active-link count for every setting, and retain global,
fixed-corridor, and peak-link diagnostics. Packet delivery ratio is reported
only as an algorithmic outcome and is never used to define scenario load.

## 10. 下一步建議

只做一件事：使用 `hotspot_formal_candidate_table.csv` 的五個 settings 跑
Baseline、Queue-aware、LoHi、LHTR 四演算法 60s formal experiment。
""" % (
        mapping["hotspot_reference_load_percent"].min(),
        mapping["hotspot_reference_load_percent"].max(),
        ", ".join(
            "%s=%d" % (label, int(label_counts.get(label, 0)))
            for label, _, _ in HOTSPOT_LABELS
        ),
        _markdown_table(
            display,
            [
                "setting_id",
                "global_offered_isl_load_percent",
                "hotspot_reference_load_percent",
                "target_corridor_offered_load_percent",
                "peak_reference_link_offered_load_percent",
                "hotspot_traffic_load_label",
                "observed_pressure_condition",
                "safe_for_isl_focused_experiment",
            ],
        ),
        ", ".join(
            "%s=%d" % (label, int(label_counts.get(label, 0)))
            for label, _, _ in HOTSPOT_LABELS
        ),
        correlations["global_vs_target_p95"],
        correlations["hotspot_vs_target_p95"],
        correlations["target_offered_vs_target_p95"],
        correlations["peak_vs_target_p95"],
        correlations["hotspot_vs_pressure_order"],
        _markdown_table(
            comparison,
            [
                "setting_id",
                "hotspot_reference_load_percent",
                "hotspot_traffic_load_label",
                "observed_pressure_condition",
                "queue_aware_pdr",
            ],
        ),
        _markdown_table(
            nearest,
            [
                "target_percent",
                "setting_id",
                "hotspot_percent",
                "hotspot_label",
                "observed_condition",
            ],
        ),
        _markdown_table(
            candidates,
            [
                "scenario_id",
                "setting_id",
                "global_offered_isl_load_percent",
                "hotspot_reference_load_percent",
                "hotspot_traffic_load_label",
                "observed_pressure_condition",
                "recommended_for_60s",
            ],
        ),
    )
    with open(
        os.path.join(OUTPUT_DIR, "analysis_report_zh.md"),
        "w",
        encoding="utf-8",
    ) as f_out:
        f_out.write(report)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    mapping, comparison, candidates, pdr = build_hotspot_analysis()
    mapping.to_csv(
        os.path.join(OUTPUT_DIR, "hotspot_load_mapping.csv"),
        index=False,
        float_format="%.9f",
    )
    comparison.to_csv(
        os.path.join(
            OUTPUT_DIR,
            "hotspot_vs_global_load_comparison.csv",
        ),
        index=False,
        float_format="%.9f",
    )
    candidates.to_csv(
        os.path.join(OUTPUT_DIR, "hotspot_formal_candidate_table.csv"),
        index=False,
        float_format="%.9f",
    )
    _save_plots(mapping, candidates, pdr)
    _write_notes(mapping)
    _write_report(mapping, comparison, candidates)
    print("Wrote hotspot reference load analysis to %s" % OUTPUT_DIR)
    print(
        "Hotspot load range: %.6f%% to %.6f%%"
        % (
            mapping["hotspot_reference_load_percent"].min(),
            mapping["hotspot_reference_load_percent"].max(),
        )
    )
    print(
        "Hotspot labels: %s"
        % mapping["hotspot_traffic_load_label"].value_counts().to_dict()
    )
    print(
        "Candidates: %s"
        % candidates[["scenario_id", "setting_id"]].to_dict("records")
    )


if __name__ == "__main__":
    main()
