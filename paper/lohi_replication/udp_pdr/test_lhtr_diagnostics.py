import csv
import os
import tempfile
import unittest

from analyze_packet_delivery import (
    LHTR_DIAGNOSTIC_COLUMNS,
    collect_lhtr_diagnostic_summaries,
)


class LhtrDiagnosticsAnalysisTest(unittest.TestCase):
    def test_missing_diagnostics_returns_empty_stable_frames(self):
        with tempfile.TemporaryDirectory() as algorithm_run_dir:
            summaries = collect_lhtr_diagnostic_summaries(
                algorithm_run_dir,
                "run_test",
                "algorithm_lhtr",
            )

        self.assertEqual(set(LHTR_DIAGNOSTIC_COLUMNS), set(summaries))
        for filename, columns in LHTR_DIAGNOSTIC_COLUMNS.items():
            self.assertEqual(0, len(summaries[filename]))
            self.assertEqual(
                ["run_name", "algorithm"] + columns,
                list(summaries[filename].columns),
            )

    def test_existing_summary_is_tagged_for_comparison_output(self):
        filename = "lhtr_br_sbr_summary.csv"
        columns = LHTR_DIAGNOSTIC_COLUMNS[filename]
        with tempfile.TemporaryDirectory() as algorithm_run_dir:
            diagnostics_dir = os.path.join(
                algorithm_run_dir,
                "lhtr_diagnostics",
            )
            os.makedirs(diagnostics_dir)
            row = {column: "" for column in columns}
            row.update({
                "time_ns": 100000000,
                "br_selected_count": 12,
                "sbr_selected_count": 3,
            })
            with open(
                os.path.join(diagnostics_dir, filename),
                "w",
                newline="",
                encoding="utf-8",
            ) as f_out:
                writer = csv.DictWriter(f_out, fieldnames=columns)
                writer.writeheader()
                writer.writerow(row)

            summaries = collect_lhtr_diagnostic_summaries(
                algorithm_run_dir,
                "run_test",
                "algorithm_lhtr",
            )

        frame = summaries[filename]
        self.assertEqual(1, len(frame))
        self.assertEqual("run_test", frame.iloc[0]["run_name"])
        self.assertEqual("algorithm_lhtr", frame.iloc[0]["algorithm"])
        self.assertEqual(3, frame.iloc[0]["sbr_selected_count"])


if __name__ == "__main__":
    unittest.main()
