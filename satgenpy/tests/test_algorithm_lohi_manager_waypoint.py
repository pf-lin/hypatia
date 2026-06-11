import os
import sys
import unittest

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-lohi-manager-test")
sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
)

import networkx as nx

from satgen.dynamic_state.algorithm_lohi import (
    BorderSelector,
    GroupPlanner,
    VirtualPIDRouterPlaneBlock,
    normalize_lohi_management_mode,
    strict_waypoint_support_report,
)


class AlgorithmLoHiManagerWaypointTest(unittest.TestCase):

    def setUp(self):
        self.graph = nx.Graph()
        self.graph.add_edge(0, 2, weight=1.0, geo_len_m=1.0)
        self.graph.add_edge(0, 1, weight=100.0, geo_len_m=100.0)
        self.graph.add_edge(1, 3, weight=1.0, geo_len_m=1.0)
        self.graph.add_edge(2, 4, weight=1.0, geo_len_m=1.0)
        self.graph.add_edge(3, 5, weight=1.0, geo_len_m=1.0)

        self.sat_pid = {0: 0, 1: 0, 2: 0, 3: 0, 4: 1, 5: 1}
        self.router = VirtualPIDRouterPlaneBlock()
        self.router.pid_members = {0: {0, 1, 2, 3}, 1: {4, 5}}
        self.router.pid_sat_comp = {
            0: {0: 0, 1: 0, 2: 0, 3: 0},
            1: {4: 0, 5: 0},
        }
        self.router.pid_mgmt_sat = {0: 1, 1: 4}

        self.planner = GroupPlanner()
        self.planner.edge_meta[(0, 1)] = {
            "isl_pairs": [(2, 4), (3, 5)],
            "links": 2,
        }

    def test_management_mode_normalization_and_strict_capability(self):
        self.assertEqual(
            normalize_lohi_management_mode("control-plane"),
            "control_plane_only",
        )
        self.assertEqual(
            normalize_lohi_management_mode("strict"),
            "strict_physical_waypoint",
        )
        with self.assertRaisesRegex(ValueError, "Invalid LoHi management mode"):
            normalize_lohi_management_mode("unknown")

        report = strict_waypoint_support_report()
        self.assertFalse(report["supported"])
        self.assertIn("waypoint phase", report["reason"])

    def test_manager_distance_field_changes_border_selection(self):
        current_dists = nx.single_source_dijkstra_path_length(
            self.graph.subgraph(self.router.pid_members[0]),
            0,
            weight="weight",
        )
        manager_dists = nx.single_source_dijkstra_path_length(
            self.graph.subgraph(self.router.pid_members[0]),
            1,
            weight="weight",
        )
        dst_dists = {4: 0.0, 5: 0.0}

        legacy_border = BorderSelector.pick_border_pair(
            self.graph,
            self.planner,
            0,
            1,
            self.sat_pid,
            src_sat=0,
            router=self.router,
            dst_sat=4,
            dst_pid=1,
            pre_src_side_dists=current_dists,
            pre_dst_side_dists=dst_dists,
        )
        manager_border = BorderSelector.pick_border_pair(
            self.graph,
            self.planner,
            0,
            1,
            self.sat_pid,
            src_sat=0,
            router=self.router,
            dst_sat=4,
            dst_pid=1,
            pre_src_side_dists=manager_dists,
            pre_dst_side_dists=dst_dists,
        )

        self.assertEqual(legacy_border, (2, 4))
        self.assertEqual(manager_border, (3, 5))


if __name__ == "__main__":
    unittest.main()
