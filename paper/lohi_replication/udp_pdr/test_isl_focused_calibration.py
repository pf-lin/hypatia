import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyze_isl_focused_calibration import (
    BASELINE,
    QUEUE_AWARE,
    _apply_scenario_reference,
    congestion_label,
)


class CongestionLabelTest(unittest.TestCase):
    def test_utilization_bands(self):
        self.assertEqual(congestion_label(0.49, 0), "Light")
        self.assertEqual(congestion_label(0.50, 0), "Moderate")
        self.assertEqual(congestion_label(0.70, 0), "High")
        self.assertEqual(congestion_label(0.85, 0), "Severe")
        self.assertEqual(congestion_label(1.00, 0), "Overload")

    def test_many_saturated_links_force_overload(self):
        self.assertEqual(congestion_label(0.90, 3), "Overload")

    def test_missing_utilization_is_unknown(self):
        self.assertEqual(congestion_label(float("nan"), 0), "Unknown")

    def test_queue_aware_defines_scenario_label(self):
        common = {
            "run_folder": "run_example",
            "target_corridor_utilization_p95": 0.44,
            "target_corridor_utilization_max": 0.55,
            "gsl_bottleneck_flag": "false",
            "dominant_loss_attribution": "no_loss",
            "isl_utilization_source": "measured_throughput",
            "links_over_80pct": 0,
            "links_over_90pct": 0,
            "links_over_100pct": 0,
            "notes": "",
        }
        rows = [
            {
                **common,
                "algorithm": BASELINE,
                "algorithm_congestion_label": "Overload",
                "p95_isl_utilization": 1.0,
                "max_isl_utilization": 1.0,
                "aggregate_pdr": 0.79,
                "lost_packets": 100,
            },
            {
                **common,
                "algorithm": QUEUE_AWARE,
                "algorithm_congestion_label": "Light",
                "p95_isl_utilization": 0.339,
                "max_isl_utilization": 0.55,
                "aggregate_pdr": 1.0,
                "lost_packets": 0,
            },
        ]
        enriched = _apply_scenario_reference(rows)
        for row in enriched:
            self.assertEqual(row["scenario_congestion_label"], "Light")
            self.assertEqual(row["recommended_congestion_label"], "Light")
            self.assertEqual(row["reference_p95_isl_utilization"], 0.339)
            self.assertEqual(row["baseline_congestion_label"], "Overload")
            self.assertEqual(row["safe_for_isl_focused_experiment"], "true")
            self.assertEqual(row["recommended_for_formal"], "true")
        self.assertEqual(
            enriched[0]["algorithm_congestion_label"],
            "Overload",
        )
        self.assertEqual(
            enriched[1]["algorithm_congestion_label"],
            "Light",
        )

    def test_missing_queue_aware_reference_is_unknown(self):
        rows = [
            {
                "run_folder": "run_example",
                "algorithm": BASELINE,
                "algorithm_congestion_label": "Overload",
                "p95_isl_utilization": 1.0,
                "max_isl_utilization": 1.0,
                "target_corridor_utilization_p95": 1.0,
                "target_corridor_utilization_max": 1.0,
                "aggregate_pdr": 0.8,
                "lost_packets": 10,
                "gsl_bottleneck_flag": "false",
                "dominant_loss_attribution": "isl_saturation_associated_loss",
                "isl_utilization_source": "measured_throughput",
                "links_over_80pct": 10,
                "links_over_90pct": 10,
                "links_over_100pct": 10,
                "notes": "",
            }
        ]
        enriched = _apply_scenario_reference(rows)
        self.assertEqual(
            enriched[0]["scenario_congestion_label"],
            "Unknown",
        )
        self.assertEqual(
            enriched[0]["safe_for_isl_focused_experiment"],
            "false",
        )


if __name__ == "__main__":
    unittest.main()
