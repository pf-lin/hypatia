import csv
import os
import re
import shutil


CORE_FILES = {
    "summary_by_algorithm.csv": (
        "Algorithm-level packet delivery summary.",
        "udp_bursts_outgoing.csv; udp_bursts_incoming.csv",
        True,
    ),
    "per_flow_delivery.csv": (
        "Per-flow sent, received, loss, PDR, and rate results.",
        "udp_bursts_outgoing.csv; udp_bursts_incoming.csv",
        True,
    ),
    "loss_attribution_breakdown_v3.csv": (
        "Canonical v3 exact and associated loss attribution summary.",
        "loss_attribution_detailed_v3.csv",
        True,
    ),
    "loss_attribution_detailed_v3.csv": (
        "Canonical per-flow v3 loss attribution with reconciliation fields.",
        "UDP counters; exact traces; dynamic path replay; queue histories",
        True,
    ),
    "congested_interfaces_summary.csv": (
        "Interfaces that reached configured queue capacity.",
        "isl_queue_pkt_history.csv; gsl_queue_pkt_history.csv",
        True,
    ),
    "path_replay_diagnostics.csv": (
        "Dynamic forwarding-state replay success and failure counts.",
        "fstate_*; dynamic_state_*",
        True,
    ),
    "physical_drop_summary.csv": (
        "Summary of exact traced link/device drop events.",
        "physical_link_drops.csv; routing_drops.csv; udp_send_failures.csv",
        True,
    ),
    "loss_diagnostics.txt": (
        "Human-readable entry point for definitions, caveats, and run results.",
        "All packet delivery and attribution outputs",
        True,
    ),
    "aggregate_pdr.png": (
        "Aggregate packet delivery ratio by algorithm.",
        "summary_by_algorithm.csv",
        True,
    ),
    "focus_flow_pdr.png": (
        "Focus-flow packet delivery ratio by algorithm.",
        "summary_by_algorithm.csv",
        True,
    ),
    "per_flow_pdr_cdf.png": (
        "CDF of per-flow packet delivery ratio.",
        "per_flow_delivery.csv",
        True,
    ),
    "loss_attribution_breakdown_v3.png": (
        "Canonical v3 exact and associated loss attribution figure.",
        "loss_attribution_breakdown_v3.csv",
        True,
    ),
    "top_congested_interfaces.png": (
        "Interfaces with the most samples at queue capacity.",
        "congested_interfaces_summary.csv",
        True,
    ),
    "queue_saturation_by_link_type.png": (
        "At-capacity queue samples grouped by ISL/GSL link type.",
        "congested_interfaces_summary.csv",
        True,
    ),
    "queue_saturation_timeline.png": (
        "At-capacity events for the most congested interfaces.",
        "queue_saturation_timeline_at_capacity.csv",
        True,
    ),
    "top_loss_flows.png": (
        "Flows with the largest synthetic sent-minus-received loss.",
        "top_loss_flows.csv",
        True,
    ),
    "destination_loss_summary.png": (
        "Destination aggregates with the largest synthetic loss.",
        "destination_loss_summary.csv",
        True,
    ),
    "destination_offered_rate_vs_gsl_capacity.png": (
        "Destination offered rate compared with configured GSL capacity.",
        "destination_loss_summary.csv",
        True,
    ),
}


