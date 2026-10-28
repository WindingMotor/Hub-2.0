"""Analytical verification of compact-network equations and wire thermal limits."""

import importlib.util
import unittest
from types import SimpleNamespace

from thermal_network import wire_fin


class WirePhysicsTests(unittest.TestCase):
    def test_cold_wire_and_distributed_heating_and_fin_length(self):
        w = dict(length_m=.9144, copper_area_mm2=1.31, outer_diameter_mm=2.5,
                 insulation_k_w_mk=.2, surface_h_w_m2k=10, copper_k_w_mk=400,
                 ohm_per_m_20c=.01317, tcr_per_c=.00393)
        g, sink, power = wire_fin(w, 0, 25)
        self.assertGreater(g, 0)
        self.assertEqual(sink, 25)
        self.assertEqual(power, 0)
        _, sink, power = wire_fin(w, 13, 25)
        self.assertGreater(sink, 25)
        self.assertGreater(power, 13**2 * .01317 * w["length_m"])
        # A few feet is beyond the local fin length: extra length adds loss but
        # cannot be treated as ever-increasing cooling conductance.
        long_g, _, long_power = wire_fin(dict(w, length_m=2), 13, 25)
        self.assertAlmostEqual(g, long_g, places=8)
        self.assertGreater(long_power, power)
        short_g, _, _ = wire_fin(dict(w, length_m=.01), 13, 25)
        self.assertLess(short_g, g)


@unittest.skipUnless(importlib.util.find_spec("numpy"), "Requires NumPy")
class CompactNetworkPhysicsTests(unittest.TestCase):
    def model(self):
        import numpy as np
        from thermal_network import CompactBoard

        # Exact single-cell board: 10 K/W to ambient.
        class Board:
            layers = [0]
            inside = np.ones((1, 1), dtype=bool)
            settings = SimpleNamespace(ambient_c=25)

            def empty_heat(self):
                return np.zeros((1, 1, 1))

            def solve(self, heat):
                return 25 + 10 * heat

        board = Board()
        network = CompactBoard(board, None)
        network.pads.weight = lambda ids: np.ones((1, 1, 1))
        return board, network

    def test_two_path_solution_matches_hand_calculation(self):
        board, network = self.model()
        node = dict(name="component", category="test", pad_ids=["pad"], power_w=2,
                    thermal=dict(r_board_k_w=20, r_air_k_w=30, status="analytical test"))
        t, rows = network.solve(board.empty_heat(), [node])
        # Component-to-air is 30 K/W; board path is 20+10=30 K/W.
        self.assertAlmostEqual(float(t.max()), 35)
        self.assertAlmostEqual(rows[0]["component_node_c"], 55)
        self.assertAlmostEqual(rows[0]["to_board_w"], 1)
        self.assertAlmostEqual(rows[0]["to_external_w"], 1)

    def test_hot_board_can_lose_heat_through_passive_component(self):
        board, network = self.model()
        node = dict(name="passive", category="test", pad_ids=["pad"], power_w=0,
                    thermal=dict(r_board_k_w=20, r_air_k_w=30, status="analytical test"))
        heat = board.empty_heat() + 2
        t, rows = network.solve(heat, [node])
        self.assertAlmostEqual(float(t.max()), 25+2/(1/10+1/50))
        self.assertLess(rows[0]["to_board_w"], 0)
        self.assertAlmostEqual(rows[0]["energy_error_w"], 0)

    def test_all_to_board_limit_and_coil_feedback(self):
        board, network = self.model()
        node = dict(name="coil", category="test", pad_ids=["pad"], power_w=1.6,
                    thermal=dict(r_board_k_w=20, r_air_k_w=None, status="limit test"))
        t, rows = network.solve(board.empty_heat(), [node])
        self.assertAlmostEqual(float(t.max()), 41)
        self.assertAlmostEqual(rows[0]["to_board_w"], 1.6)
        node["coil"] = dict(cold_ohm=90, reference_c=23, tcr_per_c=.00393, voltage_v=12)
        _, hot = network.solve(board.empty_heat(), [node])
        self.assertLess(hot[0]["generated_w"], 1.6)
        self.assertAlmostEqual(hot[0]["generated_w"], hot[0]["to_board_w"])
