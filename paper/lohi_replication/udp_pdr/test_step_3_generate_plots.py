import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import step_3_generate_plots


class StepThreeGeneratePlotsTest(unittest.TestCase):
    @staticmethod
    def _fail_rtt(command):
        if any(str(part).endswith("udp_rtt_analysis.py") for part in command):
            raise step_3_generate_plots.subprocess.CalledProcessError(
                7,
                command,
            )

    def test_requested_route_visualization_propagates_rtt_failure(self):
        with mock.patch.object(
            step_3_generate_plots.subprocess,
            "check_call",
            side_effect=self._fail_rtt,
        ), mock.patch.object(
            step_3_generate_plots.sys,
            "argv",
            ["step_3_generate_plots.py", "--enable-route-visualization"],
        ):
            self.assertEqual(step_3_generate_plots.main(), 7)


if __name__ == "__main__":
    unittest.main()
