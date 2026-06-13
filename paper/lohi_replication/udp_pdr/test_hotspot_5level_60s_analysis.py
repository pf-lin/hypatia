import unittest

import pandas as pd

from analyze_hotspot_5level_60s_formal import (
    ALGORITHM_ORDER,
    build_output_catalog,
    build_plot_manifest,
    build_rankings,
    parse_flow_ids,
    safe_ratio,
    scenario_order,
)


class HotspotFiveLevelAnalysisTest(unittest.TestCase):

    def test_safe_ratio_handles_zero(self):
        self.assertEqual(safe_ratio(10, 0), 0.0)
        self.assertAlmostEqual(safe_ratio(1, 4), 0.25)

    def test_parse_flow_ids(self):
        self.assertEqual(parse_flow_ids("0;1;7"), {0, 1, 7})
        self.assertEqual(parse_flow_ids(""), set())

    def test_rankings_use_documented_directions(self):
        rows = []
        pdr_values = [0.4, 0.9, 0.6, 0.8]
        mean_values = [400, 100, 300, 200]
        p95_values = [450, 150, 350, 250]
        for algorithm, pdr, mean, p95 in zip(
            ALGORITHM_ORDER,
            pdr_values,
            mean_values,
            p95_values,
        ):
            rows.append(
                {
                    "scenario": "H40",
                    "hotspot_label": "Hotspot-Light",
                    "algorithm": algorithm,
                    "algorithm_label": algorithm,
                    "aggregate_pdr": pdr,
                    "mean_rtt_ms": mean,
                    "p95_rtt_ms": p95,
                }
            )
        rankings = build_rankings(pd.DataFrame(rows))
        queue = rankings[
            rankings["algorithm"] == "algorithm_queue_aware_over_isls"
        ].iloc[0]
        self.assertEqual(queue["aggregate_pdr_rank"], 1)
        self.assertEqual(queue["mean_rtt_rank"], 1)
        self.assertEqual(queue["p95_rtt_rank"], 1)
        self.assertEqual(queue["composite_rank"], 1)

    def test_output_catalog_classifies_figures_and_tables(self):
        plots = build_plot_manifest()
        catalog = build_output_catalog(plots)
        self.assertEqual(set(catalog["tier"]), {"A", "B", "C"})
        self.assertIn("figure", set(catalog["output_type"]))
        self.assertIn("table", set(catalog["output_type"]))
        self.assertIn(
            "hotspot_5level_cross_level_summary.csv",
            set(catalog["filename"]),
        )

    def test_partial_scenario_order_and_catalog_metadata(self):
        summary = pd.DataFrame(
            [
                {"scenario": "H100+"},
                {"scenario": "H80"},
            ]
        )
        self.assertEqual(scenario_order(summary), ["H80", "H100+"])
        catalog = build_output_catalog(
            build_plot_manifest(),
            simulation_end_time_s=200,
            traffic_stop_time_s=198,
            scenario_set="H80,H100+",
        )
        self.assertEqual(set(catalog["duration_label"]), {"200s"})
        self.assertEqual(set(catalog["scenario_set"]), {"H80,H100+"})


if __name__ == "__main__":
    unittest.main()
