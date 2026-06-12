import unittest

from analyze_isl_load_percentage_mapping import (
    observed_pressure_condition,
    traffic_load_label,
)


class IslLoadPercentageMappingTest(unittest.TestCase):
    def test_traffic_labels_use_offered_percentage_only(self):
        self.assertEqual(traffic_load_label(49.999), "Low")
        self.assertEqual(traffic_load_label(50.0), "Medium")
        self.assertEqual(traffic_load_label(70.0), "High")
        self.assertEqual(traffic_load_label(85.0), "Severe")
        self.assertEqual(traffic_load_label(100.0), "Overload")

    def test_observed_pressure_threshold_precedence(self):
        self.assertEqual(
            observed_pressure_condition(0.50, 0, 0, 0, 0.0),
            "Non-congested",
        )
        self.assertEqual(
            observed_pressure_condition(0.61, 0, 0, 1, 0.0),
            "Localized congestion",
        )
        self.assertEqual(
            observed_pressure_condition(0.61, 1, 0, 1000, 0.0),
            "Sustained congestion",
        )
        self.assertEqual(
            observed_pressure_condition(0.61, 3, 3, 25000, 7.0),
            "Overloaded",
        )


if __name__ == "__main__":
    unittest.main()
