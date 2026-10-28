"""Lumped DT mating-contact losses for fixed-current loads, separate from PCB FEA.

KiPI's load table remains referenced at PCB pads. The supplemental report estimates
voltage beyond the mating contacts and any explicitly configured harness length.
"""

from html import escape
import json
import math
from pathlib import Path


def validate(connectors, loads):
    loads = {load["name"]: load for load in loads}
    seen = set()
    for model in connectors:
        name = model["load"]
        if name not in loads or name in seen:
            raise ValueError(f"Unknown or duplicate connector load: {name}")
        seen.add(name)
        for key in ("supply_contact_ohm", "return_contact_ohm", "board_fraction",
                    "supply_wire_m", "return_wire_m", "wire_ohm_per_m_20c", "max_contact_a"):
            value = model[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name}: {key} must be finite")
            if value < 0 or (key == "board_fraction" and value > 1):
                raise ValueError(f"{name}: invalid {key}")
        if not math.isfinite(model["wire_temperature_c"]) or model["wire_temperature_c"] < -273.15:
            raise ValueError(f"{name}: invalid wire_temperature_c")
        load = loads[name]
        if not load.get("ground") or load.get("groups"):
            raise ValueError("Connector model needs an ungrouped load with explicit ground pads")
        if model.get("thermal"):
            from thermal_network import validate_parameters
            validate_parameters(model["thermal"])


def connector_rows(tree, setup, data):
    models = data.get("connectors", [])
    # Resolve against the *solved* current, so GUI edits cannot leave fixed-current heat behind.
    reports = {load.name: load for load in getattr(tree, "loads", [])}
    loads = {load.name: load for load in setup.loads}
    rows = []
    for model in models:
        name = model["load"]
        if name not in loads:
            raise ValueError(f"Connector model refers to removed load {name}")
        report = reports.get(name)
        if report is None:
            # Excluded net groups generate no heat in the corresponding load contacts.
            continue
        amps = abs(report.current)
        if not math.isfinite(amps) or not math.isfinite(report.v_effective):
            continue
        rs, rg = model["supply_contact_ohm"], model["return_contact_ohm"]
        wire_r = ((model["supply_wire_m"] + model["return_wire_m"])
                  * model["wire_ohm_per_m_20c"]
                  * (1 + 0.00393 * (model["wire_temperature_c"] - 20)))
        if model.get("thermal", {}).get("wire"):
            from thermal_network import wire_fin
            total_wire_w = sum(wire_fin(dict(model["thermal"]["wire"], length_m=model[key]),
                                         amps, setup.thermal.ambient_c)[2]
                               for key in ("supply_wire_m", "return_wire_m"))
            wire_r = total_wire_w / amps**2 if amps else 0.0
        drop = amps * (rs + rg + wire_r)
        load = loads[name]
        rows.append({"load": name, "current_a": amps,
                     "pcb_pad_voltage_v": report.v_effective,
                     "estimated_harness_voltage_v": report.v_effective - drop,
                     "additional_drop_v": drop,
                     "supply_contact_w": amps * amps * rs,
                     "return_contact_w": amps * amps * rg,
                     "external_wire_w": amps * amps * wire_r,
                     "board_fraction": model["board_fraction"],
                     "supply": {"ref": load.supply.ref, "pins": load.supply.pins},
                     "return": {"ref": load.ground.ref, "pins": load.ground.pins},
                     "max_contact_a": model["max_contact_a"],
                     "rating_status": "EXCEEDS catalog current" if amps > model["max_contact_a"]
                         else "AT catalog current" if amps == model["max_contact_a"]
                         else "Below catalog current (not qualification)",
                     "model_basis": model["basis"],
                     "wire_length_known": model["wire_length_known"]})
    return rows


def heat_inputs(rows):
    sources = []
    for row in rows:
        for side in ("supply", "return"):
            sources.append({"name": f"{row['load']} DT {side}",
                            **row[side], "power_w": row[f"{side}_contact_w"],
                            "board_fraction": row["board_fraction"],
                            "category": "DT contacts (board-deposited estimate)"})
    return sources


