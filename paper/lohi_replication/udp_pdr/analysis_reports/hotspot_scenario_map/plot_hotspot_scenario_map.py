#!/usr/bin/env python3
"""Draw the publication schematic for the UDP-PDR hotspot scenarios.

The routes are replayed from the H80 Baseline forwarding state at t=0.  The
five background OD pairs are the highest-ranked bidirectional pairs shared by
all five formal scenarios.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/hypatia-hotspot-map-mpl")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/hypatia-hotspot-map-xdg")

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Patch, Polygon


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[5]
UDP_PDR_DIR = REPO_ROOT / "paper" / "lohi_replication" / "udp_pdr"
sys.path.insert(0, str(UDP_PDR_DIR))

from dynamic_path_replay import load_forwarding_state_at, replay_path
from udp_rtt_analysis import load_network_context, node_positions_at_time


H80_BASELINE_DIR = (
    UDP_PDR_DIR
    / "runs"
    / (
        "run_core_isl_hotspot_specific_src754_dst785_load_1p6x_"
        "bg_flow_count_32_sim200s_stop198s_isl10mbps_gsl100mbps_"
        "lohi_mgmt_control_plane_only_oneweb_isls_moving_udp_pdr"
    )
    / "algorithm_free_one_only_over_isls"
)

FOCUS_PAIR = (754, 785)
REPRESENTATIVE_BACKGROUND_PAIRS = (
    ("Khartoum ↔ Beijing", 791, 726),
    ("Lagos ↔ Qingdao", 736, 801),
    ("Luanda ↔ Jinan", 786, 813),
    ("Kinshasa ↔ Tianjin", 742, 743),
    ("Cairo ↔ Dalian", 728, 805),
)
SCENARIOS = (
    ("H40", 24),
    ("H60", 32),
    ("H80", 32),
    ("H90", 48),
    ("H100+", 48),
)

FOCUS_COLOR = "#C8343A"
BACKGROUND_COLOR = "#007C91"
CORRIDOR_COLOR = "#E69F00"
REGION_COLOR = "#6654A3"
LAND_COLOR = "#F2F0E8"
OCEAN_COLOR = "#EAF2F8"
TEXT_COLOR = "#1F2937"
MUTED_TEXT_COLOR = "#5F6B7A"


def replay_routes():
    """Load the actual t=0 Baseline routes used by the schematic."""
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

    def route(src, dst):
        result = replay_path(
            state,
            src,
            dst,
            network.num_satellites,
            network.num_nodes,
        )
        if not result.success:
            raise RuntimeError(
                "Unable to replay %d -> %d at t=0: %s"
                % (src, dst, result.status)
            )
        return tuple(result.path)

    focus_path = route(*FOCUS_PAIR)
    background_paths = [
        (label, route(src, dst), src, dst)
        for label, src, dst in REPRESENTATIVE_BACKGROUND_PAIRS
    ]
    positions = node_positions_at_time(network, 0, {})
    return network, positions, focus_path, background_paths


def path_edges(path):
    return set(zip(path[:-1], path[1:]))


def shared_background_trace(focus_path, background_paths):
    """Return the longest focus-path trace shared by all five BG routes."""
    common_edges = set.intersection(
        *(path_edges(path) for _, path, _, _ in background_paths)
    )
    runs = []
    current = []
    for source, destination in zip(focus_path[:-1], focus_path[1:]):
        if (source, destination) in common_edges:
            if not current:
                current = [source]
            current.append(destination)
        elif current:
            runs.append(tuple(current))
            current = []
    if current:
        runs.append(tuple(current))
    if not runs:
        raise RuntimeError("The representative background routes share no trace")
    return max(runs, key=len)


def coordinates(path, positions):
    latitudes = [positions[node][0] for node in path]
    longitudes = [positions[node][1] for node in path]
    return longitudes, latitudes


def draw_route(
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
    """Draw link-by-link so Cartopy handles each ISL as a geodesic segment."""
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
                transform=ccrs.Geodetic(),
                zorder=zorder,
            )
        )
    return artists


def rounded_region_points(west, east, south, north, radius, samples=12):
    """Construct a rounded rectangle in longitude/latitude coordinates."""
    import numpy as np

    points = []
    corners = (
        (east - radius, north - radius, 0, 90),
        (west + radius, north - radius, 90, 180),
        (west + radius, south + radius, 180, 270),
        (east - radius, south + radius, 270, 360),
    )
    for center_lon, center_lat, start, stop in corners:
        for angle in np.linspace(start, stop, samples):
            radians = np.deg2rad(angle)
            points.append(
                (
                    center_lon + radius * np.cos(radians),
                    center_lat + radius * np.sin(radians),
                )
            )
    return points


def add_map_background(ax):
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
        edgecolor="#A7ADB5",
        linewidth=0.35,
        zorder=1,
    )
    ax.add_feature(
        cfeature.BORDERS.with_scale("110m"),
        edgecolor="#B7BDC5",
        linewidth=0.28,
        zorder=2,
    )


def add_concentration_region(ax):
    region = Polygon(
        rounded_region_points(-4, 146, -34, 51, 10),
        closed=True,
        facecolor=REGION_COLOR,
        edgecolor=REGION_COLOR,
        linewidth=1.8,
        linestyle=(0, (5, 4)),
        alpha=0.10,
        transform=ccrs.PlateCarree(),
        zorder=2.5,
    )
    ax.add_patch(region)
    ax.text(
        71,
        52,
        "Main traffic concentration region",
        color=REGION_COLOR,
        fontsize=10.5,
        fontweight="bold",
        horizontalalignment="center",
        transform=ccrs.PlateCarree(),
        zorder=9,
        bbox={
            "boxstyle": "round,pad=0.25",
            "facecolor": "white",
            "edgecolor": "none",
            "alpha": 0.86,
        },
    )


def add_endpoint(
    ax,
    node_id,
    positions,
    *,
    color,
    size,
    zorder,
):
    latitude, longitude = positions[node_id]
    ax.scatter(
        [longitude],
        [latitude],
        s=size + 42,
        facecolor="white",
        edgecolor="white",
        linewidth=0,
        transform=ccrs.PlateCarree(),
        zorder=zorder,
    )
    ax.scatter(
        [longitude],
        [latitude],
        s=size,
        facecolor=color,
        edgecolor="#17324D",
        linewidth=0.55,
        transform=ccrs.PlateCarree(),
        zorder=zorder + 0.1,
    )


def add_map_annotations(ax, positions):
    plate = ccrs.PlateCarree()
    johannesburg_lat, johannesburg_lon = positions[754]
    fukuoka_lat, fukuoka_lon = positions[785]

    ax.annotate(
        "Johannesburg",
        xy=(johannesburg_lon, johannesburg_lat),
        xytext=(10, -13),
        textcoords="offset points",
        fontsize=9.5,
        fontweight="bold",
        color=TEXT_COLOR,
        transform=plate,
        zorder=10,
        bbox={
            "boxstyle": "round,pad=0.18",
            "facecolor": "white",
            "edgecolor": "none",
            "alpha": 0.84,
        },
    )
    ax.annotate(
        "Fukuoka",
        xy=(fukuoka_lon, fukuoka_lat),
        xytext=(10, 6),
        textcoords="offset points",
        fontsize=9.5,
        fontweight="bold",
        color=TEXT_COLOR,
        transform=plate,
        zorder=10,
        bbox={
            "boxstyle": "round,pad=0.18",
            "facecolor": "white",
            "edgecolor": "none",
            "alpha": 0.84,
        },
    )

    annotation_style = {
        "fontsize": 9.2,
        "fontweight": "bold",
        "color": TEXT_COLOR,
        "zorder": 10,
        "bbox": {
            "boxstyle": "round,pad=0.34",
            "facecolor": "white",
            "edgecolor": "#D6DAE0",
            "linewidth": 0.7,
            "alpha": 0.94,
        },
        "arrowprops": {
            "arrowstyle": "-",
            "linewidth": 1.0,
            "color": "#6B7280",
        },
        "transform": plate,
    }
    ax.annotate(
        "Focus Flow",
        xy=(29.8, -5),
        xytext=(44, -19),
        **annotation_style,
    )
    ax.annotate(
        "Target ISL Corridor",
        xy=(61, 27.2),
        xytext=(57, 12),
        color=CORRIDOR_COLOR,
        **{key: value for key, value in annotation_style.items() if key != "color"},
    )
    ax.annotate(
        "Focus + Background overlap",
        xy=(89, 31.5),
        xytext=(83, 16),
        color=BACKGROUND_COLOR,
        **{key: value for key, value in annotation_style.items() if key != "color"},
    )


def add_selection_inset(fig):
    inset = fig.add_axes([0.035, 0.565, 0.255, 0.26], zorder=20)
    inset.set_xlim(0, 1)
    inset.set_ylim(0, 1)
    inset.axis("off")
    panel = FancyBboxPatch(
        (0, 0),
        1,
        1,
        boxstyle="round,pad=0.018,rounding_size=0.045",
        facecolor="white",
        edgecolor="#C9CED6",
        linewidth=1.0,
        alpha=0.96,
    )
    inset.add_patch(panel)
    inset.text(
        0.06,
        0.89,
        "Background-flow selection",
        color=TEXT_COLOR,
        fontsize=11,
        fontweight="bold",
        va="center",
    )
    inset.plot(
        [0.06, 0.94],
        [0.80, 0.80],
        color="#E1E4E8",
        linewidth=0.8,
    )

    steps = (
        "Candidate ground-station pairs",
        "Rank by middle-ISL overlap\n+ path stability",
        "Enforce endpoint/interface\nspread constraints",
        "Select a nested flow prefix",
    )
    y_positions = (0.70, 0.52, 0.32, 0.13)
    for index, (text, y) in enumerate(zip(steps, y_positions), 1):
        inset.text(
            0.10,
            y,
            str(index),
            ha="center",
            va="center",
            fontsize=8.6,
            fontweight="bold",
            color="white",
            bbox={
                "boxstyle": "circle,pad=0.32",
                "facecolor": (
                    BACKGROUND_COLOR if index < 4 else FOCUS_COLOR
                ),
                "edgecolor": "none",
            },
        )
        inset.text(
            0.19,
            y,
            text,
            ha="left",
            va="center",
            fontsize=8.45,
            color=TEXT_COLOR,
            linespacing=1.15,
        )
        if index < len(steps):
            inset.annotate(
                "",
                xy=(0.10, y - 0.105),
                xytext=(0.10, y - 0.055),
                arrowprops={
                    "arrowstyle": "-|>",
                    "color": "#A6ADB7",
                    "linewidth": 0.8,
                },
            )


def add_legend(ax):
    handles = [
        Line2D(
            [0],
            [0],
            color=FOCUS_COLOR,
            linewidth=3.0,
            label="Focus pair: Johannesburg ↔ Fukuoka",
        ),
        Line2D(
            [0],
            [0],
            color=BACKGROUND_COLOR,
            linewidth=2.4,
            alpha=0.75,
            label="5 representative bidirectional BG pairs",
        ),
        Line2D(
            [0],
            [0],
            color=CORRIDOR_COLOR,
            linewidth=9,
            alpha=0.48,
            label="Target middle-ISL corridor (t=0 trace)",
        ),
        Patch(
            facecolor=REGION_COLOR,
            edgecolor=REGION_COLOR,
            linestyle="--",
            alpha=0.14,
            label="Main traffic concentration region",
        ),
    ]
    legend = ax.legend(
        handles=handles,
        loc="lower left",
        bbox_to_anchor=(0.012, 0.025),
        ncol=2,
        fontsize=8.4,
        frameon=True,
        fancybox=True,
        framealpha=0.96,
        borderpad=0.75,
        handlelength=2.8,
        columnspacing=1.7,
        labelspacing=0.7,
    )
    legend.get_frame().set_edgecolor("#C9CED6")
    legend.get_frame().set_linewidth(0.8)


def add_scenario_strip(fig):
    strip = fig.add_axes([0.025, 0.018, 0.95, 0.118], zorder=30)
    strip.set_xlim(0, 1)
    strip.set_ylim(0, 1)
    strip.axis("off")
    strip.add_patch(
        FancyBboxPatch(
            (0, 0),
            1,
            1,
            boxstyle="round,pad=0.01,rounding_size=0.035",
            facecolor="white",
            edgecolor="#C9CED6",
            linewidth=1.0,
        )
    )
    strip.text(
        0.028,
        0.68,
        "Actual directed\nbackground flows",
        color=TEXT_COLOR,
        fontsize=10.2,
        fontweight="bold",
        va="center",
    )
    strip.text(
        0.028,
        0.20,
        "H level also changes the offered rate per flow.",
        color=MUTED_TEXT_COLOR,
        fontsize=7.7,
        va="center",
    )

    start_x = 0.255
    gap = 0.142
    for index, (scenario, count) in enumerate(SCENARIOS):
        x = start_x + index * gap
        strip.add_patch(
            FancyBboxPatch(
                (x - 0.055, 0.27),
                0.11,
                0.52,
                boxstyle="round,pad=0.012,rounding_size=0.035",
                facecolor=(
                    "#FFF6DF" if scenario in {"H40", "H60"} else "#F3F1FB"
                ),
                edgecolor=(
                    CORRIDOR_COLOR
                    if scenario in {"H40", "H60"}
                    else REGION_COLOR
                ),
                linewidth=0.9,
            )
        )
        strip.text(
            x,
            0.62,
            scenario,
            color=TEXT_COLOR,
            fontsize=9.8,
            fontweight="bold",
            ha="center",
            va="center",
        )
        strip.text(
            x,
            0.39,
            "%d flows" % count,
            color=MUTED_TEXT_COLOR,
            fontsize=8.1,
            ha="center",
            va="center",
        )
    strip.text(
        0.965,
        0.10,
        "Five pairs shown = 10 directed flows · representative paths at t=0",
        color=MUTED_TEXT_COLOR,
        fontsize=7.5,
        ha="right",
        va="center",
    )


def build_figure():
    network, positions, focus_path, background_paths = replay_routes()
    shared_trace = shared_background_trace(focus_path, background_paths)

    # The target middle-ISL trace excludes the first and last access satellites.
    target_corridor_trace = focus_path[2:-2]

    fig = plt.figure(figsize=(18, 10.125), facecolor="#F7F8FA")
    ax = fig.add_axes(
        [0.012, 0.145, 0.976, 0.765],
        projection=ccrs.Robinson(central_longitude=20),
    )
    add_map_background(ax)
    add_concentration_region(ax)

    # Corridor halo below all traffic paths.
    draw_route(
        ax,
        target_corridor_trace,
        positions,
        color=CORRIDOR_COLOR,
        linewidth=13.5,
        alpha=0.25,
        zorder=3,
    )
    draw_route(
        ax,
        target_corridor_trace,
        positions,
        color=CORRIDOR_COLOR,
        linewidth=5.7,
        alpha=0.72,
        zorder=3.1,
    )

    # Actual representative Baseline paths. Repeated shared edges darken
    # naturally, making the overlap visible without artificial offsets.
    for _, path, source, destination in background_paths:
        draw_route(
            ax,
            path,
            positions,
            color=BACKGROUND_COLOR,
            linewidth=2.5,
            alpha=0.40,
            zorder=4,
        )
        add_endpoint(
            ax,
            source,
            positions,
            color=BACKGROUND_COLOR,
            size=30,
            zorder=6,
        )
        add_endpoint(
            ax,
            destination,
            positions,
            color=BACKGROUND_COLOR,
            size=30,
            zorder=6,
        )

    # A teal outer stroke plus red center line makes simultaneous traffic on
    # the common corridor explicit even where paths are exactly coincident.
    draw_route(
        ax,
        shared_trace,
        positions,
        color=BACKGROUND_COLOR,
        linewidth=6.0,
        alpha=0.63,
        zorder=5,
    )
    draw_route(
        ax,
        focus_path,
        positions,
        color="white",
        linewidth=4.7,
        alpha=0.92,
        zorder=5.4,
    )
    draw_route(
        ax,
        focus_path,
        positions,
        color=FOCUS_COLOR,
        linewidth=2.8,
        alpha=0.98,
        zorder=5.5,
    )

    # Corridor satellite nodes are schematic markers placed at the actual t=0
    # sub-satellite positions.
    corridor_lons, corridor_lats = coordinates(
        target_corridor_trace,
        positions,
    )
    ax.scatter(
        corridor_lons,
        corridor_lats,
        s=24,
        facecolor="white",
        edgecolor=CORRIDOR_COLOR,
        linewidth=1.15,
        transform=ccrs.PlateCarree(),
        zorder=7,
    )

    add_endpoint(
        ax,
        754,
        positions,
        color=FOCUS_COLOR,
        size=58,
        zorder=8,
    )
    add_endpoint(
        ax,
        785,
        positions,
        color=FOCUS_COLOR,
        size=58,
        zorder=8,
    )

    add_map_annotations(ax, positions)
    add_selection_inset(fig)
    add_legend(ax)
    add_scenario_strip(fig)

    fig.text(
        0.5,
        0.965,
        "UDP-PDR Hotspot Traffic Scenario",
        ha="center",
        va="center",
        fontsize=22,
        fontweight="bold",
        color=TEXT_COLOR,
    )
    fig.text(
        0.5,
        0.932,
        (
            "Five highest-ranked background OD pairs shared by "
            "H40, H60, H80, H90, and H100+"
        ),
        ha="center",
        va="center",
        fontsize=10.2,
        color=MUTED_TEXT_COLOR,
    )
    fig.text(
        0.988,
        0.147,
        (
            "Schematic line widths and concentration boundary · "
            "routes replayed from the H80 Baseline t=0 forwarding state"
        ),
        ha="right",
        va="bottom",
        fontsize=7.2,
        color=MUTED_TEXT_COLOR,
    )

    return fig, network, focus_path, background_paths, shared_trace


def main():
    fig, network, focus_path, background_paths, shared_trace = build_figure()
    output_stem = SCRIPT_PATH.with_name("udp_pdr_hotspot_traffic_scenario")
    outputs = (
        output_stem.with_suffix(".png"),
        output_stem.with_suffix(".svg"),
        output_stem.with_suffix(".pdf"),
    )
    fig.savefig(outputs[0], dpi=220, facecolor=fig.get_facecolor())
    fig.savefig(outputs[1], facecolor=fig.get_facecolor())
    fig.savefig(outputs[2], facecolor=fig.get_facecolor())
    plt.close(fig)

    print("Focus path: %s" % " -> ".join(map(str, focus_path)))
    for label, path, _, _ in background_paths:
        print("%s: %s" % (label, " -> ".join(map(str, path))))
    print("Shared trace: %s" % " -> ".join(map(str, shared_trace)))
    for output in outputs:
        print("Wrote %s" % output)


if __name__ == "__main__":
    main()
