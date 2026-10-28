"""Exercise new thermal physics on the saved PCB, without rerunning DC FEA."""

import copy
import dataclasses
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("kipi"), "Requires KiPI environment")
class ResearchedModelIntegration(unittest.TestCase):
    def test_native_source_dispatch_partition_energy_and_finite_pad_layers(self):
        import numpy as np
        import component_heat
        from kipi.dc.pi.model import PISetup
        from kipi.dc.pi.results import TreeResult, LoadReport
        from kipi.dc.pi import tree as electrical
        from kipi.dc.thermal import cosim
        from kipi.dc.thermal.model import BoardThermalModel
        from kipi.core.model.stackup import from_setup
        from kipi.sources.kicad_pcb.reader import read_board
        from thermal_network import PadAreas

        config = json.loads((HERE / "config.json").read_text())
        setup = PISetup.from_dict(config["setup"])
        setup.thermal.iterations = 1
        setup.thermal.grid_mm = .8
        model_data = {"sources": config["component_heat"], "connectors": config["connectors"],
                      "thermal_model": config["thermal_model"],
                      "solder_reinforcement": config.get("solder_reinforcement"),
                      "fabrication": config.get("fabrication")}
        reports = [LoadReport(l.name, "test", l.current, 12, 11.9, 11.9, 0, 11.9, .1,
                             "", None, v_worst=11.9, v_low=11.9, v_high=11.9)
                   for l in setup.loads]
        with tempfile.TemporaryDirectory() as temporary:
            board = Path(temporary) / config["board"]
            shutil.copy2(HERE.parent / config["board"], board)
            component_heat.source_path(board).write_text(json.dumps(model_data))
            snap = read_board(board)
            self.assertEqual(snap.file, "")
            st, reason = from_setup(snap.stackup, setup.stackup)
            if setup.stackup is None:
                st = snap.stackup
            self.assertIsNotNone(st, reason)
            snap = dataclasses.replace(snap, stackup=st)
            model = BoardThermalModel(snap, setup.thermal)
            areas = PadAreas(model, snap)
            pad_ids = [p.id for p in snap.pads if p.footprint == "CN1" and p.number == "3"]
            weights = areas.weight(pad_ids)
            self.assertAlmostEqual(float(weights.sum()), 1)
            self.assertEqual(float(weights[1:-1].sum()), 0)  # no source inside inner-layer antipads
            self.assertGreater(int(np.count_nonzero(weights)), 4)  # finite footprint, not 1 cell/layer
            original_solver = cosim.solve_electrothermal
            original_heat = cosim.heat_sources
            with patch.object(electrical, "solve_tree", side_effect=lambda *a, **k:
                              TreeResult(loads=copy.deepcopy(reports))), \
                    patch.object(cosim, "solve_electrothermal", original_solver), \
                    patch.object(cosim, "heat_sources", original_heat):
                component_heat.install(expected_board=board)
                result = cosim.solve_electrothermal(snap, setup, setup.thermal)
                rows = result.thermal.compact_nodes
                self.assertEqual(len(rows), 12)  # 4 coils + 8 supply/return contacts
                for row in rows:
                    self.assertAlmostEqual(row["generated_w"], row["to_board_w"]+row["to_external_w"])
                self.assertTrue(np.isfinite(result.thermal.temps[:, model.inside]).all())
                self.assertAlmostEqual(result.thermal.heat_w, sum(result.thermal.heat_by_kind.values()))
                self.assertGreater(sum(r["to_external_w"] for r in rows), 0)
                self.assertIn("UNCALIBRATED", result.thermal.model_status)
                self.assertLess(sum(r["generated_w"] for r in rows if r["name"].endswith("coil")), 6.4)


if __name__ == "__main__":
    unittest.main()
