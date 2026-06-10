import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dynamic_run_list import (
    focus_pair_metadata,
    get_udp_pdr_run_list,
    resolve_existing_run,
    run_name_for,
    validate_focus_pair,
)


class DynamicRunListFocusPairTest(unittest.TestCase):
    def test_custom_focus_pair_is_part_of_run_identity_and_metadata(self):
        runs = get_udp_pdr_run_list(
            selected_mode="core_isl_hotspot_specific",
            load_levels=[1.4],
            algorithms=["algorithm_free_one_only_over_isls"],
            background_flow_count_override=[24],
            src_node_id_override=754,
            dst_node_id_override=785,
        )
        self.assertEqual(len(runs), 1)
        run = runs[0]
        self.assertEqual(run["src_node_id"], 754)
        self.assertEqual(run["dst_node_id"], 785)
        self.assertEqual(run["focus_pair_tag"], "src754_dst785")
        self.assertIn("src754_dst785", run["name"])
        self.assertEqual(run["focus_src_name_if_available"], "Johannesburg")
        self.assertIn("Fukuoka", run["focus_dst_name_if_available"])
        self.assertEqual(run["focus_flow_direction_count"], 2)

    def test_focus_pair_validation_rejects_same_or_non_ground_station_nodes(self):
        with self.assertRaisesRegex(ValueError, "must differ"):
            validate_focus_pair(754, 754)
        with self.assertRaisesRegex(ValueError, "inclusive range 720-819"):
            validate_focus_pair(719, 785)
        with self.assertRaisesRegex(ValueError, "inclusive range 720-819"):
            validate_focus_pair(754, 820)

    def test_default_pair_keeps_legacy_folder_read_compatibility(self):
        runs = get_udp_pdr_run_list(
            selected_mode="focus_only",
            load_levels=[1.0],
            algorithms=["algorithm_free_one_only_over_isls"],
        )
        run = runs[0]
        self.assertIn("src738_dst793", run["name"])
        with tempfile.TemporaryDirectory() as runs_root:
            os.makedirs(os.path.join(runs_root, run["legacy_name"]))
            resolved = resolve_existing_run(run, runs_root)
        self.assertEqual(resolved["name"], run["legacy_name"])
        self.assertTrue(resolved["using_legacy_run_name"])

    def test_custom_pair_never_falls_back_to_untagged_legacy_folder(self):
        runs = get_udp_pdr_run_list(
            selected_mode="focus_only",
            load_levels=[1.0],
            algorithms=["algorithm_free_one_only_over_isls"],
            src_node_id_override=754,
            dst_node_id_override=785,
        )
        run = runs[0]
        with tempfile.TemporaryDirectory() as runs_root:
            os.makedirs(os.path.join(runs_root, run["legacy_name"]))
            resolved = resolve_existing_run(run, runs_root)
        self.assertEqual(resolved["name"], run["name"])
        self.assertNotIn("using_legacy_run_name", resolved)

    def test_helpers_expose_expected_tag_and_names(self):
        self.assertEqual(
            run_name_for(
                "core_isl_hotspot_specific",
                1.4,
                24,
                754,
                785,
            ),
            (
                "run_core_isl_hotspot_specific_src754_dst785_load_1p4x_"
                "bg_flow_count_24_oneweb_isls_moving_udp_pdr"
            ),
        )
        metadata = focus_pair_metadata(738, 793)
        self.assertEqual(metadata["focus_src_name_if_available"], "Rio-de-Janeiro")
        self.assertIn("Saint-Petersburg", metadata["focus_dst_name_if_available"])


if __name__ == "__main__":
    unittest.main()
