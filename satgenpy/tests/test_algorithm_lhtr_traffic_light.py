import csv
import os
import tempfile
import unittest

import networkx as nx

from satgen.dynamic_state import algorithm_lhtr as lhtr


class TestAlgorithmLhtrTrafficLight(unittest.TestCase):

    def setUp(self):
        self.saved_globals = {
            "ENABLE_TRAFFIC_LIGHT": lhtr.ENABLE_TRAFFIC_LIGHT,
            "TRAFFIC_LIGHT_SCORING_MODE": lhtr.TRAFFIC_LIGHT_SCORING_MODE,
            "TRAFFIC_LIGHT_ALT_PATH_FACTOR": lhtr.TRAFFIC_LIGHT_ALT_PATH_FACTOR,
            "TRAFFIC_LIGHT_YELLOW_PENALTY_M": lhtr.TRAFFIC_LIGHT_YELLOW_PENALTY_M,
            "TRAFFIC_LIGHT_RED_PENALTY_M": lhtr.TRAFFIC_LIGHT_RED_PENALTY_M,
            "TRAFFIC_LIGHT_YELLOW_PENALTY_S": lhtr.TRAFFIC_LIGHT_YELLOW_PENALTY_S,
            "TRAFFIC_LIGHT_RED_PENALTY_S": lhtr.TRAFFIC_LIGHT_RED_PENALTY_S,
            "TRAFFIC_LIGHT_BUFFER_SIZE": lhtr.TRAFFIC_LIGHT_BUFFER_SIZE,
            "ENABLE_TRAFFIC_LIGHT_DIAGNOSTICS": lhtr.ENABLE_TRAFFIC_LIGHT_DIAGNOSTICS,
            "LHTR_DIAGNOSTICS_DIR": lhtr.LHTR_DIAGNOSTICS_DIR,
            "_ROUTER": lhtr._ROUTER,
            "_GPLANNER": lhtr._GPLANNER,
        }
        lhtr.ENABLE_TRAFFIC_LIGHT = True
        lhtr.TRAFFIC_LIGHT_SCORING_MODE = "categorical"
        lhtr.TRAFFIC_LIGHT_ALT_PATH_FACTOR = 1.5

    def tearDown(self):
        for name, value in self.saved_globals.items():
            setattr(lhtr, name, value)

    @staticmethod
    def candidate(next_hop, path_cost, color, link_qor=0.0):
        return lhtr.NextHopCandidate(
            next_hop=next_hop,
            path_cost=path_cost,
            decision_score=lhtr._traffic_light_decision_score(path_cost, color),
            final_color=color,
            link_qor=link_qor,
            queue_packets=0,
            route_kind="test",
        )

    def select(self, candidates, preferred_br_next_hop=None):
        return lhtr.select_next_hop_candidate_by_traffic_light(
            candidates,
            preferred_br_next_hop=preferred_br_next_hop,
        )

    def test_green_br_is_always_selected(self):
        br = self.candidate(1, 10.0, lhtr.TrafficLightColor.GREEN)
        alternative = self.candidate(2, 11.0, lhtr.TrafficLightColor.GREEN)

        selected, picked_br, _ = self.select([alternative, br])

        self.assertEqual(1, picked_br.next_hop)
        self.assertEqual(1, selected.next_hop)

    def test_yellow_br_selects_green_or_yellow_sbr(self):
        for sbr_color in (
            lhtr.TrafficLightColor.GREEN,
            lhtr.TrafficLightColor.YELLOW,
        ):
            with self.subTest(sbr_color=sbr_color):
                br = self.candidate(1, 10.0, lhtr.TrafficLightColor.YELLOW)
                sbr = self.candidate(2, 11.0, sbr_color)

                selected, _, _ = self.select([br, sbr])

                self.assertEqual(2, selected.next_hop)

    def test_red_br_selects_green_or_yellow_sbr(self):
        for sbr_color in (
            lhtr.TrafficLightColor.GREEN,
            lhtr.TrafficLightColor.YELLOW,
        ):
            with self.subTest(sbr_color=sbr_color):
                br = self.candidate(1, 10.0, lhtr.TrafficLightColor.RED)
                sbr = self.candidate(2, 11.0, sbr_color)

                selected, _, _ = self.select([br, sbr])

                self.assertEqual(2, selected.next_hop)

    def test_both_red_compare_qor_then_categorical_path_cost(self):
        br = self.candidate(1, 10.0, lhtr.TrafficLightColor.RED, link_qor=0.9)
        lower_qor_sbr = self.candidate(
            2,
            11.0,
            lhtr.TrafficLightColor.RED,
            link_qor=0.8,
        )
        selected, _, _ = self.select([br, lower_qor_sbr])
        self.assertEqual(2, selected.next_hop)

        preferred_br = self.candidate(
            1,
            12.0,
            lhtr.TrafficLightColor.RED,
            link_qor=0.9,
        )
        lower_cost_sbr = self.candidate(
            2,
            10.0,
            lhtr.TrafficLightColor.RED,
            link_qor=0.9,
        )
        selected, picked_br, picked_sbr = self.select(
            [preferred_br, lower_cost_sbr],
            preferred_br_next_hop=1,
        )
        self.assertEqual(1, picked_br.next_hop)
        self.assertEqual(2, picked_sbr.next_hop)
        self.assertEqual(2, selected.next_hop)

    def test_categorical_selection_is_independent_of_penalty_values(self):
        br = self.candidate(1, 10.0, lhtr.TrafficLightColor.YELLOW)
        sbr = self.candidate(2, 11.0, lhtr.TrafficLightColor.GREEN)
        first_selected, _, _ = self.select([br, sbr])

        lhtr.TRAFFIC_LIGHT_YELLOW_PENALTY_M = 9.0e12
        lhtr.TRAFFIC_LIGHT_RED_PENALTY_M = 18.0e12
        lhtr.TRAFFIC_LIGHT_YELLOW_PENALTY_S = 9.0e6
        lhtr.TRAFFIC_LIGHT_RED_PENALTY_S = 18.0e6
        rebuilt_br = self.candidate(1, 10.0, lhtr.TrafficLightColor.YELLOW)
        rebuilt_sbr = self.candidate(2, 11.0, lhtr.TrafficLightColor.GREEN)
        second_selected, _, _ = self.select([rebuilt_br, rebuilt_sbr])

        self.assertEqual(2, first_selected.next_hop)
        self.assertEqual(2, second_selected.next_hop)
        self.assertEqual(rebuilt_br.path_cost, rebuilt_br.decision_score)

    def test_legacy_fused_preserves_color_penalty_in_decision_score(self):
        lhtr.TRAFFIC_LIGHT_SCORING_MODE = "legacy_fused"
        path_cost = 10.0

        candidate = self.candidate(
            1,
            path_cost,
            lhtr.TrafficLightColor.YELLOW,
        )

        self.assertAlmostEqual(
            path_cost + lhtr.traffic_light_color_to_cost(
                lhtr.TrafficLightColor.YELLOW
            ),
            candidate.decision_score,
        )

    def test_legacy_fused_preserves_decision_score_tie_break(self):
        lhtr.TRAFFIC_LIGHT_SCORING_MODE = "legacy_fused"
        preferred_br = lhtr.NextHopCandidate(
            next_hop=1,
            path_cost=10.0,
            decision_score=12.0,
            final_color=lhtr.TrafficLightColor.RED,
            link_qor=0.9,
            queue_packets=0,
            route_kind="test",
        )
        lower_score_sbr = lhtr.NextHopCandidate(
            next_hop=2,
            path_cost=10.0,
            decision_score=11.0,
            final_color=lhtr.TrafficLightColor.RED,
            link_qor=0.9,
            queue_packets=0,
            route_kind="test",
        )

        selected, picked_br, picked_sbr = self.select(
            [preferred_br, lower_score_sbr],
            preferred_br_next_hop=1,
        )

        self.assertEqual(1, picked_br.next_hop)
        self.assertEqual(2, picked_sbr.next_hop)
        self.assertEqual(2, selected.next_hop)

    def test_meter_only_config_recomputes_delay_penalties(self):
        yellow_m = lhtr.SPEED_OF_LIGHT_M_PER_S * 0.01
        red_m = lhtr.SPEED_OF_LIGHT_M_PER_S * 0.02

        lhtr.init({
            "traffic_light_scoring_mode": "categorical",
            "traffic_light_yellow_penalty_m": yellow_m,
            "traffic_light_red_penalty_m": red_m,
        })

        self.assertAlmostEqual(0.01, lhtr.TRAFFIC_LIGHT_YELLOW_PENALTY_S)
        self.assertAlmostEqual(0.02, lhtr.TRAFFIC_LIGHT_RED_PENALTY_S)

    def test_diagnostics_separate_configured_and_applied_penalty(self):
        br = self.candidate(1, 10.0, lhtr.TrafficLightColor.YELLOW)
        rows = []

        lhtr._record_br_sbr_diagnostic(
            rows,
            time_ns=0,
            src=0,
            dst=2,
            current_node=0,
            pid=0,
            case_type="test",
            selected=br,
            br=br,
            sbr=None,
        )

        self.assertEqual("categorical", rows[0]["traffic_light_scoring_mode"])
        self.assertGreater(rows[0]["br_traffic_light_penalty"], 0.0)
        self.assertEqual(0.0, rows[0]["br_applied_traffic_light_penalty"])
        self.assertEqual(rows[0]["br_path_cost"], rows[0]["br_decision_score"])

    def test_tqor_is_next_hop_total_outgoing_queue_occupancy(self):
        graph = nx.Graph()
        graph.add_edges_from([(0, 1), (1, 2)])
        lhtr.TRAFFIC_LIGHT_BUFFER_SIZE = 100

        state = lhtr.build_traffic_light_state(
            {
                (0, 1): 10,
                (1, 0): 40,
                (1, 2): 40,
            },
            graph,
            num_satellites=3,
        )

        self.assertAlmostEqual(0.1, state.link_qor[(0, 1)])
        self.assertEqual(80, state.node_queue_packets[1])
        self.assertEqual(200, state.node_queue_capacity_packets[1])
        self.assertAlmostEqual(0.4, state.node_tqor[1])
        self.assertEqual(lhtr.TrafficLightColor.GREEN, state.link_color[(0, 1)])
        self.assertEqual(lhtr.TrafficLightColor.YELLOW, state.node_color[1])
        self.assertEqual(
            lhtr.TrafficLightColor.YELLOW,
            state.final_link_color_map[(0, 1)],
        )

    def test_diagnostics_writer_uses_run_local_directory_and_headers(self):
        graph = nx.Graph()
        graph.add_edge(0, 1)
        state = lhtr.build_traffic_light_state(
            {(0, 1): 70, (1, 0): 40},
            graph,
            num_satellites=2,
        )
        br = self.candidate(1, 10.0, lhtr.TrafficLightColor.YELLOW)
        br = lhtr.NextHopCandidate(
            **{**br.__dict__, "path": (0, 1)}
        )
        decision_rows = []
        lhtr._record_br_sbr_diagnostic(
            decision_rows,
            time_ns=0,
            src=0,
            dst=2,
            current_node=0,
            pid=0,
            case_type="same_pid_next_hop",
            selected=br,
            br=br,
            sbr=None,
            sbr_unavailable_reason="no_alternative_candidate",
        )
        decision_rows[0]["installed_next_hop"] = 1
        decision_rows[0]["selected_applied"] = True
        decision_rows[0]["fstate_consistency_notes"] = "exact_next_hop_check"

        lhtr.ENABLE_TRAFFIC_LIGHT_DIAGNOSTICS = True
        lhtr.LHTR_DIAGNOSTICS_DIR = "lhtr_diagnostics"
        with tempfile.TemporaryDirectory() as tmpdir:
            dynamic_state_dir = os.path.join(
                tmpdir,
                "algorithm_lhtr",
                "dynamic_state",
            )
            os.makedirs(dynamic_state_dir)
            diagnostics_dir = lhtr._resolve_lhtr_diagnostics_dir(
                dynamic_state_dir
            )
            lhtr._write_traffic_light_diagnostics(
                diagnostics_dir,
                0,
                graph,
                {0: 0, 1: 0},
                state,
                decision_rows,
            )
            second_rows = [dict(decision_rows[0], time_ns=100000000)]
            lhtr._write_traffic_light_diagnostics(
                diagnostics_dir,
                100000000,
                graph,
                {0: 0, 1: 0},
                state,
                second_rows,
            )

            required = {
                "lhtr_qor_tqor_samples.csv",
                "lhtr_traffic_light_color_summary.csv",
                "lhtr_br_sbr_decision_log.csv",
                "lhtr_br_sbr_summary.csv",
                "lhtr_decision_reason_summary.csv",
                "lhtr_fstate_decision_consistency.csv",
            }
            self.assertEqual(required, set(os.listdir(diagnostics_dir)))
            self.assertFalse(any(
                name.startswith("lhtr_")
                for name in os.listdir(dynamic_state_dir)
            ))
            for filename in required:
                with open(
                    os.path.join(diagnostics_dir, filename),
                    newline="",
                    encoding="utf-8",
                ) as f_in:
                    self.assertTrue(next(csv.reader(f_in)))
            with open(
                os.path.join(
                    diagnostics_dir,
                    "lhtr_decision_reason_summary.csv",
                ),
                newline="",
                encoding="utf-8",
            ) as f_in:
                reason_rows = list(csv.DictReader(f_in))
            self.assertEqual("no_alternative_candidate", reason_rows[0]["decision_reason"])
            self.assertEqual("2", reason_rows[0]["count"])
            self.assertEqual(100.0, float(reason_rows[0]["percentage"]))
            with open(
                os.path.join(
                    diagnostics_dir,
                    "lhtr_traffic_light_color_summary.csv",
                ),
                newline="",
                encoding="utf-8",
            ) as f_in:
                color_rows = list(csv.DictReader(f_in))
            self.assertEqual("1", color_rows[0]["tqor_yellow_count"])
            self.assertEqual("1", color_rows[0]["tqor_red_count"])

    def test_diagnostics_directory_cannot_escape_algorithm_run(self):
        lhtr.LHTR_DIAGNOSTICS_DIR = "../outside"
        with self.assertRaisesRegex(ValueError, "dedicated relative directory"):
            lhtr._resolve_lhtr_diagnostics_dir(
                "/tmp/run/algorithm_lhtr/dynamic_state"
            )

    def test_disabled_diagnostics_do_not_create_output_directory(self):
        lhtr.ENABLE_TRAFFIC_LIGHT_DIAGNOSTICS = False
        graph = nx.Graph()
        graph.add_edge(0, 1)
        with tempfile.TemporaryDirectory() as tmpdir:
            diagnostics_dir = os.path.join(tmpdir, "lhtr_diagnostics")
            lhtr._write_traffic_light_diagnostics(
                diagnostics_dir,
                0,
                graph,
                {0: 0, 1: 0},
                None,
                [],
            )
            self.assertFalse(os.path.exists(diagnostics_dir))

    def test_sbr_unavailable_diagnoses_stretch_without_changing_selection(self):
        br = self.candidate(1, 10.0, lhtr.TrafficLightColor.YELLOW)
        far_alternative = self.candidate(
            2,
            20.0,
            lhtr.TrafficLightColor.GREEN,
        )

        selected, picked_br, picked_sbr = self.select([br, far_alternative])

        self.assertEqual(br, selected)
        self.assertEqual(br, picked_br)
        self.assertIsNone(picked_sbr)
        self.assertEqual(
            "sbr_stretch_too_high",
            lhtr._diagnose_sbr_unavailable([br, far_alternative], picked_br),
        )


if __name__ == "__main__":
    unittest.main()
