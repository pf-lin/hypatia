import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_hotspot_5level_60s_formal import (
    ALGORITHMS,
    SCENARIOS,
    common_args,
    formal_metadata,
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
        self.assertEqual(common[-4:], ALGORITHMS)
        self.assertIn("--enable-rtt-analysis", step3)
        self.assertIn("--enable-route-visualization", step3)
        self.assertIn("0,30,58", step3)
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