def section(rows, data, tree):
    def cell(value):
        return f"<td>{escape(str(value))}</td>"
    headers = ["Load", "A", "PCB-pad V", "Estimated harness-side V", "Added drop mV",
               "Both contacts W", "External wire W", "Rating check"]
    body = []
    for row in rows:
        values = [row["load"], f"{row['current_a']:.3f}", f"{row['pcb_pad_voltage_v']:.5f}",
                  f"{row['estimated_harness_voltage_v']:.5f}", f"{row['additional_drop_v']*1000:.3f}",
                  f"{row['supply_contact_w']+row['return_contact_w']:.4f}",
                  f"{row['external_wire_w']:.4f}", row["rating_status"]]
        body.append("<tr>" + "".join(cell(value) for value in values) + "</tr>")
    th = getattr(tree, "thermal", None)
    actual = getattr(th, "heat_by_kind", {})
    expected = sum(s["power_w"] * s["board_fraction"] for s in data.get("sources", []))
    node_rows = getattr(th, "compact_nodes", [])
    node_table = ""
    if node_rows:
        node_table = "<h3>Uncalibrated compact thermal nodes</h3><table><tr>" + "".join(
            f"<th>{escape(h)}</th>" for h in ("Node", "Node °C", "Attachment mean °C",
                                            "Generated W", "Into PCB W", "To air/wire W",
                                            "Energy residual W")) + "</tr>"
        for node in node_rows:
            values = [node["name"], f"{node['component_node_c']:.2f}",
                      f"{node['attachment_mean_c']:.2f}", f"{node['generated_w']:.5f}",
                      f"{node['to_board_w']:.5f}", f"{node['to_external_w']:.5f}",
                      f"{node['energy_error_w']:.3g}"]
            node_table += "<tr>" + "".join(cell(v) for v in values) + "</tr>"
        node_table += "</table>"
    mode = data.get("thermal_model", {}).get("mode", "legacy point-source stress")
    status = data.get("thermal_model", {}).get("status", "Legacy model; see assumptions")
    solder = getattr(th, "solder_reinforcement", None)
    solder_note = ""
    if solder and solder.get("enabled"):
        solder_note = ("<h3>Selective solder reinforcement</h3><p>Perfectly bonded outer sheet; "
                       "uniform effective thickness = thickness × coverage. Actual mask openings, bead shape, "
                       "added surface cooling and solder-filled holes are not modeled. Current density is copper-only; "
                       "native sheet-loss tables include copper and solder. Added solder loss is separately listed "
                       "in the heat breakdown. Material TCR may be an assumed sensitivity input.</p><pre>"
                       + escape(json.dumps(solder, indent=2)) + "</pre>")
    fabrication = getattr(th, "fabrication", None)
    if fabrication:
        solder_note += ("<h3>Fabrication assumptions</h3><p>Laminate identity is user supplied; "
                        "thermal conductivities remain estimates. Epoxy fill is nonconductive. "
                        "Copper caps are recorded but their disks and the epoxy-core thermal correction "
                        "are not resolved; no solid-copper via fill is assumed.</p><pre>"
                        + escape(json.dumps(fabrication, indent=2)) + "</pre>")
    return ("<h2>Component model audit and DT interface estimates</h2>"
            f"<p><strong>Thermal mode: {escape(mode)}. {escape(status)}</strong></p>"
            "<p>The native Loads table is at PCB pads. This supplemental table adds lumped "
            "supply AND return mating-contact resistance for constant-current loads. "
            "The 3D map remains PCB temperature, not contact or wire temperature. "
            "Unknown contact type uses the stamped-contact specification-limit sensitivity "
            "model, not measured typical resistance. Harness estimates use the configured lengths; "
            "the compact wire model includes its own distributed Joule heating.</p>"
            f"<p>Nominal cold component generation reference: {expected:.6f} W. "
            f"Actual thermal heat breakdown: {escape(str(actual))}. "
            "Compact mode solves a PCB/component/ambient-and-wire thermal network. Its thermal "
            "resistances are uncalibrated sensitivity inputs. Positive PCB heat enters the board; "
            "negative PCB heat is cooling. Stress mode instead forces all generation into the board. "
            "The native electrical terminal geometry remains idealized; no detailed 3D pin model is present.</p>"
            "<table><tr>" + "".join(f"<th>{escape(h)}</th>" for h in headers)
            + "</tr>" + "".join(body) + "</table>" + node_table + solder_note)


def install_report(read_model):
    from kipi.dc.report import html as report_html

    if getattr(report_html.write_report, "_hub_interfaces", False):
        return
    original = report_html.write_report

    def write(path, tree, scenes, snap, setup, progress=None):
        data = read_model(snap)
        rows = connector_rows(tree, setup, data)
        original_notes = report_html.notes_section
        report_html.notes_section = lambda pdf=False: section(rows, data, tree) + original_notes(pdf)
        try:
            result = original(path, tree, scenes, snap, setup, progress)
        finally:
            report_html.notes_section = original_notes
        audit = {"connector_estimates": rows, "configured_model": data,
                 "actual_heat_by_kind_w": getattr(getattr(tree, "thermal", None), "heat_by_kind", {}),
                 "applied_solder_reinforcement": getattr(getattr(tree, "thermal", None), "solder_reinforcement", None),
                 "applied_fabrication": getattr(getattr(tree, "thermal", None), "fabrication", None),
                 "compact_thermal_nodes": getattr(getattr(tree, "thermal", None), "compact_nodes", [])}
        Path(path).with_suffix(".interfaces.json").write_text(
            json.dumps(audit, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        return result

    write._hub_interfaces = True
    report_html.write_report = write
