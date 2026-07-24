import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.path import Path
from matplotlib.transforms import IdentityTransform

from dynamic_run_list import build_arg_parser
from udp_rtt_analysis import (
    _ground_station_label,
    _rendered_route_segments,
    _save_route_figure,
    build_sample_times_ns,
    build_summary,
    calculate_zoomed_route_extent,
    ensure_route_plot_directories,
    path_queue_delay_s,
    plot_connection,
    resolve_route_plot_variants,
    route_plot_directories,
    scan_queue_history,
)


class UdpRttAnalysisTest(unittest.TestCase):
    def test_default_rtt_sampling_is_every_100_ms(self):
        args = build_arg_parser("test").parse_args([])
        self.assertEqual(args.rtt_sample_interval_s, 0.1)
        self.assertEqual(args.route_plot_variants, "all")
        self.assertEqual(
            resolve_route_plot_variants(args.route_plot_variants),
            ("original", "world_map", "world_map_zoomed"),
        )
        self.assertEqual(
            resolve_route_plot_variants("both"),
            ("original", "world_map"),
        )

        times = build_sample_times_ns(60, 58, args.rtt_sample_interval_s)
        self.assertEqual(len(times), 581)
        self.assertEqual(times[:3], [0, 100_000_000, 200_000_000])
        self.assertEqual(times[-1], 58_000_000_000)

    def test_all_route_variants_create_three_sibling_directories(self):
        with tempfile.TemporaryDirectory() as comparison_dir:
            directories = route_plot_directories(
                comparison_dir,
                resolve_route_plot_variants("all"),
            )
            ensure_route_plot_directories(directories)

            self.assertEqual(
                set(directories),
                {"original", "world_map", "world_map_zoomed"},
            )
            self.assertEqual(
                {os.path.basename(path) for path in directories.values()},
                {
                    "graphical_routes",
                    "graphical_routes_world_map",
                    "graphical_routes_world_map_zoomed",
                },
            )
            self.assertTrue(
                all(os.path.isdir(path) for path in directories.values())
            )

    def test_interval_sampling_includes_traffic_stop_time(self):
        self.assertEqual(
            build_sample_times_ns(60, 58, 5),
            [
                0,
                5_000_000_000,
                10_000_000_000,
                15_000_000_000,
                20_000_000_000,
                25_000_000_000,
                30_000_000_000,
                35_000_000_000,
                40_000_000_000,
                45_000_000_000,
                50_000_000_000,
                55_000_000_000,
                58_000_000_000,
            ],
        )

    def test_queue_lookup_uses_latest_completed_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "isl_queue_byte_history.csv")
            with open(path, "w") as f_out:
                f_out.write("1,2,0,99,100\n")
                f_out.write("1,2,100,199,200\n")
            index = scan_queue_history(path, "ISL", {"ISL:1->2"})
            config = {"isl_data_rate_megabit_per_s": "10"}

            before_first = path_queue_delay_s(
                ("ISL:1->2",),
                98,
                config,
                1500,
                index,
                {},
            )
            at_second = path_queue_delay_s(
                ("ISL:1->2",),
                199,
                config,
                1500,
                index,
                {},
            )

            self.assertEqual(before_first["missing"], 1)
            self.assertAlmostEqual(at_second["delay_s"], 200 * 8 / 10e6)
            self.assertEqual(at_second["sources"], {"queue_bytes"})

    def test_packet_fallback_and_missing_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "gsl_queue_pkt_history.csv")
            with open(path, "w") as f_out:
                f_out.write("754,-1,0,99,2\n")
            packet_index = scan_queue_history(
                path,
                "GSL",
                {"GSL:754->-1"},
            )
            result = path_queue_delay_s(
                ("GSL:754->-1", "ISL:1->2"),
                100,
                {
                    "gsl_data_rate_megabit_per_s": "10",
                    "isl_data_rate_megabit_per_s": "10",
                },
                1500,
                {},
                packet_index,
            )
            self.assertAlmostEqual(result["delay_s"], 2 * 1500 * 8 / 10e6)
            self.assertEqual(result["found"], 1)
            self.assertEqual(result["missing"], 1)
            self.assertEqual(
                result["sources"],
                {"queue_packets_fallback", "missing_queue_data"},
            )

    def test_summary_counts_replay_failures_as_missing(self):
        rows = [
            {
                "algorithm": "baseline",
                "direction": "1_to_2",
                "path_replay_status": "success",
                "propagation_only_rtt_ms": 10.0,
                "queue_aware_rtt_ms": 12.0,
                "forward_queue_delay_ms": 1.0,
                "reverse_queue_delay_ms": 1.0,
            },
            {
                "algorithm": "baseline",
                "direction": "1_to_2",
                "path_replay_status": "forward:missing_entry;reverse:success",
                "propagation_only_rtt_ms": float("nan"),
                "queue_aware_rtt_ms": float("nan"),
                "forward_queue_delay_ms": float("nan"),
                "reverse_queue_delay_ms": 0.0,
            },
        ]
        summary = build_summary(pd.DataFrame(rows))
        self.assertEqual(int(summary.iloc[0]["valid_sample_count"]), 1)
        self.assertEqual(int(summary.iloc[0]["missing_sample_count"]), 1)
        self.assertEqual(summary.iloc[0]["mean_queue_aware_rtt_ms"], 12.0)

    def test_world_map_only_setup_does_not_touch_existing_routes(self):
        with tempfile.TemporaryDirectory() as comparison_dir:
            original_dir = os.path.join(comparison_dir, "graphical_routes")
            world_map_dir = os.path.join(
                comparison_dir,
                "graphical_routes_world_map",
            )
            os.makedirs(original_dir)
            os.makedirs(world_map_dir)
            filename = "algorithm_lhtr_focus_forward_path_t0s.png"
            original_path = os.path.join(original_dir, filename)
            world_map_path = os.path.join(world_map_dir, filename)
            with open(original_path, "wb") as f_out:
                f_out.write(b"original")
            with open(world_map_path, "wb") as f_out:
                f_out.write(b"world map")

            directories = route_plot_directories(
                comparison_dir,
                resolve_route_plot_variants("world_map"),
            )
            ensure_route_plot_directories(directories)

            self.assertTrue(os.path.exists(original_path))
            self.assertTrue(os.path.exists(world_map_path))

    def test_zoomed_world_map_only_setup_does_not_touch_existing_routes(self):
        with tempfile.TemporaryDirectory() as comparison_dir:
            original_dir = os.path.join(comparison_dir, "graphical_routes")
            world_map_dir = os.path.join(
                comparison_dir,
                "graphical_routes_world_map",
            )
            zoomed_dir = os.path.join(
                comparison_dir,
                "graphical_routes_world_map_zoomed",
            )
            os.makedirs(original_dir)
            os.makedirs(world_map_dir)
            filename = "algorithm_lhtr_focus_forward_path_t0s.png"
            original_path = os.path.join(original_dir, filename)
            world_map_path = os.path.join(world_map_dir, filename)
            zoomed_path = os.path.join(zoomed_dir, filename)
            with open(original_path, "wb") as f_out:
                f_out.write(b"original")
            with open(world_map_path, "wb") as f_out:
                f_out.write(b"world map")

            directories = route_plot_directories(
                comparison_dir,
                resolve_route_plot_variants("world_map_zoomed"),
            )
            self.assertEqual(
                directories,
                {"world_map_zoomed": zoomed_dir},
            )
            ensure_route_plot_directories(directories)

            with open(original_path, "rb") as f_in:
                self.assertEqual(f_in.read(), b"original")
            with open(world_map_path, "rb") as f_in:
                self.assertEqual(f_in.read(), b"world map")
            self.assertTrue(os.path.isdir(zoomed_dir))
            self.assertFalse(os.path.exists(zoomed_path))

    def test_zoomed_extent_frames_path_region_with_geographic_padding(self):
        positions = [
            (-26.202, 28.044),
            (35.886, 80.0),
            (33.606, 130.418),
        ]
        extent = calculate_zoomed_route_extent(
            [([0, 1, 2], "red", "Forward path", "-")],
            positions,
        )
        center, west, east, south, north = extent

        self.assertAlmostEqual(center, 79.231, places=3)
        self.assertLess(center + west, -15.0)
        self.assertGreater(center + east, 170.0)
        self.assertLess(south, -45.0)
        self.assertGreater(north, 55.0)
        self.assertLess(east - west, 250.0)
        self.assertLess(north - south, 140.0)

    def test_zoomed_extent_uses_short_arc_across_dateline(self):
        positions = [(10.0, 170.0), (15.0, -175.0)]
        center, west, east, south, north = calculate_zoomed_route_extent(
            [([0, 1], "red", "Forward path", "-")],
            positions,
        )

        self.assertAlmostEqual(center, 177.5)
        self.assertAlmostEqual(east - west, 60.0)
        self.assertLessEqual(west, -7.5)
        self.assertGreaterEqual(east, 7.5)
        self.assertGreaterEqual(north - south, 40.0)

    def test_fukuoka_ground_station_label_is_shortened(self):
        network = SimpleNamespace(
            num_satellites=1,
            ground_stations=[
                {"name": "Kitakyushu-Fukuoka-M.M.A."},
            ],
        )
        self.assertEqual(
            _ground_station_label(network, 1, shorten=True),
            "1: Fukuoka",
        )
        self.assertEqual(
            _ground_station_label(network, 1),
            "1: Kitakyushu-Fukuoka-M.M.A.",
        )

    def test_failed_route_save_preserves_existing_image(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = os.path.join(directory, "route.png")
            with open(output_path, "wb") as f_out:
                f_out.write(b"existing image")
            fig = plt.figure()

            with mock.patch(
                "udp_rtt_analysis._save_figure",
                side_effect=RuntimeError("save failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "save failed"):
                    _save_route_figure(fig, output_path)

            with open(output_path, "rb") as f_in:
                self.assertEqual(f_in.read(), b"existing image")
            self.assertEqual(
                [
                    filename
                    for filename in os.listdir(directory)
                    if filename != "route.png"
                ],
                [],
            )

    def test_dateline_connection_keeps_both_edge_segments(self):
        fig, ax = plt.subplots()
        lines = plot_connection(
            ax,
            179.999,
            10.0,
            -170.0,
            20.0,
            label="path",
        )
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(ax.lines), 2)
        self.assertEqual(
            list(ax.lines[0].get_xdata()),
            [179.999, 180],
        )
        self.assertEqual(
            list(ax.lines[1].get_xdata()),
            [-180, -170.0],
        )
        self.assertEqual(ax.lines[0].get_label(), "path")
        self.assertNotEqual(ax.lines[1].get_label(), "path")
        plt.close(fig)

    def test_rendered_route_segments_do_not_bridge_seam_subpaths(self):
        rendered_path = Path(
            [(0, 0), (1, 1), (9, 9), (10, 10)],
            [Path.MOVETO, Path.LINETO, Path.MOVETO, Path.LINETO],
        )
        line = SimpleNamespace(
            get_path=lambda: rendered_path,
            get_transform=lambda: IdentityTransform(),
        )

        segments = _rendered_route_segments([line])

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].vertices.tolist(), [[0, 0], [1, 1]])
        self.assertEqual(segments[1].vertices.tolist(), [[9, 9], [10, 10]])


if __name__ == "__main__":
    unittest.main()
