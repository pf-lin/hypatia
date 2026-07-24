import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_hotspot_5level_60s_formal import (
    ALGORITHMS,
    ROUTE_PLOT_DIRECTORIES,
    SCENARIOS,
    common_args,
    default_route_plot_times,
    default_rtt_sample_interval_s,
    duration_label,
    expected_route_plot_filenames,
    formal_metadata,
    output_paths,
    planned_commands,
    run_name_for_scenario,
    selected_scenarios,
)


class HotspotFiveLevelFormalRunnerTest(unittest.TestCase):
    def test_fixed_scenarios_match_formal_candidates(self):
        self.assertEqual(
            [
                (
                    row["scenario_id"],
                    row["load_level"],
                    row["background_flow_count"],
                )
                for row in SCENARIOS
            ],
            [
                ("H40", 1.0, 24),
                ("H60", 1.2, 32),
                ("H80", 1.6, 32),
                ("H90", 2.2, 48),
                ("H100+", 2.8, 48),
            ],
        )

    def test_commands_include_required_formal_controls(self):
        scenario = SCENARIOS[0]
        step1, step2, step3 = planned_commands(scenario, force=True)
        common = common_args(scenario)
        self.assertIn("--force", step1)
        self.assertIn("--lohi-management-mode", common)
        self.assertIn("control_plane_only", common)
        self.assertIn("--isl-data-rate-megabit-per-s", common)
        self.assertIn("--gsl-data-rate-megabit-per-s", common)
        algorithm_start = common.index("--algorithms") + 1
        self.assertEqual(
            common[algorithm_start:algorithm_start + len(ALGORITHMS)],
            ALGORITHMS,
        )
        self.assertIn("--enable-rtt-analysis", step3)
        self.assertIn("--enable-route-visualization", step3)
        self.assertIn("0,30,58", step3)
        self.assertIn("--route-plot-variants", step3)
        variant_index = step3.index("--route-plot-variants") + 1
        self.assertEqual(step3[variant_index], "all")
        self.assertEqual(
            ROUTE_PLOT_DIRECTORIES,
            (
                "graphical_routes",
                "graphical_routes_world_map",
                "graphical_routes_world_map_zoomed",
            ),
        )
        self.assertNotIn("--force", step2)

    def test_run_identity_and_metadata_are_formal_specific(self):
        scenario = SCENARIOS[0]
        run_name = run_name_for_scenario(scenario)
        self.assertIn("src754_dst785", run_name)
        self.assertIn("sim60s_stop58s", run_name)
        self.assertIn("isl10mbps_gsl100mbps", run_name)
        self.assertIn("lohi_mgmt_control_plane_only", run_name)
        metadata = formal_metadata(scenario)
        self.assertEqual(metadata["scenario_id"], "H40")
        self.assertEqual(metadata["formal_duration_s"], 60)
        self.assertEqual(metadata["formal_traffic_stop_s"], 58)
        self.assertTrue(metadata["lhtr_diagnostics_enabled"])
        self.assertTrue(metadata["rtt_analysis_enabled"])
        self.assertTrue(metadata["route_visualization_enabled"])
        self.assertEqual(
            metadata["route_plot_variants"],
            ["original", "world_map", "world_map_zoomed"],
        )

    def test_200s_defaults_use_two_second_drain_and_bounded_visualization(self):
        scenario = SCENARIOS[2]
        step1, _, step3 = planned_commands(
            scenario,
            force=False,
            simulation_end_time_s=200,
            traffic_stop_time_s=198,
        )
        self.assertIn("200", step1)
        self.assertIn("198", step1)
        self.assertIn("1", step3)
        self.assertIn("0,30,60,90,120,150,180,198", step3)
        self.assertEqual(default_rtt_sample_interval_s(200), 1.0)
        self.assertEqual(
            default_route_plot_times(198),
            [0.0, 30.0, 60.0, 90.0, 120.0, 150.0, 180.0, 198.0],
        )
        self.assertEqual(
            expected_route_plot_filenames(
                "algorithm_lhtr",
                [0.0, 30.5],
            ),
            {
                "algorithm_lhtr_focus_forward_path_t0s.png",
                "algorithm_lhtr_focus_reverse_path_t0s.png",
                "algorithm_lhtr_focus_round_trip_path_t0s.png",
                "algorithm_lhtr_focus_forward_path_t30p5s.png",
                "algorithm_lhtr_focus_reverse_path_t30p5s.png",
                "algorithm_lhtr_focus_round_trip_path_t30p5s.png",
            },
        )

    def test_duration_aware_output_paths_share_normal_200s_scenarios(self):
        paths = output_paths(200, 198)
        self.assertEqual(duration_label(200, 198), "200s")
        self.assertTrue(
            paths["report_dir"].endswith("hotspot_5level_200s_formal")
        )
        self.assertTrue(
            paths["manifest_path"].endswith(
                "hotspot_5level_200s_formal_manifest.csv"
            )
        )
        self.assertEqual(duration_label(200, 195), "200s_stop195s")

    def test_scenario_filter_accepts_comma_and_space_forms(self):
        selected = selected_scenarios(["H40,H80", "H100+"])
        self.assertEqual(
            [scenario["scenario_id"] for scenario in selected],
            ["H40", "H80", "H100+"],
        )

    def test_aggregate_only_is_exposed_by_cli(self):
        source = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "run_hotspot_5level_60s_formal.py",
        )
        with open(source) as f_in:
            self.assertIn('"--aggregate-only"', f_in.read())


if __name__ == "__main__":
    unittest.main()
