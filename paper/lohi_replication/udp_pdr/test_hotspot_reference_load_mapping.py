import unittest

from analyze_hotspot_reference_load_mapping import hotspot_load_label


class HotspotReferenceLoadMappingTest(unittest.TestCase):
    def test_hotspot_load_bands(self):
        self.assertEqual(hotspot_load_label(49.999), "Hotspot-Light")
        self.assertEqual(hotspot_load_label(50.0), "Hotspot-Moderate")
        self.assertEqual(hotspot_load_label(70.0), "Hotspot-High")
        self.assertEqual(hotspot_load_label(69.999999999), "Hotspot-High")
        self.assertEqual(hotspot_load_label(85.0), "Hotspot-Severe")
        self.assertEqual(hotspot_load_label(100.0), "Hotspot-Overload")


if __name__ == "__main__":
    unittest.main()
