#!/usr/bin/env python3
"""Draw the focused UDP-PDR hotspot traffic scenario map.

This version intentionally matches the existing graphical route-map style:
Plate Carree projection, Natural Earth colors, hollow markers for the complete
100-ground-station candidate set, and filled triangles for route-used
satellites. The traffic geometry is replayed from the H80 Baseline t=0
forwarding state.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/hypatia-hotspot-map-mpl")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/hypatia-hotspot-map-xdg")

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Polygon
from matplotlib.ticker import FixedLocator

from plot_hotspot_scenario_map import (
    FOCUS_PAIR,
    rounded_region_points,
    replay_routes,
    shared_background_trace,
)


SCRIPT_PATH = Path(__file__).resolve()

FOCUS_COLOR = "#C62828"
BACKGROUND_COLOR = "#007C91"
CORRIDOR_COLOR = "#F2B544"
CORRIDOR_CORE_COLOR = "#E69F00"
REGION_COLOR = "#6654A3"
LAND_COLOR = "#EFEFDB"
OCEAN_COLOR = "#97B6E1"
TEXT_COLOR = "#202020"
USED_SATELLITE_COLOR = "#A61111"
UNSELECTED_GS_COLOR = "#111111"


def draw_plate_carree_path(
    ax,
    path,
    positions,
    *,
    color,
    linewidth,
    alpha=1.0,
    zorder=5,
    linestyle="-",
):
    """Draw a node path using the same Plate Carree link style as route plots."""
    transform = ccrs.PlateCarree()
    artists = []
    for source, destination in zip(path[:-1], path[1:]):
        source_lat, source_lon = positions[source]
        destination_lat, destination_lon = positions[destination]
        artists.extend(
            ax.plot(
                [source_lon, destination_lon],
                [source_lat, destination_lat],
                color=color,
                linewidth=linewidth,
                alpha=alpha,
                linestyle=linestyle,
                solid_capstyle="round",
                transform=transform,
                zorder=zorder,
            )
        )
    return artists


def add_base_map(ax):
    coordinate_system = ccrs.PlateCarree()
    ax.set_global()
    ax.add_feature(
        cfeature.OCEAN.with_scale("110m"),
        facecolor=OCEAN_COLOR,
        edgecolor="none",
        zorder=0,
    )
    ax.add_feature(
        cfeature.LAND.with_scale("110m"),
        facecolor=LAND_COLOR,
        edgecolor="#3F3F3F",
        linewidth=0.28,
        zorder=1,
    )
    ax.add_feature(
        cfeature.BORDERS.with_scale("110m"),
        edgecolor="#888888",
        linewidth=0.28,
        zorder=1.2,
    )
    gridlines = ax.gridlines(
        crs=coordinate_system,
        draw_labels=True,
        linewidth=0.42,
        color="#6F7D8A",
        alpha=0.42,
        linestyle=":",
    )
    gridlines.xlocator = FixedLocator([-180, -120, -60, 0, 60, 120, 180])
    gridlines.ylocator = FixedLocator([-60, -30, 0, 30, 60])
    gridlines.top_labels = False
    gridlines.right_labels = False
    gridlines.xlabel_style = {"size": 10, "color": TEXT_COLOR}
    gridlines.ylabel_style = {"size": 10, "color": TEXT_COLOR}
    return coordinate_system


def add_congestion_region(ax, coordinate_system):
    """Draw the data-derived padded bounding box of the exact common trace."""
    polygon = Polygon(
        rounded_region_points(24, 126, 20, 43, 5, samples=18),
        closed=True,
        facecolor=to_rgba(REGION_COLOR, 0.09),
        edgecolor=REGION_COLOR,
        linewidth=2.2,
        linestyle=(0, (5, 3)),
        transform=coordinate_system,
        zorder=2,
    )
    ax.add_patch(polygon)


def add_all_ground_stations(ax, network, positions, coordinate_system):
    ground_station_positions = positions[network.num_satellites :]
    if len(ground_station_positions) != 100:
        raise RuntimeError(
            "Expected exactly 100 candidate ground stations, found %d"
            % len(ground_station_positions)
        )
    ax.scatter(
        [longitude for _, longitude in ground_station_positions],
        [latitude for latitude, _ in ground_station_positions],
        marker="o",
        s=20,
        facecolors="none",
        edgecolors=UNSELECTED_GS_COLOR,
        linewidths=0.65,
        alpha=0.82,
        transform=coordinate_system,
        zorder=3,
    )


def add_selected_endpoint(
    ax,
    node_id,
    positions,
    coordinate_system,
    *,
    color,
    size,
    zorder,
):
    latitude, longitude = positions[node_id]
    ax.scatter(
        [longitude],
        [latitude],
        marker="o",
        s=size + 62,
        facecolor="white",
        edgecolor="white",
        linewidth=0,
        transform=coordinate_system,
        zorder=zorder,
    )
    ax.scatter(
        [longitude],
        [latitude],
        marker="o",
        s=size,
        facecolor=color,
        edgecolor="#23313F",
        linewidth=0.8,
        transform=coordinate_system,
        zorder=zorder + 0.1,
    )


def add_selected_satellites(
    ax,
    used_satellites,
    target_satellites,
    positions,
    coordinate_system,
):
    non_target = sorted(set(used_satellites) - set(target_satellites))
    ax.scatter(
        [positions[node][1] for node in non_target],
        [positions[node][0] for node in non_target],
        marker="^",
        s=45,
        facecolor=USED_SATELLITE_COLOR,
        edgecolor="white",
        linewidth=0.65,
        transform=coordinate_system,
        zorder=10,
    )
    ax.scatter(
        [positions[node][1] for node in target_satellites],
        [positions[node][0] for node in target_satellites],
        marker="^",
        s=66,
        facecolor=CORRIDOR_COLOR,
        edgecolor="#A56700",
        linewidth=0.9,
        transform=coordinate_system,
        zorder=10.2,
    )


def add_focus_labels(ax, positions, coordinate_system):
    johannesburg_lat, johannesburg_lon = positions[FOCUS_PAIR[0]]
    fukuoka_lat, fukuoka_lon = positions[FOCUS_PAIR[1]]
    label_box = {
        "boxstyle": "round,pad=0.20",
        "facecolor": "white",
        "edgecolor": "none",
        "alpha": 0.90,
    }
    ax.annotate(
        "Johannesburg",
        xy=(johannesburg_lon, johannesburg_lat),
        xytext=(11, -13),
        textcoords="offset points",
        fontsize=13,
        fontweight="bold",
        color=TEXT_COLOR,
        transform=coordinate_system,
        zorder=13,
        bbox=label_box,
    )
    ax.annotate(
        "Fukuoka",
        xy=(fukuoka_lon, fukuoka_lat),
        xytext=(11, 7),
        textcoords="offset points",
        fontsize=13,
        fontweight="bold",
        color=TEXT_COLOR,
        transform=coordinate_system,
        zorder=13,
        bbox=label_box,
    )


def add_legend(ax):
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
            label="Background Flow Pairs",
        ),
        Line2D(
            [0],
            [0],
            color=CORRIDOR_COLOR,
            linewidth=10,
            alpha=0.75,
            label="Target Middle-ISL Corridor",
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
            label="Ground Stations (n = 100)",
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
            label="Route Satellites",
        ),
    ]
    legend = ax.legend(
        handles=handles,
        loc="lower left",
        bbox_to_anchor=(0.006, 0.012),
        ncol=1,
        fontsize=10.5,
        frameon=True,
        fancybox=True,
        framealpha=0.94,
        borderpad=0.62,
        handlelength=2.7,
        labelspacing=0.46,
    )
    legend.get_frame().set_facecolor("white")
    legend.get_frame().set_edgecolor("#59636E")
    legend.get_frame().set_linewidth(0.8)


def build_figure():
    network, positions, focus_path, background_paths = replay_routes()
    coordinate_system = ccrs.PlateCarree()
    shared_trace = shared_background_trace(focus_path, background_paths)
    target_corridor_trace = tuple(focus_path[2:-2])

    all_paths = [focus_path] + [
        path for _, path, _, _ in background_paths
    ]
    used_satellites = sorted(
        {
            node
            for path in all_paths
            for node in path
            if node < network.num_satellites
        }
    )
    if len(used_satellites) != 26:
        raise RuntimeError(
            "Expected 26 route-used satellites, found %d"
            % len(used_satellites)
        )

    fig = plt.figure(figsize=(12, 6.75), facecolor="white")
    ax = fig.add_axes(
        [0.035, 0.065, 0.93, 0.835],
        projection=coordinate_system,
    )
    add_base_map(ax)
    add_congestion_region(ax, coordinate_system)
    add_all_ground_stations(ax, network, positions, coordinate_system)

    # Nested strokes create the same clear amber → teal → crimson hierarchy as
    # the preferred concept while preserving exact forwarding-path geometry.
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

    for _, path, source, destination in background_paths:
        draw_plate_carree_path(
            ax,
            path,
            positions,
            color=BACKGROUND_COLOR,
            linewidth=2.35,
            alpha=0.68,
            zorder=5,
        )
        add_selected_endpoint(
            ax,
            source,
            positions,
            coordinate_system,
            color=BACKGROUND_COLOR,
            size=54,
            zorder=9,
        )
        add_selected_endpoint(
            ax,
            destination,
            positions,
            coordinate_system,
            color=BACKGROUND_COLOR,
            size=54,
            zorder=9,
        )

    draw_plate_carree_path(
        ax,
        shared_trace,
        positions,
        color=BACKGROUND_COLOR,
        linewidth=6.8,
        alpha=0.80,
        zorder=6,
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

    add_selected_satellites(
        ax,
        used_satellites,
        target_corridor_trace,
        positions,
        coordinate_system,
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
    add_legend(ax)

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
    return fig, focus_path, background_paths, used_satellites


def main():
    fig, focus_path, background_paths, used_satellites = build_figure()
    output_stem = SCRIPT_PATH.with_name(
        "udp_pdr_hotspot_traffic_scenario_focused"
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

    print("Focus path: %s" % " -> ".join(map(str, focus_path)))
    for label, path, _, _ in background_paths:
        print("%s: %s" % (label, " -> ".join(map(str, path))))
    print(
        "Selected route satellites (%d): %s"
        % (len(used_satellites), ",".join(map(str, used_satellites)))
    )
    for output in outputs:
        print("Wrote %s" % output)


if __name__ == "__main__":
    main()
