"""Headless full electrothermal check, then thermal-grid/model sensitivity checks.

Run with KiPI's environment and pinned source on PYTHONPATH (see README).
The full case solves electrical/thermal feedback. Subsequent checks freeze its
electrical fields to isolate thermal discretization/model effects; they are not
independent fully coupled operating-case predictions.
"""

import argparse
import copy
import dataclasses
import json
import logging
from pathlib import Path
from unittest.mock import patch


def main():
    from run import snapshot, read_config, HERE
    from component_heat import install, read_model
    from kipi.core.model.stackup import from_setup
    from kipi.core.progress import ProgressReporter
    from kipi.sources.kicad_pcb.reader import read_board
    from kipi.dc.pi.model import PISetup
    from kipi.dc.pi import tree as electrical
    from kipi.dc.thermal import cosim
    from researched_cosim import solve

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--sensitivity", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = read_config(args.config.resolve())
    board = snapshot(config, args.config.resolve())
    snap = read_board(board)
    setup = PISetup.load(board.with_name(board.stem + ".kipi-setup.yml"))
    if setup.stackup:
        stack, reason = from_setup(snap.stackup, setup.stackup)
        if stack is None:
            raise ValueError(reason)
        snap = dataclasses.replace(snap, stackup=stack)
    progress = ProgressReporter()
    install(expected_board=board)
    tree = cosim.solve_electrothermal(snap, setup, setup.thermal, progress)

    def summary(name, result, kind):
        th = result.thermal
        return {"case": name, "check_type": kind, "model_status": th.model_status,
                "grid_mm": result.thermal.settings.grid_mm,
                "net_board_heat_w": th.heat_w, "peak_board_c": th.t_max,
                "heat_by_kind_w": th.heat_by_kind, "history": th.history,
                "solder_reinforcement": getattr(th, "solder_reinforcement", None),
                "fabrication": getattr(th, "fabrication", None),
                "compact_nodes": th.compact_nodes,
                "loads": [{"name": load.name, "current_a": load.current,
                           "pcb_voltage_v": load.v_effective} for load in result.loads]}

    checks = [summary("default", tree, "full electrothermal solve")]
    output = board.parent / "thermal-validation.json"
    output.write_text(json.dumps(checks, indent=2) + "\n")
    print("FULL CASE:", checks[0]["peak_board_c"], "C;", tree.thermal.heat_w, "W", flush=True)
    if args.sensitivity:
        # Do not repeat the expensive electrical mesh/solve for a thermal-only comparison.
        def frozen(*args, **kwargs):
            return dataclasses.replace(tree, warnings=[])
        with patch.object(electrical, "solve_tree", side_effect=frozen):
            for name in ("board-reference.json", "all-to-board-stress.json",
                         "compact-weak-board-coupling.json", "compact-strong-board-coupling.json"):
                cfg = read_config(HERE / "cases" / name)
                data = {"sources": cfg["component_heat"], "connectors": cfg["connectors"],
                        "thermal_model": cfg["thermal_model"], "fabrication": cfg.get("fabrication"),
                        "solder_reinforcement": config.get("solder_reinforcement")}
                settings = copy.deepcopy(setup.thermal)
                settings.iterations = 1
                settings.grid_mm = .8
                result = solve(snap, setup, settings, data, progress)
                checks.append(summary(name, result, "thermal sensitivity at frozen electrical losses"))
                output.write_text(json.dumps(checks, indent=2) + "\n")
                print(name, result.thermal.t_max, "C", flush=True)
            for grid in (.8, .4):
                settings = copy.deepcopy(setup.thermal)
                settings.iterations = 1
                settings.grid_mm = grid
                result = solve(snap, setup, settings, read_model(snap), progress)
                checks.append(summary(f"grid-{grid}", result,
                                      "thermal grid check at frozen electrical losses"))
                output.write_text(json.dumps(checks, indent=2) + "\n")
                print(f"grid {grid}:", result.thermal.t_max, "C", flush=True)
    print("Validation artifact:", output)


if __name__ == "__main__":
    main()
