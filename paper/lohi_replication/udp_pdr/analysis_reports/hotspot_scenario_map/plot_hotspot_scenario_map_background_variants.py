#!/usr/bin/env python3
"""Draw 10-, 15-, and 20-pair UDP-PDR hotspot-map variants.

Every displayed OD pair belongs to the strict 24-pair H90/H100+ formal
selection.  The 10-pair set emphasizes geographic direction diversity while
retaining exact t=0 target-corridor overlap.  The 15-pair set is the largest
formal subset for which every displayed t=0 path overlaps that single t=0
target trace.  The 20-pair set adds five formal pairs whose target overlap
occurs at another selector sample (29.9 or 59.9 s).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/hypatia-hotspot-map-mpl")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/hypatia-hotspot-map-xdg")

import cartopy.crs as ccrs
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from plot_hotspot_scenario_map import (
    FOCUS_PAIR,
    H80_BASELINE_DIR,
    load_forwarding_state_at,
    load_network_context,
    node_positions_at_time,
    replay_path,
)
from plot_hotspot_scenario_map_focused import (
    BACKGROUND_COLOR,
    CORRIDOR_COLOR,
    CORRIDOR_CORE_COLOR,
    FOCUS_COLOR,
    REGION_COLOR,
    TEXT_COLOR,
    UNSELECTED_GS_COLOR,
    USED_SATELLITE_COLOR,
    add_all_ground_stations,
    add_base_map,
    add_congestion_region,
    add_focus_labels,
    add_selected_endpoint,
)
from udp_rtt_analysis import plot_connection


SCRIPT_PATH = Path(__file__).resolve()

# Pair index follows the formal H100+ selection order after collapsing the two
# directed flows of each bidirectional OD pair.
FORMAL_BACKGROUND_PAIRS = (
    (1, "Beijing ↔ Khartoum", 726, 791),
    (2, "Lagos ↔ Qingdao", 736, 801),
    (3, "Luanda ↔ Jinan", 786, 813),
    (4, "Kinshasa ↔ Tianjin", 742, 743),
    (5, "Cairo ↔ Dalian", 728, 805),
    (6, "Xi'an ↔ Abidjan", 775, 795),
    (7, "Alexandria ↔ Zhengzhou", 798, 807),
    (8, "Shanghai ↔ Madrid", 722, 774),
    (9, "Nanjing ↔ Barcelona", 763, 789),
    (10, "Istanbul ↔ Hangzhou", 734, 771),
    (11, "Tokyo ↔ Ankara", 720, 799),
    (12, "Shenyang ↔ Jiddah", 773, 811),
    (13, "Osaka ↔ Nairobi", 727, 816),
    (14, "Nagoya ↔ Dar es Salaam", 753, 792),
    (15, "Riyadh ↔ Suzhou", 772, 787),
    (16, "Tehran ↔ Xiamen", 759, 806),
    (17, "Baghdad ↔ Shantou", 769, 815),
    (18, "Manila ↔ Kabul", 737, 800),
    (19, "Karachi ↔ Chongqing", 731, 735),
    (20, "Wuhan ↔ Ahmadabad", 760, 764),
    (21, "Lahore ↔ Sydney", 758, 804),
    (22, "Chengdu ↔ Surat", 761, 781),
    (23, "Delhi ↔ Fortaleza", 721, 818),
    (24, "Los Angeles ↔ Singapore", 740, 783),
)

# These sets are nested so pair-count is the only visual quantity being added.
# The first seven retain the strongest formal overlap.  The next entries add
# opposite diagonals and additional continents before geographically similar
# routes.
PAIR_VARIANT_INDICES = {
    5: (1, 2, 3, 4, 5),
    10: (1, 2, 3, 4, 5, 6, 7, 18, 23, 24),
    15: (1, 2, 3, 4, 5, 6, 7, 13, 14, 16, 18, 19, 20, 23, 24),
    20: (
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        11,
        12,
        13,
        14,
        16,
        18,
        19,
        20,
        21,
        22,
        23,
        24,
    ),
}

PAIR_STYLES = {
    5: {
        "route_width": 2.35,
        "route_alpha": 0.68,
        "endpoint_size": 54,
        "endpoint_halo_size": 100,
        "satellite_size": 45,
        "satellite_alpha": 0.92,
    },
    10: {
        "route_width": 1.65,
        "route_alpha": 0.45,
        "endpoint_size": 42,
        "endpoint_halo_size": 80,
        "satellite_size": 34,
        "satellite_alpha": 0.82,
    },
    15: {
        "route_width": 1.40,
        "route_alpha": 0.36,
        "endpoint_size": 38,
        "endpoint_halo_size": 71,
        "satellite_size": 29,
        "satellite_alpha": 0.72,
    },
    20: {
        "route_width": 1.20,
        "route_alpha": 0.28,
        "endpoint_size": 34,
        "endpoint_halo_size": 64,
        "satellite_size": 25,
        "satellite_alpha": 0.62,
    },
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Draw direction-diverse UDP-PDR background-pair variants."
    )
    parser.add_argument(
        "--pair-count",
        type=int,
        nargs="+",
        choices=sorted(PAIR_VARIANT_INDICES),
        default=[10, 15, 20],
        help="One or more pair counts to render (default: 10 15 20).",
    )
    return parser.parse_args()


def undirected_edges(path):
    return {
        tuple(sorted((source, destination)))
        for source, destination in zip(path[:-1], path[1:])
    }


def draw_plate_carree_path(
    ax,
    path,
    positions,
    *,
    color,
    linewidth,
    alpha=1.0,
    zorder=5,
):
    """Draw a route link-by-link, splitting links at the antimeridian."""
    coordinate_system = ccrs.PlateCarree()
    artists = []
    for source, destination in zip(path[:-1], path[1:]):
        source_lat, source_lon = positions[source]
        destination_lat, destination_lon = positions[destination]
        artists.extend(
            plot_connection(
                ax,
                source_lon,
                source_lat,
                destination_lon,
                destination_lat,
                color=color,
                linewidth=linewidth,
                alpha=alpha,
                solid_capstyle="round",
                transform=coordinate_system,
                zorder=zorder,
            )
        )
    return artists


def replay_variant_routes(pair_count):
    if not H80_BASELINE_DIR.exists():
        raise FileNotFoundError(
            "The H80 Baseline run directory is required: %s"
            % H80_BASELINE_DIR
        )

    network = load_network_context(str(H80_BASELINE_DIR))
    state, snapshot_time_ns = load_forwarding_state_at(
        str(H80_BASELINE_DIR / "dynamic_state"),
        0,
    )
    if snapshot_time_ns != 0:
        raise RuntimeError(
            "Expected the t=0 forwarding snapshot, got %r" % snapshot_time_ns
        )

    def route(source, destination):
        result = replay_path(
            state,
            source,
            destination,
            network.num_satellites,
            network.num_nodes,
        )
        if not result.success:
            raise RuntimeError(
                "Unable to replay %d -> %d at t=0: %s"
                % (source, destination, result.status)
            )
        return tuple(result.path)

    pair_lookup = {
        pair_index: (label, source, destination)
        for pair_index, label, source, destination
        in FORMAL_BACKGROUND_PAIRS
    }
    selected_pairs = []
    for pair_index in PAIR_VARIANT_INDICES[pair_count]:
        label, source, destination = pair_lookup[pair_index]
        selected_pairs.append(
            (
                pair_index,
                label,
                route(source, destination),
                source,
                destination,
            )
        )

    positions = node_positions_at_time(network, 0, {})
    focus_path = route(*FOCUS_PAIR)
    return network, positions, focus_path, selected_pairs


def add_background_endpoints(
    ax,
    node_ids,
    positions,
    coordinate_system,
    style,
):
    nodes = sorted(set(node_ids))
    longitudes = [positions[node][1] for node in nodes]
    latitudes = [positions[node][0] for node in nodes]
    ax.scatter(
        longitudes,
        latitudes,
        marker="o",
        s=style["endpoint_halo_size"],
        facecolor="white",
        edgecolor="white",
        linewidth=0,
        transform=coordinate_system,
        zorder=8.9,
    )
    ax.scatter(
        longitudes,
        latitudes,
        marker="o",
        s=style["endpoint_size"],
        facecolor=BACKGROUND_COLOR,
        edgecolor="#23313F",
        linewidth=0.70,
        transform=coordinate_system,
        zorder=9,
    )


def add_route_satellites(
    ax,
    used_satellites,
    target_satellites,
    positions,
    coordinate_system,
    style,
):
    target_nodes = set(target_satellites)
    non_target_nodes = sorted(set(used_satellites) - target_nodes)
    ax.scatter(
        [positions[node][1] for node in non_target_nodes],
        [positions[node][0] for node in non_target_nodes],
        marker="^",
        s=style["satellite_size"],
        facecolor=USED_SATELLITE_COLOR,
        edgecolor="white",
        linewidth=0.45,
        alpha=style["satellite_alpha"],
        transform=coordinate_system,
        zorder=10,
    )
    ax.scatter(
        [positions[node][1] for node in target_nodes],
        [positions[node][0] for node in target_nodes],
        marker="^",
        s=64,
        facecolor=CORRIDOR_COLOR,
        edgecolor="#A56700",
        linewidth=0.90,
        transform=coordinate_system,
        zorder=10.2,
    )


def add_variant_legend(ax, pair_count):
    handles = [
        Line2D(
            [0],
            [0],
            color=FOCUS_COLOR,
            linewidth=3.8,
            label="Focus Flow Pair",
        ),
        Line2D(
            [0],
            [0],
            color=BACKGROUND_COLOR,
            linewidth=3.0,
            label="Background Flow Pairs (n = %d)" % pair_count,
        ),
        Line2D(
            [0],
            [0],
            color=CORRIDOR_COLOR,
            linewidth=10,
            alpha=0.75,
            label="Target Middle-ISL Corridor (t = 0)",
        ),
        Patch(
            facecolor=to_rgba(REGION_COLOR, 0.09),
            edgecolor=REGION_COLOR,
            linewidth=1.6,
            linestyle="--",
            label="Main Congestion Region",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markersize=6.5,
            markerfacecolor="none",
            markeredgecolor=UNSELECTED_GS_COLOR,
            label="Candidate Ground Stations (n = 100)",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markersize=7,
            markerfacecolor=BACKGROUND_COLOR,
            markeredgecolor="white",
            label="Background Endpoints",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markersize=7.5,
            markerfacecolor=FOCUS_COLOR,
            markeredgecolor="white",
            label="Focus Endpoints",
        ),
        Line2D(
            [0],
            [0],
            marker="^",
            linestyle="none",
            markersize=8,
            markerfacecolor=USED_SATELLITE_COLOR,
            markeredgecolor="white",
            label="Selected Route Satellites (t = 0)",
        ),
    ]
    legend = ax.legend(
        handles=handles,
        loc="lower left",
        bbox_to_anchor=(0.006, 0.012),
        ncol=2,
        fontsize=9.5,
        frameon=True,
        fancybox=True,
        framealpha=0.94,
        borderpad=0.65,
        handlelength=2.3,
        columnspacing=1.15,
        labelspacing=0.58,
    )
    legend.get_frame().set_facecolor("white")
    legend.get_frame().set_edgecolor("#59636E")
    legend.get_frame().set_linewidth(0.8)


def build_figure(pair_count):
    network, positions, focus_path, background_paths = replay_variant_routes(
        pair_count
    )
    style = PAIR_STYLES[pair_count]
    coordinate_system = ccrs.PlateCarree()
    target_corridor_trace = tuple(focus_path[2:-2])
    target_edges = undirected_edges(target_corridor_trace)

    overlap_counts = {
        pair_index: len(undirected_edges(path) & target_edges)
        for pair_index, _, path, _, _ in background_paths
    }
    t0_overlap_count = sum(
        overlap_count > 0 for overlap_count in overlap_counts.values()
    )
    expected_t0_overlap_count = {5: 5, 10: 10, 15: 15, 20: 15}[pair_count]
    if t0_overlap_count != expected_t0_overlap_count:
        raise RuntimeError(
            "Expected %d/%d t=0 target-overlapping pairs, found %d"
            % (expected_t0_overlap_count, pair_count, t0_overlap_count)
        )

    all_paths = [focus_path] + [
        path for _, _, path, _, _ in background_paths
    ]
    used_satellites = sorted(
        {
            node
            for path in all_paths
            for node in path
            if node < network.num_satellites
        }
    )

    fig = plt.figure(figsize=(12, 6.75), facecolor="white")
    ax = fig.add_axes(
        [0.035, 0.065, 0.93, 0.835],
        projection=coordinate_system,
    )
    add_base_map(ax)
    add_congestion_region(ax, coordinate_system)
    add_all_ground_stations(ax, network, positions, coordinate_system)

    draw_plate_carree_path(
        ax,
        target_corridor_trace,
        positions,
        color=CORRIDOR_COLOR,
        linewidth=14,
        alpha=0.55,
        zorder=4,
    )
    draw_plate_carree_path(
        ax,
        target_corridor_trace,
        positions,
        color=CORRIDOR_CORE_COLOR,
        linewidth=5.3,
        alpha=0.88,
        zorder=4.1,
    )

    for _, _, path, _, _ in background_paths:
        draw_plate_carree_path(
            ax,
            path,
            positions,
            color=BACKGROUND_COLOR,
            linewidth=style["route_width"],
            alpha=style["route_alpha"],
            zorder=5,
        )

    draw_plate_carree_path(
        ax,
        focus_path,
        positions,
        color=FOCUS_COLOR,
        linewidth=3.6,
        alpha=0.98,
        zorder=7,
    )

    background_endpoint_nodes = {
        node
        for _, _, _, source, destination in background_paths
        for node in (source, destination)
    }
    add_background_endpoints(
        ax,
        background_endpoint_nodes,
        positions,
        coordinate_system,
        style,
    )
    add_route_satellites(
        ax,
        used_satellites,
        target_corridor_trace,
        positions,
        coordinate_system,
        style,
    )
    add_selected_endpoint(
        ax,
        FOCUS_PAIR[0],
        positions,
        coordinate_system,
        color=FOCUS_COLOR,
        size=76,
        zorder=11,
    )
    add_selected_endpoint(
        ax,
        FOCUS_PAIR[1],
        positions,
        coordinate_system,
        color=FOCUS_COLOR,
        size=76,
        zorder=11,
    )

    add_focus_labels(ax, positions, coordinate_system)
    add_variant_legend(ax, pair_count)

    fig.text(
        0.5,
        0.956,
        "UDP-PDR Hotspot Traffic Scenario",
        ha="center",
        va="center",
        fontsize=27,
        fontweight="bold",
        color="#111827",
    )
    return (
        fig,
        focus_path,
        background_paths,
        used_satellites,
        overlap_counts,
    )


def render_variant(pair_count):
    (
        fig,
        focus_path,
        background_paths,
        used_satellites,
        overlap_counts,
    ) = build_figure(pair_count)
    output_stem = SCRIPT_PATH.with_name(
        "udp_pdr_hotspot_traffic_scenario_bg%dpairs" % pair_count
    )
    outputs = (
        output_stem.with_suffix(".png"),
        output_stem.with_suffix(".svg"),
        output_stem.with_suffix(".pdf"),
    )
    fig.savefig(outputs[0], dpi=330, facecolor=fig.get_facecolor())
    fig.savefig(outputs[1], facecolor=fig.get_facecolor())
    fig.savefig(outputs[2], facecolor=fig.get_facecolor())
    plt.close(fig)

    print(
        "\nVariant %d pairs: %d selected route satellites; "
        "%d/%d paths overlap the exact t=0 target trace"
        % (
            pair_count,
            len(used_satellites),
            sum(value > 0 for value in overlap_counts.values()),
            pair_count,
        )
    )
    print("Focus path: %s" % " -> ".join(map(str, focus_path)))
    for pair_index, label, path, _, _ in background_paths:
        print(
            "  #%02d %-30s overlap=%d  path=%s"
            % (
                pair_index,
                label,
                overlap_counts[pair_index],
                " -> ".join(map(str, path)),
            )
        )
    for output in outputs:
        print("Wrote %s" % output)


def main():
    args = parse_args()
    for pair_count in dict.fromkeys(args.pair_count):
        render_variant(pair_count)


if __name__ == "__main__":
    main()
