import csv
import os
import sys
import tempfile
import unittest

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-lohi-diagnostics-test")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(REPO_ROOT, "satgenpy"))

import networkx as nx

from satgen.dynamic_state.algorithm_lohi import (
    LOHI_MANAGER_DIAGNOSTIC_HEADERS,
    VirtualPIDRouterPlaneBlock,
    _write_strict_waypoint_unsupported_diagnostics,
    write_lohi_manager_diagnostics,
)


class LoHiManagerDiagnosticsTest(unittest.TestCase):

    def _read_rows(self, path):
        with open(path, newline="") as f_in:
            return list(csv.DictReader(f_in))

    def test_focus_path_diagnostics_are_written_outside_dynamic_state(self):
        graph = nx.Graph()
        for u, v in [(0, 1), (1, 2), (2, 3), (3, 4)]:
            graph.add_edge(u, v, weight=1000.0, geo_len_m=1000.0)

        router = VirtualPIDRouterPlaneBlock()
        router.pid_of_sat = {0: 0, 1: 0, 2: 0, 3: 1, 4: 1}
        router.pid_members = {0: {0, 1, 2}, 1: {3, 4}}
        router.pid_mgmt_sat = {0: 1, 1: 3}

        fstate = {
            (5, 6): (0, 0, 0),
            (0, 6): (1, 0, 0),
            (1, 6): (2, 0, 0),
            (2, 6): (3, 0, 0),
            (3, 6): (4, 0, 0),
            (4, 6): (6, 0, 0),
        }
        decisions = {
            (0, 6): {
                "u_border": 2,
                "v_border": 3,
                "decision_scope": "manager_assisted_border_selection",
                "notes": "test decision",
            }
        }

        with tempfile.TemporaryDirectory() as run_dir:
            dynamic_state_dir = os.path.join(run_dir, "dynamic_state")
            os.makedirs(dynamic_state_dir)
            write_lohi_manager_diagnostics(
                dynamic_state_dir,
                0,
                "control_plane_only",
                [(5, 6)],
                fstate,
                graph,
                router,
                decisions,
                num_sats=5,
                num_nodes=7,
            )

            diagnostics_dir = os.path.join(
                run_dir,
                "lohi_manager_diagnostics",
            )
            self.assertTrue(os.path.isdir(diagnostics_dir))
            self.assertFalse(
                os.path.exists(
                    os.path.join(dynamic_state_dir, "lohi_manager_mode_summary.csv")
                )
            )
            for filename in LOHI_MANAGER_DIAGNOSTIC_HEADERS:
                self.assertTrue(os.path.exists(os.path.join(diagnostics_dir, filename)))

            summary = self._read_rows(
                os.path.join(diagnostics_dir, "lohi_manager_mode_summary.csv")
            )
            self.assertEqual(summary[0]["management_mode"], "control_plane_only")
            self.assertEqual(
                summary[0]["decision_scope"],
                "manager_assisted_border_selection",
            )
            self.assertEqual(summary[0]["physical_path_contains_manager"], "True")

            compliance = self._read_rows(
                os.path.join(
                    diagnostics_dir,
                    "lohi_manager_waypoint_compliance.csv",
                )
            )
            self.assertEqual(
                compliance[0]["compliance_status"],
                "NOT_APPLICABLE_CONTROL_PLANE_ONLY",
            )

    def test_strict_mode_writes_fail_closed_diagnostics(self):
        with tempfile.TemporaryDirectory() as run_dir:
            dynamic_state_dir = os.path.join(run_dir, "dynamic_state")
            os.makedirs(dynamic_state_dir)
            _write_strict_waypoint_unsupported_diagnostics(
                dynamic_state_dir,
                0,
            )
            rows = self._read_rows(
                os.path.join(
                    run_dir,
                    "lohi_manager_diagnostics",
                    "lohi_manager_waypoint_compliance.csv",
                )
            )
            self.assertEqual(
                rows[0]["compliance_status"],
                "FAIL_UNSUPPORTED_FORWARDING_MODEL",
            )
            self.assertIn("waypoint phase", rows[0]["failure_reason"])


if __name__ == "__main__":
    unittest.main()