DIAGNOSTIC_FILES = {
    "focus_flow_delivery.csv": "Focus-flow rows used by the core PDR figure.",
    "pairwise_algorithm_comparison.csv": "Pairwise algorithm differences.",
    "affected_flows.csv": "All flows with synthetic sent-minus-received loss.",
    "top_loss_flows.csv": "Largest synthetic loss contributors.",
    "destination_loss_summary.csv": "Destination-level delivery and capacity aggregates.",
    "flow_path_timeline.csv": "Per-flow dynamic path replay timeline.",
    "queue_saturation_timeline_at_capacity.csv": "Queue timeline filtered to is_at_capacity=true.",
    "queue_saturation_timeline.csv": "Optional full queue timeline; disabled by default.",
    "tag_coverage_diagnostics.csv": "Exact trace event and UdpFlowTag coverage counts.",
    "physical_link_drops.csv": "Exact queue/device/PHY drop trace events.",
    "routing_drops.csv": "Exact routing/no-route drop trace events.",
    "udp_send_failures.csv": "Exact Socket::SendTo failure events.",
    "gsl_queue_summary.csv": "GSL/access queue occupancy summary.",
    "max_queue_occupancy_by_algorithm.csv": "Sampled maximum ISL queue occupancy.",
    "statistics.txt": "Extended packet delivery statistics.",
    "flow_selection_diagnostics.csv": "Flow-selection candidate diagnostics.",
    "corridor_overlap_summary.csv": "Candidate path-corridor overlap diagnostics.",
    "gsl_load_by_endpoint.csv": "Estimated endpoint GSL load.",
    "isl_corridor_load_summary.csv": "Estimated load on corridor ISLs.",
    "fallback_phase_summary.csv": "Flow-selection fallback phase counts.",
    "corridor_concentration_summary.csv": "Scenario corridor concentration check.",
    "satellite_interface_load_summary.csv": "Satellite-interface proxy load.",
    "flow_selection_warnings.txt": "Flow-selection warnings.",
    "packet_loss_count_by_algorithm.png": "Synthetic sent-minus-received loss figure.",
    "failed_flow_count.png": "Flows with zero received packets.",
    "physical_drop_count_by_algorithm.png": "Exact trace event counts by algorithm.",
    "physical_drop_by_link_type.png": "Exact trace event counts by link type.",
    "gsl_queue_occupancy_by_algorithm.png": "Maximum GSL queue occupancy.",
    "tag_coverage_diagnostics.png": "Trace event counts and tag coverage; zero events are N/A.",
    "saturation_overlap_by_algorithm.png": "Inferred path/saturation overlap counts.",
    "max_queue_occupancy_top_links.png": "Top sampled ISL queue occupancies.",
    "corridor_concentration_summary.png": "Corridor concentration diagnostic.",
    "satellite_interface_load_summary.png": "Satellite-interface load diagnostic.",
    "fallback_phase_summary.png": "Flow-selection fallback diagnostic.",
}


LEGACY_FILES = {
    "loss_attribution_summary.csv": "Superseded by loss_attribution_breakdown_v3.csv.",
    "loss_attribution_detailed.csv": "Superseded by loss_attribution_detailed_v3.csv.",
    "loss_attribution_breakdown_v2.csv": "Superseded by v3 time-aware attribution.",
    "loss_attribution_breakdown.png": "Legacy attribution figure.",
    "loss_attribution_breakdown_v2.png": "Legacy v2 attribution figure.",
    "link_drops.csv": "Synthetic flow loss summary, not physical link drops.",
    "synthetic_link_drops.csv": "Compatibility alias for synthetic flow loss.",
    "link_drop_heatmap.png": "Deprecated name for a queue occupancy diagnostic.",
    "path_replay_coverage.png": (
        "Deprecated ratio-only plot; zero trace events incorrectly looked like full coverage."
    ),
}


_DUPLICATE_PLOT_RE = re.compile(r"_bg_flow_count_\d+\.png$")


def ensure_standard_layout(comparison_dir):
    for dirname in ["core", "diagnostics", "legacy"]:
        os.makedirs(os.path.join(comparison_dir, dirname), exist_ok=True)


def category_for_filename(filename):
    if filename in CORE_FILES:
        return "core"
    if filename in DIAGNOSTIC_FILES:
        return "diagnostics"
    if filename in LEGACY_FILES:
        return "legacy"
    if _DUPLICATE_PLOT_RE.search(filename):
        return "duplicates"
    return None


def output_path(comparison_dir, filename, output_layout="standard"):
    if output_layout == "flat":
        return os.path.join(comparison_dir, filename)
    category = category_for_filename(filename)
    if category == "core":
        return os.path.join(comparison_dir, "core", filename)
    if category == "legacy":
        return os.path.join(comparison_dir, "legacy", filename)
    return os.path.join(comparison_dir, "diagnostics", filename)


