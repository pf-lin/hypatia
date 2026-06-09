import unittest

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


if __name__ == "__main__":
    unittest.main()
