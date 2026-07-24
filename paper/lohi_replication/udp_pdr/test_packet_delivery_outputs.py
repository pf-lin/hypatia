import os
import tempfile
import unittest

from packet_delivery_outputs import (
    archive_flat_outputs,
    output_path,
    write_deprecated_notes,
    write_output_manifest,
    write_result_guide,
)


class PacketDeliveryOutputsTest(unittest.TestCase):
    def test_standard_paths_classify_core_diagnostic_and_legacy(self):
        comparison_dir = "/tmp/comparison_packet_delivery"
        self.assertEqual(
            output_path(comparison_dir, "summary_by_algorithm.csv"),
            os.path.join(comparison_dir, "core", "summary_by_algorithm.csv"),
        )
        self.assertEqual(
            output_path(comparison_dir, "physical_link_drops.csv"),
            os.path.join(comparison_dir, "diagnostics", "physical_link_drops.csv"),
        )
        self.assertEqual(
            output_path(comparison_dir, "lhtr_br_sbr_summary.csv"),
            os.path.join(
                comparison_dir,
                "diagnostics",
                "lhtr_br_sbr_summary.csv",
            ),
        )
        self.assertEqual(
            output_path(comparison_dir, "link_drops.csv"),
            os.path.join(comparison_dir, "legacy", "link_drops.csv"),
        )
        self.assertEqual(
            output_path(comparison_dir, "udp_rtt_summary_by_algorithm.csv"),
            os.path.join(
                comparison_dir,
                "core",
                "udp_rtt_summary_by_algorithm.csv",
            ),
        )
        self.assertEqual(
            output_path(comparison_dir, "udp_focus_rtt_timeseries.csv"),
            os.path.join(
                comparison_dir,
                "diagnostics",
                "udp_focus_rtt_timeseries.csv",
            ),
        )

    def test_archive_flat_outputs_preserves_duplicates(self):
        with tempfile.TemporaryDirectory() as comparison_dir:
            filenames = [
                "summary_by_algorithm.csv",
                "physical_link_drops.csv",
                "loss_attribution_breakdown_v2.csv",
                "aggregate_pdr_bg_flow_count_24.png",
            ]
            for filename in filenames:
                with open(os.path.join(comparison_dir, filename), "w") as f_out:
                    f_out.write(filename)

            archive_flat_outputs(comparison_dir)

            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        comparison_dir,
                        "core",
                        "summary_by_algorithm.csv",
                    )
                )
            )
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        comparison_dir,
                        "diagnostics",
                        "physical_link_drops.csv",
                    )
                )
            )
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        comparison_dir,
                        "legacy",
                        "loss_attribution_breakdown_v2.csv",
                    )
                )
            )
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        comparison_dir,
                        "legacy",
                        "duplicates",
                        "aggregate_pdr_bg_flow_count_24.png",
                    )
                )
            )

    def test_manifest_and_guides_are_created(self):
        with tempfile.TemporaryDirectory() as comparison_dir:
            original_dir = os.path.join(comparison_dir, "graphical_routes")
            world_map_dir = os.path.join(
                comparison_dir,
                "graphical_routes_world_map",
            )
            os.makedirs(original_dir)
            os.makedirs(world_map_dir)
            original_filename = "algorithm_lhtr_focus_forward_path_t0s.png"
            world_map_filename = "algorithm_lhtr_focus_reverse_path_t0s.png"
            with open(
                os.path.join(original_dir, original_filename),
                "wb",
            ) as f_out:
                f_out.write(b"original")
            with open(
                os.path.join(world_map_dir, world_map_filename),
                "wb",
            ) as f_out:
                f_out.write(b"world map")

            write_result_guide(comparison_dir)
            write_deprecated_notes(comparison_dir)
            manifest_path = write_output_manifest(comparison_dir)

            self.assertTrue(os.path.exists(manifest_path))
            self.assertTrue(os.path.exists(os.path.join(comparison_dir, "README.md")))
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        comparison_dir,
                        "legacy",
                        "deprecated_notes.md",
                    )
                )
            )
            with open(manifest_path) as f_in:
                manifest = f_in.read()
            self.assertIn("core/loss_attribution_breakdown_v3.csv", manifest)
            self.assertIn("large_optional", manifest)
            self.assertIn("deprecated", manifest)
            self.assertIn(
                "graphical_routes/" + original_filename,
                manifest,
            )
            self.assertIn(
                "graphical_routes_world_map/" + world_map_filename,
                manifest,
            )


if __name__ == "__main__":
    unittest.main()
