"""Analytical sheet resistance, selective thermal spreading and native-board checks."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest

from solder_reinforcement import validate

HERE = Path(__file__).resolve().parents[1]
CONFIG = json.loads((HERE / "config.json").read_text())


class SolderInputTests(unittest.TestCase):
    def test_invalid_material_region_and_net_rejected(self):
        config = CONFIG["solder_reinforcement"]
        nets = set(config["regions"][0]["nets"])
        for key, value in (("rho_ohm_mm_20c", 0), ("tcr_per_c", float("nan")),
                           ("thermal_k_w_mk", True)):
            bad = copy.deepcopy(config)
            bad["material"][key] = value
            with self.assertRaises(ValueError):
                validate(bad, nets, {"F.Cu", "B.Cu"})
        for key, value in (("coverage_fraction", 1.1), ("thickness_mm", -1),
                           ("layer", "In1.Cu"), ("nets", ["typo"])):
            bad = copy.deepcopy(config)
            bad["regions"][0][key] = value
            with self.assertRaises(ValueError):
                validate(bad, nets, {"F.Cu", "B.Cu"})
        bad = copy.deepcopy(config)
        bad["regions"].append(copy.deepcopy(bad["regions"][0]))
        with self.assertRaises(ValueError):
            validate(bad, nets, {"F.Cu", "B.Cu"})


@unittest.skipUnless(importlib.util.find_spec("kipi"), "Requires KiPI environment")
class SolderPhysicsTests(unittest.TestCase):
    def fixture(self):
        import numpy as np
        from kipi.core.model.board import (BoardSnapshot, CopperLayer, DielectricLayer,
                                           Net, Poly, Stackup, Zone)
        from kipi.core.mesh.mesher import NetMesh
        from kipi.dc.solver.setup import NetProblem, VoltageSource, CurrentLoad
        stack = Stackup([CopperLayer(0, "F.Cu", 0, .035, 1.565),
                         CopperLayer(31, "B.Cu", 1, .035, 0)],
                        [DielectricLayer(1.53, "FR4", 4.5, 0, 31)], 1.6)
        polygon = Poly([(0, 0), (10, 0), (10, 2), (0, 2)])
        other = Poly([(0, 3), (10, 3), (10, 5), (0, 5)])
        snap = BoardSnapshot("coupon", "", stack, [Net(1, "power"), Net(2, "other")], [], [], [], [],
                             [Zone("z1", "power", "", 0, {0: [polygon], 31: [polygon]}),
                              Zone("z2", "other", "", 0, {0: [other], 31: [other]})],
                             [Poly([(0, 0), (10, 0), (10, 5), (0, 5)])])
        mesh = NetMesh("power", np.array(polygon.outline, dtype=float), np.full(4, 31),
                       np.array([[0, 1, 2], [0, 2, 3]]), np.full(2, 31), [31], [],
                       {"source": {31: np.array([0, 3])}, "load": {31: np.array([1, 2])}})
        problem = NetProblem("power", [VoltageSource("battery", ["source"], 12)],
                             [CurrentLoad("load", ["load"], 1)])
        cfg = copy.deepcopy(CONFIG["solder_reinforcement"])
        cfg["regions"][0]["nets"] = ["power"]
        return snap, mesh, problem, cfg

    def test_parallel_sheet_resistance_loss_and_copper_current_density(self):
        import numpy as np
        from kipi.dc.solver import fem, post
        from solder_reinforcement import activated
        snap, mesh, problem, cfg = self.fixture()
        bare = fem.solve(snap, mesh, problem)
        bare_drop = 12 - bare.node_v[1]
        for temperature in (20, 80):
            cfg["material"]["tcr_per_c"] = .002  # test separate material coefficients
            problem.temperature = lambda xy: np.full(len(xy), temperature)
            with activated(snap, cfg):
                solution = fem.solve(snap, mesh, problem)
            fields = post.compute_fields(solution)
            gc = .035 / (problem.settings.rho_ohm_mm * (1+.00393*(temperature-20)))
            gs = 1.5 / (cfg["material"]["rho_ohm_mm_20c"] * (1+.002*(temperature-20)))
            resistance = 10 / (2*(gc+gs))
            drop = 12 - solution.node_v[1]
            self.assertAlmostEqual(drop, resistance, places=10)
            self.assertAlmostEqual(fields.tri_power.sum(), resistance, places=10)
            self.assertAlmostEqual(fields.solder_power.sum()/fields.tri_power.sum(), gs/(gc+gs))
            expected_j = gc/(gc+gs) / (2*.035)
            np.testing.assert_allclose(fields.j_density, expected_j, rtol=1e-8)
            self.assertLess(fields.summary["energy_balance_error"], 1e-7)
            self.assertLess(drop, bare_drop)
        # Hooks must not leak to another solve after the context exits.
        problem.temperature = None
        again = fem.solve(snap, mesh, problem)
        self.assertAlmostEqual(12-again.node_v[1], bare_drop)
        self.assertIsNone(again.solder_reinforcement)

    def test_disabled_zero_thickness_and_fractional_coverage(self):
        from kipi.dc.solver import fem
        from solder_reinforcement import activated
        snap, mesh, problem, cfg = self.fixture()
        baseline = fem.solve(snap, mesh, problem).node_v[1]
        for disabled, thickness, coverage in ((True, 1.5, 1), (False, 0, 1), (False, 1.5, 0)):
            cfg["enabled"] = not disabled
            cfg["regions"][0].update(thickness_mm=thickness, coverage_fraction=coverage)
            with activated(snap, cfg):
                self.assertAlmostEqual(fem.solve(snap, mesh, problem).node_v[1], baseline)
        cfg["regions"][0].update(thickness_mm=1.5, coverage_fraction=.5)
        with activated(snap, cfg):
            result = fem.solve(snap, mesh, problem)
        expected = 10/(2*(.035/problem.settings.rho_ohm_mm+.75/cfg["material"]["rho_ohm_mm_20c"]))
        self.assertAlmostEqual(12-result.node_v[1], expected)

    def test_only_selected_bottom_net_gains_thermal_conductance(self):
        import numpy as np
        from kipi.dc.thermal.model import BoardThermalModel, ThermalSettings
        from kipi.core.progress import NULL
        from solder_reinforcement import activated
        snap, mesh, problem, cfg = self.fixture()
        model = BoardThermalModel(snap, ThermalSettings(grid_mm=.5))
        before, vertical = model.g.copy(), model.g_vertical.copy()
        with activated(snap, cfg) as reinforcement:
            reinforcement.thermal(model, NULL)
        delta = model.g - before
        self.assertEqual(delta[0].sum(), 0)
        self.assertEqual(delta[-1, model.y > 2, :].sum(), 0)
        np.testing.assert_allclose(delta[-1, model.y < 2, :], 1.5*50*.001)
        np.testing.assert_array_equal(model.g_vertical, vertical)
        # Uniform heating has exact area/convection balance with either matrix.
        q = model.empty_heat()
        q[-1, model.inside] = 1/model.inside.sum()
        result = model.solve(q)
        self.assertTrue(np.isfinite(result[:, model.inside]).all())

    def test_native_board_regions_and_nonconductive_epoxy(self):
        from kipi.sources.kicad_pcb.reader import read_board
        from solder_reinforcement import Reinforcement
        from fabrication_model import activated
        from kipi.dc.thermal.materials import lookup
        from kipi.dc.solver.via_barrel import ViaRule, barrel_copper_area
        snap = read_board(HERE.parent / CONFIG["board"])
        old_materials = [d.material for d in snap.stackup.dielectrics]
        with activated(snap, CONFIG["fabrication"]) as adjusted:
            reinforcement = Reinforcement(adjusted, CONFIG["solder_reinforcement"])
            self.assertEqual(len(reinforcement.regions), 1)
            self.assertTrue(all(v.filled for v in adjusted.vias if v.drill_mm <= .5))
            material = lookup(adjusted.stackup.dielectrics[0].material)
            self.assertEqual(material.k_w_mk, .8)
            self.assertEqual(material.k_through, .3)
            self.assertTrue(material.assumed)
        self.assertEqual([d.material for d in snap.stackup.dielectrics], old_materials)
        rule = ViaRule("through", .025, fill="nonconductive")
        self.assertEqual(barrel_copper_area(rule, .3, True, 1.724e-5),
                         barrel_copper_area(rule, .3, False, 1.724e-5))


if __name__ == "__main__":
    unittest.main()
