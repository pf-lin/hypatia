import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import analyze_packet_delivery
from analyze_packet_delivery import (
    build_queue_saturation_outputs,
    collect_gsl_queue_summary,
)
from loss_attribution_v3 import _read_queue_history


class QueueStreamingAnalysisTest(unittest.TestCase):

    def write_history(self, logs_dir, filename, rows):
        os.makedirs(logs_dir, exist_ok=True)
        path = os.path.join(logs_dir, filename)
        with open(path, "w") as f_out:
            for row in rows:
                f_out.write(",".join(str(value) for value in row) + "\n")
        return path

    def test_gsl_summary_is_aggregated_across_chunks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_dir = os.path.join(tmp_dir, "logs_ns3")
            self.write_history(
                logs_dir,
                "gsl_queue_pkt_history.csv",
                [
                    (1, 2, 0, 10, 0),
                    (1, 2, 10, 20, 5),
                    (3, 4, 0, 10, 9),
                    (1, 2, 20, 30, 7),
                ],
            )
            with patch.object(analyze_packet_delivery, "QUEUE_CSV_CHUNK_ROWS", 2):
                summary = collect_gsl_queue_summary(tmp_dir, "algorithm_test")

        self.assertEqual(summary["max_gsl_queue_pkt"], 9)
        self.assertEqual(summary["nonzero_gsl_queue_samples"], 3)
        self.assertAlmostEqual(summary["mean_gsl_queue_pkt"], 5.25)
        self.assertEqual(summary["top_gsl_queue_links"], "3->4:9;1->2:7")

    def test_saturation_outputs_keep_only_saturated_rows_by_default(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_dir = os.path.join(tmp_dir, "logs_ns3")
            self.write_history(
                logs_dir,
                "isl_queue_pkt_history.csv",
                [
                    (1, 2, 0, 10, 20),
                    (1, 2, 10, 20, 100),
                    (1, 2, 20, 30, 80),
                    (1, 2, 30, 40, 110),
                ],
            )
            flows = pd.DataFrame(
                [
                    {
                        "flow_id": 7,
                        "start_time_ns": 0,
                        "end_time_ns": 40,
                        "lost_packets": 3,
                        "src": 10,
                        "dst": 11,
                    }
                ]
            )
            run = {"queue_size_pkt": 100}
            mapping = {"ISL:1->2": {7}}
            with (
                patch.object(
                    analyze_packet_delivery,
                    "load_interface_flow_maps",
                    return_value=(mapping, {}, {}),
                ),
                patch.object(
                    analyze_packet_delivery,
                    "read_queue_capacity_pkt",
                    side_effect=lambda _run_dir, _run, link_type: (
                        100 if link_type == "ISL" else 50
                    ),
                ),
                patch.object(analyze_packet_delivery, "QUEUE_CSV_CHUNK_ROWS", 2),
            ):
                timeline, congested, isl_flows, gsl_flows = (
                    build_queue_saturation_outputs(
                        tmp_dir,
                        run,
                        "algorithm_test",
                        flows,
                    )
                )

        self.assertEqual(timeline["queue_pkt"].tolist(), [100.0, 110.0])
        self.assertEqual(timeline["estimated_active_lost_flow_count"].tolist(), [1, 1])
        self.assertEqual(isl_flows, {7: {"ISL:1->2"}})
        self.assertEqual(gsl_flows, {})
        self.assertEqual(int(congested.iloc[0]["samples_at_capacity"]), 2)
        self.assertEqual(int(congested.iloc[0]["max_queue_pkt"]), 110)
        self.assertAlmostEqual(float(congested.iloc[0]["mean_queue_pkt"]), 77.5)
        self.assertEqual(int(congested.iloc[0]["first_saturation_time_ns"]), 10)
        self.assertEqual(int(congested.iloc[0]["last_saturation_time_ns"]), 30)

    def test_v3_queue_reader_discards_non_saturated_rows(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.write_history(
                tmp_dir,
                "isl_queue_pkt_history.csv",
                [
                    (1, 2, 0, 10, 99),
                    (1, 2, 10, 20, 100),
                    (2, 3, 20, 30, 101),
                ],
            )
            frame = _read_queue_history(tmp_dir, "ISL", 100)

        self.assertEqual(frame["queue_pkt"].tolist(), [100, 101])
        self.assertEqual(
            frame["interface_key"].tolist(),
            ["ISL:1->2", "ISL:2->3"],
        )
        self.assertTrue(frame["is_at_capacity"].all())


if __name__ == "__main__":
    unittest.main()
