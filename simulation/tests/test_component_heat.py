"""Validate fixed-power inputs and, in KiPI's environment, heat conservation."""

import copy
import dataclasses
import importlib.util
import json
from pathlib import Path
import tempfile
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import component_heat
from run import read_config

HERE = Path(__file__).resolve().parents[1]


class ComponentInputTests(unittest.TestCase):
    def test_bad_power_and_missing_pad_rejected(self):
        source = dict(name="coil", ref="U1", pins=["85", "86"], power_w=1.6, board_fraction=1)
        pads = {"U1": {"85", "86"}}
        component_heat.validate([source], pads)
        for key, bad in (("power_w", -1), ("power_w", float("nan")),
                         ("board_fraction", 1.01), ("pins", ["999"])):
            changed = dict(source, **{key: bad})
            with self.assertRaises(ValueError):
                component_heat.validate([changed], pads)

    def test_cases_preserve_external_loads_and_separate_contact_assumptions(self):
        normal = read_config(HERE / "cases" / "all-loads-components.json")
        stress = read_config(HERE / "cases" / "all-loads-components-contact-max.json")
        self.assertEqual(sum(l["current"] for l in normal["setup"]["loads"]), 29)
        self.assertFalse(normal["setup"]["thermal"]["load_power"])
        self.assertEqual(normal["setup"]["loads"], stress["setup"]["loads"])
        for link in normal["setup"]["links"]:
            if link["side_a"]["ref"].startswith("F"):
                self.assertGreater(link["resistance"], 0)
            else:
                self.assertEqual(link["resistance"], 0)
        self.assertTrue(all(l["resistance"] == 0.05 for l in stress["setup"]["links"]
                            if l["side_a"]["ref"].startswith("U")))