def resolve_input_path(comparison_dir, filename):
    candidates = [
        output_path(comparison_dir, filename, "standard"),
        os.path.join(comparison_dir, filename),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[0]


def _unique_destination(path):
    if not os.path.lexists(path):
        return path
    root, extension = os.path.splitext(path)
    index = 1
    while os.path.lexists("%s_%d%s" % (root, index, extension)):
        index += 1
    return "%s_%d%s" % (root, index, extension)


def archive_flat_outputs(comparison_dir):
    ensure_standard_layout(comparison_dir)
    archived = []
    for filename in sorted(os.listdir(comparison_dir)):
        source = os.path.join(comparison_dir, filename)
        if not os.path.isfile(source) or os.path.islink(source):
            continue
        category = category_for_filename(filename)
        if category is None:
            continue
        if category == "duplicates":
            destination = os.path.join(comparison_dir, "legacy", "duplicates", filename)
        else:
            destination = output_path(comparison_dir, filename, "standard")
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        destination = _unique_destination(destination)
        shutil.move(source, destination)
        archived.append((source, destination))
    return archived


def link_selection_diagnostic(source, destination):
    if os.path.lexists(destination):
        return
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    relative_source = os.path.relpath(source, os.path.dirname(destination))
    os.symlink(relative_source, destination)


def write_deprecated_notes(comparison_dir):
    ensure_standard_layout(comparison_dir)
    path = os.path.join(comparison_dir, "legacy", "deprecated_notes.md")
    with open(path, "w") as f_out:
        f_out.write(
            "# Deprecated Packet Delivery Outputs\n\n"
            "The files in this directory are retained only for historical or "
            "backward-compatible analysis. They are not recommended for paper results.\n\n"
            "- `loss_attribution_summary.csv`, `loss_attribution_detailed.csv`, and "
            "`loss_attribution_breakdown_v2.csv` are superseded by the time-aware v3 outputs.\n"
            "- `loss_attribution_breakdown.png` and "
            "`loss_attribution_breakdown_v2.png` visualize deprecated attribution models.\n"
            "- `link_drops.csv` is a sent-minus-received flow summary. It is not a "
            "physical link-drop trace.\n"
            "- `link_drop_heatmap.png` represented sampled queue occupancy under a "
            "misleading name. Use `diagnostics/max_queue_occupancy_top_links.png`.\n"
            "- `path_replay_coverage.png` mixed path replay and tag ratios and could "
            "show full tag coverage when no trace events existed. Use "
            "`diagnostics/tag_coverage_diagnostics.png` and "
            "`core/path_replay_diagnostics.csv`.\n"
            "- `duplicates/` preserves old `_bg_flow_count_<N>.png` copies. The "
            "unsuffixed canonical plots are now generated only once.\n"
        )
    return path


def write_result_guide(comparison_dir):
    ensure_standard_layout(comparison_dir)
    path = os.path.join(comparison_dir, "README.md")
    with open(path, "w") as f_out:
        f_out.write(
            "# Packet Delivery Result Guide\n\n"
            "Use `core/` as the formal analysis entry point. Use `diagnostics/` "
            "for debugging and deeper interpretation. `legacy/` contains deprecated "
            "or duplicate historical outputs and should not be used for paper figures.\n\n"
            "## Loss Definition\n\n"
            "Synthetic loss is UDP sender count minus UDP receiver count. It means a "
            "packet did not reach the UDP application before simulation end; it does "
            "not by itself identify where the packet disappeared.\n\n"
            "## Attribution Levels\n\n"
            "| Type | Meaning | Evidence | Nature |\n"
            "| --- | --- | --- | --- |\n"
            "| Exact physical queue drop | A queue rejected a packet and a QueueDrop or DropBeforeEnqueue callback fired. | `physical_link_drops.csv` | Exact |\n"
            "| Exact physical PHY drop | A PhyTxDrop or PhyRxDrop callback fired. | `physical_link_drops.csv` | Exact |\n"
            "| Exact routing drop | Routing or an arbiter reported no route. | `routing_drops.csv` | Exact |\n"
            "| Exact send failure | `Socket::SendTo()` returned failure. | `udp_send_failures.csv` | Exact |\n"
            "| ISL associated | A replayed flow path overlapped an at-capacity ISL queue in the same time window. | path replay and ISL queue history | Inferred |\n"
            "| GSL associated | A replayed flow path overlapped an at-capacity GSL queue in the same time window. | path replay and GSL queue history | Inferred |\n"
            "| Mixed associated | One flow's residual loss has both ISL and GSL saturation-overlap evidence. | path replay and queue histories | Inferred |\n"
            "| Tail possible | Residual loss may still have been in flight at simulation end. | traffic stop, simulation end, drain time | Inferred |\n"
            "| Unclassified | No exact event or supported association explains the residual. | residual loss | Unknown |\n"
            "| No loss | Sent packets equal received packets. | UDP counters | N/A |\n\n"
            "Physical drop is best read as **exact traced link/device drop**. A queue "
            "reaching 100 packets is saturation evidence, not proof of a drop. Exact "
            "queue attribution requires an enqueue rejection and a matching callback. "
            "`UdpFlowTag` identifies a flow when an event occurs; it does not create "
            "drop events. Therefore exact physical drop counts may be zero even when "
            "synthetic loss and queue saturation exist.\n\n"
            "Mixed is flow-level ambiguity. It does not prove that every lost packet "
            "crossed both bottlenecks, identify whether ISL or GSL caused the loss, or "
            "divide loss quantitatively between them.\n\n"
            "## Reading v3\n\n"
            "Start with `core/loss_attribution_breakdown_v3.csv` and its PNG, then use "
            "`core/loss_attribution_detailed_v3.csv` for per-flow reconciliation. "
            "Exact categories are trace-backed. Associated categories require "
            "same-window dynamic path and queue-saturation overlap and remain inferred. "
            "Unclassified loss is the unexplained residual. Confidence is high only "
            "when exact events reconcile the loss, medium when association evidence "
            "exists, and low when substantial residual loss remains unclassified.\n\n"
            "## Large Diagnostics\n\n"
            "`diagnostics/queue_saturation_timeline_at_capacity.csv` is the default "
            "timeline and retains only `is_at_capacity=true` rows. The full timeline "
            "can be requested with `--write-full-queue-saturation-timeline`; it may be "
            "multiple gigabytes and is not generated by default.\n"
        )
    return path


def _manifest_rows(comparison_dir):
    rows = [
        {
            "relative_path": "README.md",
            "category": "core",
            "status": "active",
            "description": "User-oriented packet delivery and attribution guide.",
            "source_inputs": "Output layout and attribution definitions",
            "recommended_for_paper": "yes",
            "notes": "Read this first.",
        },
        {
            "relative_path": "output_manifest.csv",
            "category": "core",
            "status": "active",
            "description": "Inventory and recommendation status for packet delivery outputs.",
            "source_inputs": "Generated output inventory",
            "recommended_for_paper": "yes",
            "notes": "",
        },
        {
            "relative_path": os.path.join("legacy", "deprecated_notes.md"),
            "category": "deprecated",
            "status": "deprecated",
            "description": "Reasons legacy and misleading outputs are deprecated.",
            "source_inputs": "Output compatibility policy",
            "recommended_for_paper": "no",
            "notes": "Documentation only.",
        },
    ]
    for filename, (description, source_inputs, recommended) in CORE_FILES.items():
        path = os.path.join("core", filename)
        exists = os.path.exists(os.path.join(comparison_dir, path))
        rows.append({
            "relative_path": path,
            "category": "core",
            "status": "active",
            "description": description,
            "source_inputs": source_inputs,
            "recommended_for_paper": "yes" if recommended else "no",
            "notes": "" if exists else "Not generated for this run or not generated yet.",
        })
    for filename, description in DIAGNOSTIC_FILES.items():
        path = os.path.join("diagnostics", filename)
        exists = os.path.exists(os.path.join(comparison_dir, path))
        is_large = filename == "queue_saturation_timeline.csv"
        rows.append({
            "relative_path": path,
            "category": "large_debug" if is_large else "diagnostic",
            "status": "large_optional" if is_large else "diagnostic_only",
            "description": description,
            "source_inputs": "Run logs and analysis intermediates",
            "recommended_for_paper": "no",
            "notes": (
                (
                    "Historical full timeline preserved; new generation is "
                    "disabled by default."
                    if is_large and exists
                    else "Disabled by default; enable explicitly."
                )
                if is_large
                else ("" if exists else "Not generated for this run.")
            ),
        })
    for filename, description in LEGACY_FILES.items():
        path = os.path.join("legacy", filename)
        rows.append({
            "relative_path": path,
            "category": "deprecated",
            "status": "deprecated",
            "description": description,
            "source_inputs": "Legacy analysis",
            "recommended_for_paper": "no",
            "notes": (
                "Retained for compatibility."
                if os.path.exists(os.path.join(comparison_dir, path))
                else "Not generated by default."
            ),
        })
    duplicates_dir = os.path.join(comparison_dir, "legacy", "duplicates")
    if os.path.isdir(duplicates_dir):
        for filename in sorted(os.listdir(duplicates_dir)):
            rows.append({
                "relative_path": os.path.join("legacy", "duplicates", filename),
                "category": "duplicate",
                "status": "duplicate",
                "description": "Historical duplicate plot with a background-flow suffix.",
                "source_inputs": "Canonical unsuffixed plot",
                "recommended_for_paper": "no",
                "notes": "Preserved during flat-layout migration; no longer generated.",
            })
    return rows


def write_output_manifest(comparison_dir):
    ensure_standard_layout(comparison_dir)
    path = os.path.join(comparison_dir, "output_manifest.csv")
    fieldnames = [
        "relative_path",
        "category",
        "status",
        "description",
        "source_inputs",
        "recommended_for_paper",
        "notes",
    ]
    with open(path, "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_manifest_rows(comparison_dir))
    return path
