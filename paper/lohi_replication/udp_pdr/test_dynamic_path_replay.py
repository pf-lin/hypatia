import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dynamic_path_replay import (
    ForwardingStateEntry,
    latest_snapshot_time,
    load_forwarding_state_at,
    replay_path,
)


class DynamicPathReplayTest(unittest.TestCase):
    def write_snapshot(self, directory, time_ns, lines):
        path = os.path.join(directory, "fstate_%d.txt" % time_ns)
        with open(path, "w") as f_out:
            f_out.write("\n".join(lines) + "\n")

    def test_normal_path(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_snapshot(
                directory,
                0,
                [
                    "3,4,0,0,0",
                    "0,4,1,1,1",
                    "1,4,4,0,0",
                ],
            )
            state, snapshot_time = load_forwarding_state_at(directory, 0)
            result = replay_path(state, 3, 4, num_satellites=3, num_nodes=5)
            self.assertEqual(snapshot_time, 0)
            self.assertEqual(result.status, "success")
            self.assertEqual(result.path, (3, 0, 1, 4))
            self.assertEqual(
                result.interface_keys,
                ("GSL:3->-1", "ISL:0->1", "GSL:1->-1"),
            )

    def test_missing_route_and_loop(self):
        missing = {
            (3, 4): ForwardingStateEntry(3, 4, 0, 0, 0)
        }
        self.assertEqual(
            replay_path(missing, 3, 4, num_satellites=3, num_nodes=5).status,
            "missing_entry",
        )
        no_route = {(3, 4): ForwardingStateEntry(3, 4, -1, -1, -1)}
        self.assertEqual(
            replay_path(no_route, 3, 4, num_satellites=3, num_nodes=5).status,
            "no_route",
        )

        with tempfile.TemporaryDirectory() as directory:
            self.write_snapshot(
                directory,
                0,
                [
                    "3,4,0,0,0",
                    "0,4,1,0,0",
                    "1,4,0,0,0",
                ],
            )
            state, _ = load_forwarding_state_at(directory, 0)
            self.assertEqual(
                replay_path(state, 3, 4, num_satellites=3, num_nodes=5).status,
                "loop",
            )

    def test_snapshot_boundary_uses_latest_not_after_time(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_snapshot(directory, 0, ["3,4,0,0,0"])
            self.write_snapshot(directory, 100, ["3,4,-1,-1,-1"])
            before, before_time = load_forwarding_state_at(directory, 99)
            at_boundary, boundary_time = load_forwarding_state_at(directory, 100)
            self.assertEqual(before[(3, 4)].next_hop, 0)
            self.assertEqual(before_time, 0)
            self.assertEqual(at_boundary[(3, 4)].next_hop, -1)
            self.assertEqual(boundary_time, 100)
            self.assertEqual(latest_snapshot_time([0, 100], 99), 0)
            self.assertEqual(latest_snapshot_time([0, 100], 100), 100)


if __name__ == "__main__":
    unittest.main()
