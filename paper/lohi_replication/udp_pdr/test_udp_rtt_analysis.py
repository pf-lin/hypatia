import os
import tempfile
import unittest

import pandas as pd

from dynamic_run_list import build_arg_parser
from udp_rtt_analysis import (
    build_sample_times_ns,
    build_summary,
    path_queue_delay_s,
    scan_queue_history,
)


class UdpRttAnalysisTest(unittest.TestCase):
    def test_default_rtt_sampling_is_every_100_ms(self):
        args = build_arg_parser("test").parse_args([])
        self.assertEqual(args.rtt_sample_interval_s, 0.1)

        times = build_sample_times_ns(60, 58, args.rtt_sample_interval_s)
        self.assertEqual(len(times), 581)
        self.assertEqual(times[:3], [0, 100_000_000, 200_000_000])
        self.assertEqual(times[-1], 58_000_000_000)

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


if __name__ == "__main__":
    unittest.main()
