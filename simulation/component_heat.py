"""Explicit, fixed component power deposited at PCB pads in the pinned KiPI model.

This models a chosen heat input to the board, not a package or junction temperature.
It does not add electrical current through the external relay-control harness.
"""

import json
import logging
from pathlib import Path


def source_path(board):
    board = Path(board)
    return board.with_name(board.stem + ".component-heat.json")


def board_path(snap):
    """KiPI's file field names a saved snapshot, not a native PCB source."""
    if snap.project_dir and snap.board_name:
        return Path(snap.project_dir) / snap.board_name
    return Path(snap.file) if snap.file else None


def read_model(snap):
    board = board_path(snap)
    path = source_path(board) if board else None
    if path is None or not path.is_file():
        return {"sources": [], "connectors": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"sources": data, "connectors": []} if isinstance(data, list) else data


def validate(sources, pads_by_ref):
    import math

    names = set()
    for source in sources:
        name = source["name"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Component heat sources need unique, nonempty names")
        names.add(name)
        ref, pins = source["ref"], source["pins"]
        if not isinstance(pins, list) or not pins or any(not isinstance(p, str) for p in pins):
            raise ValueError(f"{name}: specify pad numbers as a nonempty list of strings")
        if ref not in pads_by_ref or set(pins) - pads_by_ref[ref]:
            raise ValueError(f"{name}: component/pads do not match the board")
        for key in ("power_w", "board_fraction"):
            value = source[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name}: {key} must be a finite number")
            if value < 0 or (key == "board_fraction" and value > 1):
                raise ValueError(f"{name}: invalid {key}")
        if source.get("thermal"):
            from thermal_network import validate_parameters
            validate_parameters(source["thermal"])


def arrays(snap, sources):
    from kipi.dc.thermal.cosim import _Heat

    pads = {}
    for pad in snap.pads:
        pads.setdefault(pad.footprint, set()).add(pad.number)
    validate(sources, pads)
    heat = _Heat(snap)
    for source in sources:
        selected = [pad.id for pad in snap.pads
                    if pad.footprint == source["ref"] and pad.number in source["pins"]]
        heat.add_pads(source.get("category", "Fixed component heat"), selected,
                      source["power_w"] * source["board_fraction"])
    return (*heat.arrays(), heat.by_kind)


def install(expected_board=None):
    """Extend KiPI's heat map; leave its electrical solve and vendor files unchanged."""
    import numpy as np
    from kipi.dc.thermal import cosim
    from connector_model import connector_rows, heat_inputs, install_report

    original = cosim.heat_sources

    def combined(tree, snap, setup, thermal=None):
        xy, watts, layers, kinds = original(tree, snap, setup, thermal)
        current_board = board_path(snap)
        if expected_board and current_board and current_board.resolve() == Path(expected_board).resolve():
            if not source_path(current_board).is_file():
                raise ValueError("Required component model is missing; refusing to omit its heat")
        data = read_model(snap)
        sources = data.get("sources", []) + heat_inputs(connector_rows(tree, setup, data))
        extra_xy, extra_watts, extra_layers, extra_kinds = arrays(snap, sources)
        expected = sum(s["power_w"] * s["board_fraction"] for s in sources)
        if not np.isclose(extra_watts.sum(), expected, rtol=1e-10, atol=1e-10):
            raise ValueError("Component/contact heat was not conserved; refusing to continue")
        kinds = dict(kinds)
        for name, value in extra_kinds.items():
            kinds[name] = kinds.get(name, 0.0) + value
        if sources:
            logging.getLogger(__name__).info(
                "Additional board heat actually applied: %s; total %.6f W",
                extra_kinds, float(extra_watts.sum()))
        return (np.vstack([xy, extra_xy]), np.concatenate([watts, extra_watts]),
                np.concatenate([layers, extra_layers]), kinds)

    cosim.heat_sources = combined
    original_solve = cosim.solve_electrothermal

    def solve(snap, setup, thermal, progress=None):
        data = read_model(snap)
        if data.get("thermal_model", {}).get("mode") in ("compact", "finite_area_stress", "board_reference"):
            from researched_cosim import solve as researched_solve
            from kipi.core.progress import NULL
            return researched_solve(snap, setup, thermal, data, progress or NULL)
        return original_solve(snap, setup, thermal, progress)

    cosim.solve_electrothermal = solve
    install_report(read_model)


def main():
    import sys

    kipi, board = sys.argv[1:]
    sys.path.insert(0, str(Path(kipi).resolve()))
    if not source_path(board).is_file():
        raise ValueError("Required component model is missing")
    install(expected_board=board)
    print("Thermal extension enabled. Check the report's model status and parameter assumptions.", flush=True)
    from kipi.__main__ import main as app
    return app([board])


if __name__ == "__main__":
    import sys
    sys.exit(main())
