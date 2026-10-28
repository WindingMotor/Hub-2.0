"""KiPI electrical solves coupled to finite pad areas and compact component nodes."""

import time
import numpy as np

from thermal_network import CompactBoard


def solve(snap, setup, thermal, data, progress):
    from solder_reinforcement import activated
    from fabrication_model import activated as fabrication

    with fabrication(snap, data.get("fabrication")) as adjusted:
        with activated(adjusted, data.get("solder_reinforcement")) as solder:
            return _solve(adjusted, setup, thermal, data, progress, solder)


def _solve(snap, setup, thermal, data, progress, solder):
    from kipi.dc.pi.tree import solve_tree
    from kipi.dc.thermal.model import BoardThermalModel
    from kipi.dc.thermal.cosim import ThermalResult, _Heat
    from component_heat import validate
    from connector_model import connector_rows

    started = time.perf_counter()
    if thermal.load_power:
        raise ValueError("External-load power must be off for the hub component model")
    mode = data["thermal_model"]["mode"]
    if data.get("fabrication", {}).get("vias", {}).get("epoxy_filled_capped"):
        # A copper-filled rule would wrongly turn an epoxy core into a conductor.
        if any(rule.fill != "nonconductive" for rule in setup.settings.via_rules if rule.kind != "pth"):
            raise ValueError("Epoxy-filled fabrication requires nonconductive via fill rules")
        progress.info("Fabrication: epoxy-filled/capped vias; copper barrels carry current. "
                      "Cap disks and epoxy-core thermal corrections are unresolved below the grid; "
                      "no extra copper/fill conductance credited. Via-in-pad locations come from saved PCB.")
    model = BoardThermalModel(snap, thermal, progress, setup.settings.conductor_by_layer,
                              setup.settings.via_rules)
    solder.thermal(model, progress)
    network = CompactBoard(model, snap)
    pad_lookup = {}
    for pad in snap.pads:
        pad_lookup.setdefault(pad.footprint, set()).add(pad.number)
    validate(data.get("sources", []), pad_lookup)

    def ids(ref, numbers):
        result = [p.id for p in snap.pads if p.footprint == ref and p.number in numbers]
        if not result:
            raise ValueError(f"No thermal attachment pads for {ref} {numbers}")
        return result

    temps = np.full_like(model.empty_heat(), thermal.ambient_c)
    temps[:, ~model.inside] = np.nan
    history, mesh_cache, factor_cache = [], {}, {}
    for iteration in range(thermal.iterations):
        progress.check_cancel()
        progress.stage(f"Researched electro-thermal iteration {iteration+1}/{thermal.iterations}")
        tree = solve_tree(snap, setup, progress, temperature=model.sampler(temps),
                          mesh_cache=mesh_cache, factor_cache=factor_cache)
        heat = model.empty_heat()
        kinds = {}

        def finite_power(category, pad_ids, power):
            if power:
                heat[:] += network.pads.weight(pad_ids) * power
                kinds[category] = kinds.get(category, 0) + power

        # Keep KiPI's spatial copper loss fields; replace its point-at-pad series heat.
        copper = _Heat(snap)
        for group in tree.groups.values():
            result = group.result
            solder_power = getattr(result.fields, "solder_power", 0.0)
            positions = result.mesh.points[result.mesh.tris].mean(axis=1)
            copper.add_field("copper", positions,
                             np.nan_to_num(result.fields.tri_power-solder_power), result.mesh.tri_layer)
            if np.any(solder_power):
                copper.add_field("Added solder", positions, np.nan_to_num(solder_power), result.mesh.tri_layer)
            for via in result.fields.vias:
                copper.add_hole("vias", via.owner_id, via.position, via.power)
            for element, report in zip(result.solution.series_elements, result.fields.series):
                link = result.solution.problem.series[element.link]
                pad_ids = ([pid for group in link.groups for pid in group] if link.groups
                           else link.pads_a + link.pads_b)
                finite_power("DC connections (finite pad area)", pad_ids, report.power)
        xy, watts, layers = copper.arrays()
        model.deposit(heat, xy, watts, layers)
        kinds.update(copper.by_kind)

        nodes = []
        if mode != "board_reference":
            for source in data.get("sources", []):
                pad_ids = ids(source["ref"], source["pins"])
                if mode == "compact" and source.get("thermal"):
                    nodes.append({"name": source["name"], "category": source["category"],
                                  "pad_ids": pad_ids, "power_w": source["power_w"],
                                  "thermal": source["thermal"], "coil": source.get("coil")})
                else:
                    finite_power(source["category"], pad_ids,
                                 source["power_w"] * source["board_fraction"])
            by_load = {m["load"]: m for m in data.get("connectors", [])}
            for row in connector_rows(tree, setup, data):
                connector = by_load[row["load"]]
                for side in ("supply", "return"):
                    attachment = row[side]
                    pad_ids = ids(attachment["ref"], attachment["pins"])
                    category = "DT contacts (compact network)"
                    power = row[f"{side}_contact_w"]
                    if mode == "compact":
                        parameters = dict(connector["thermal"])
                        parameters["wire"] = dict(parameters["wire"],
                                                   length_m=connector[f"{side}_wire_m"])
                        nodes.append({"name": f"{row['load']} DT {side}", "category": category,
                                      "pad_ids": pad_ids, "power_w": power,
                                      "thermal": parameters, "amps": row["current_a"]})
                    else:
                        finite_power("DT contacts (all-to-board stress)", pad_ids,
                                     power * connector["board_fraction"])
        new, node_rows = network.solve(heat, nodes)
        for row in node_rows:
            kinds[row["category"]] = kinds.get(row["category"], 0) + row["to_board_w"]
        board_power = float(heat.sum()) + sum(r["to_board_w"] for r in node_rows)
        error = abs(board_power - sum(kinds.values()))
        if error > 1e-7:
            raise ValueError("Board heat accounting failed")
        change = float(np.nanmax(np.abs(new-temps)))
        temps = new
        history.append({"iteration": iteration+1, "heat_w": board_power,
                        "t_max": float(np.nanmax(temps)), "dt_max": change})
        progress.info(f"Finite-area model ({mode}): {board_power:.6f} W net into PCB; "
                      f"peak {np.nanmax(temps):.2f} C; max change {change:.4f} C")
        for row in node_rows:
            progress.info(f"  {row['name']}: generated {row['generated_w']:.4f} W, "
                          f"to board {row['to_board_w']:.4f} W, "
                          f"to air/wire {row['to_external_w']:.4f} W, "
                          f"node {row['component_node_c']:.2f} C (uncalibrated)")
    tree.thermal = ThermalResult(thermal, model.x, model.y, temps, history,
                                 heat_w=board_power, heat_by_kind=kinds,
                                 dielectrics=model.dielectrics, layers=model.layers)
    tree.thermal.compact_nodes = node_rows
    tree.thermal.model_status = data["thermal_model"]["status"]
    tree.thermal.model_mode = mode
    tree.thermal.solder_reinforcement = solder.config
    tree.thermal.fabrication = data.get("fabrication")
    tree.solve_s = time.perf_counter() - started
    tree.warnings.append(f"Thermal model: {data['thermal_model']['status']}. "
                         "Component thermal resistances are explicit sensitivity inputs, not measured data.")
    if data.get("fabrication"):
        tree.warnings.append("Fabrication: Nan Ya NP-155F identity recorded; thermal conductivity is an "
                             "explicit generic FR4 estimate, not published NP-155F data. Epoxy is electrically "
                             "nonconductive; cap disks and exact epoxy-core thermal conduction are not resolved. "
                             "No solid-copper fill or added via-in-pad locations are assumed.")
    if solder.regions:
        tree.warnings.append("Solder reinforcement enabled: selected outer copper has a perfectly bonded, "
                             "homogenized solder sheet. Coverage ignores actual mask openings. Copper geometry, "
                             "via plating and surface cooling are unchanged; the 3D shape does not show solder. "
                             "Current-density map is copper only; native sheet-loss tables include copper+solder.")
    if history[-1]["dt_max"] > .5:
        tree.warnings.append("Thermal iteration changed >0.5 C; increase iterations before comparison")
    return tree