@unittest.skipUnless(importlib.util.find_spec("kipi"), "Run in KiPI environment for integration checks")
class KiPiHeatIntegrationTests(unittest.TestCase):
    def test_actual_board_heat_conservation_fraction_and_case_isolation(self):
        import numpy as np
        from kipi.dc.pi.model import PISetup, active_setup, validate
        from kipi.dc.thermal import cosim
        from kipi.dc.thermal.model import BoardThermalModel
        from kipi.sources.kicad_pcb.reader import read_board
        from kipi.core.model.stackup import from_setup

        config = read_config(HERE / "cases" / "all-loads-components.json")
        setup = PISetup.from_dict(config["setup"])
        self.assertEqual(validate(active_setup(setup)[0]), [])
        # Empty electrical results isolate added heat without running the full FEA solve.
        tree = SimpleNamespace(groups={}, vrms=[])
        with tempfile.TemporaryDirectory() as temporary:
            board = Path(temporary) / "test board.kicad_pcb"
            shutil.copy2(HERE.parent / config["board"], board)
            snap = read_board(board)
            self.assertEqual(snap.file, "")  # Regression: native KiPI reader leaves it empty.
            st, reason = from_setup(snap.stackup, setup.stackup)
            if setup.stackup is None:
                st = snap.stackup
            self.assertIsNotNone(st, reason)
            snap = dataclasses.replace(snap, stackup=st)
            self.assertEqual(st.copper[0].thickness_mm, .035)
            self.assertEqual(st.copper[-1].thickness_mm, .035)
            self.assertTrue(all(c.thickness_mm == .0175 for c in st.copper[1:-1]))
            path = component_heat.source_path(board)
            sources = config["component_heat"]
            path.write_text(json.dumps(sources))
            with patch.object(cosim, "heat_sources", cosim.heat_sources):
                component_heat.install()
                xy, watts, layers, kinds = cosim.heat_sources(tree, snap, setup)
                self.assertAlmostEqual(float(watts.sum()), 7.1776)
                self.assertAlmostEqual(sum(kinds.values()), float(watts.sum()))
                self.assertEqual(len(xy), len(watts))
                self.assertEqual(len(layers), len(watts))
                self.assertTrue(set(layers) <= {cu.id for cu in snap.stackup.copper})
                self.assertTrue(np.isfinite(xy).all())
                model = BoardThermalModel(snap, setup.thermal)
                deposited = model.empty_heat()
                model.deposit(deposited, xy, watts, layers)
                self.assertAlmostEqual(float(deposited.sum()), 7.1776)
                temperature = model.solve(deposited)
                self.assertGreater(float(np.nanmax(temperature)), setup.thermal.ambient_c)
                self.assertTrue(np.isfinite(temperature[:, model.inside]).all())
                path.write_text(json.dumps({"sources": sources, "connectors": config["connectors"]}))
                tree.loads = [SimpleNamespace(name=l.name, current=l.current, v_effective=11.9)
                              for l in setup.loads]
                all_heat = cosim.heat_sources(tree, snap, setup)
                self.assertAlmostEqual(float(all_heat[1].sum()), 11.162215384615386)
                self.assertAlmostEqual(all_heat[3]["Relay coil heat"], 6.4)
                self.assertAlmostEqual(all_heat[3]["DT contacts (board-deposited estimate)"],
                                       3.9846153846153847)
                reduced = copy.deepcopy(sources)
                for source in reduced:
                    source["board_fraction"] = 0.5
                path.write_text(json.dumps(reduced))
                self.assertAlmostEqual(float(cosim.heat_sources(tree, snap, setup)[1].sum()), 7.1776 / 2)
                # Opening a baseline board without the sidecar must not inherit this heat.
                other = dataclasses.replace(snap, board_name="baseline.kicad_pcb")
                self.assertEqual(float(cosim.heat_sources(tree, other, setup)[1].sum()), 0)

    def test_contact_heat_follows_solved_current_and_report_boundary(self):
        from connector_model import connector_rows, heat_inputs, section
        from kipi.dc.pi.model import PISetup

        config = read_config(HERE / "cases" / "all-loads-components.json")
        setup = PISetup.from_dict(config["setup"])
        tree = SimpleNamespace(loads=[SimpleNamespace(name=l.name, current=l.current,
                                    v_effective=11.9) for l in setup.loads], thermal=None)
        data = {"sources": config["component_heat"], "connectors": config["connectors"]}
        rows = connector_rows(tree, setup, data)
        self.assertAlmostEqual(sum(s["power_w"] for s in heat_inputs(rows)), 2 * .1 / 13 * 259)
        radiator = next(row for row in rows if row["load"] == "Radiator")
        self.assertAlmostEqual(radiator["estimated_harness_voltage_v"],
                               11.7 - radiator["external_wire_w"] / 13)
        self.assertAlmostEqual(radiator["supply_contact_w"], 1.3)
        tree.loads[1].current = 0
        zero = connector_rows(tree, setup, data)[1]
        self.assertEqual(zero["supply_contact_w"], 0)
        tree.loads[1].current = 15
        over = connector_rows(tree, setup, data)[1]
        self.assertIn("EXCEEDS", over["rating_status"])
        data["connectors"][0]["supply_wire_m"] = 1
        wire_row = connector_rows(tree, setup, data)[0]
        self.assertGreater(wire_row["external_wire_w"], 0)
        self.assertIn("PCB-pad V", section(rows, data, tree))
        self.assertIn("Estimated harness-side V", section(rows, data, tree))

    def test_native_report_includes_interface_table_and_machine_readable_audit(self):
        from connector_model import install_report
        from kipi.dc.report import html as report_html
        from kipi.dc.pi.results import TreeResult, LoadReport
        from kipi.dc.pi.model import PISetup
        from kipi.sources.kicad_pcb.reader import read_board

        config = read_config(HERE / "cases" / "all-loads-components.json")
        setup = PISetup.from_dict(config["setup"])
        tree = TreeResult(loads=[LoadReport(l.name, "test", l.current, 12, 11.9,
                          11.9, 0, 11.9, .1, "", None, v_worst=11.9,
                          v_low=11.9, v_high=11.9) for l in setup.loads])
        with tempfile.TemporaryDirectory() as temporary:
            board = Path(temporary) / config["board"]
            shutil.copy2(HERE.parent / config["board"], board)
            snap = read_board(board)
            component_heat.source_path(board).write_text(json.dumps(
                {"sources": config["component_heat"], "connectors": config["connectors"]}))
            with patch.object(report_html, "write_report", report_html.write_report):
                install_report(component_heat.read_model)
                report = Path(temporary) / "test report.html"
                report_html.write_report(report, tree, {}, snap, setup)
                self.assertIn("Estimated harness-side V", report.read_text())
                audit = json.loads(report.with_suffix(".interfaces.json").read_text())
                self.assertEqual(len(audit["connector_estimates"]), 4)
                radiator = audit["connector_estimates"][1]
                self.assertAlmostEqual(radiator["additional_drop_v"],
                                       .2 + radiator["external_wire_w"] / 13)


if __name__ == "__main__":
    unittest.main()
