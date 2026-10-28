"""Finite-area PCB coupling and energy-conserving compact thermal nodes.

For each component node: P = (Tc-Tb)/Rb + Ga*(Tc-Tsink).
The board responds to Qb=(Tc-Tb)/Rb. Elimination of the small component
network uses the existing board factorization; no vendor code is changed.
Thermal resistances are explicit model inputs, not package-independent truths.
"""

import math


def validate_parameters(parameters):
    for key in ("r_board_k_w", "r_air_k_w"):
        value = parameters.get(key)
        if key == "r_air_k_w" and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Compact thermal {key} must be an explicit positive K/W value")
    if not parameters.get("status"):
        raise ValueError("Compact thermal parameters need a calibration/sensitivity status")
    if parameters.get("wire"):
        wire = parameters["wire"]
        for key in ("copper_area_mm2", "outer_diameter_mm", "insulation_k_w_mk",
                    "surface_h_w_m2k", "copper_k_w_mk", "ohm_per_m_20c", "tcr_per_c"):
            value = wire[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Wire thermal {key} must be positive and finite")


def wire_fin(model, amps, ambient):
    """Insulated, uniform-current wire with an adiabatic far end.

    The fin reference temperature includes the wire's distributed I²R heating;
    the harness is not treated as an unlimited ambient-temperature heatsink.
    """
    length = model["length_m"]
    if length <= 0:
        return 0.0, ambient, 0.0
    area = model["copper_area_mm2"] * 1e-6
    radius = math.sqrt(area / math.pi)
    outer = model["outer_diameter_mm"] * .0005
    if outer <= radius:
        raise ValueError("Wire insulation diameter must exceed copper diameter")
    radial = math.log(outer / radius) / (2 * math.pi * model["insulation_k_w_mk"])
    radial += 1 / (model["surface_h_w_m2k"] * 2 * math.pi * outer)
    g_per_m = 1 / radial
    ka = model["copper_k_w_mk"] * area
    conductance = math.sqrt(ka * g_per_m) * math.tanh(length * math.sqrt(g_per_m / ka))
    r20 = model["ohm_per_m_20c"]
    alpha = model["tcr_per_c"]
    denominator = 1 - amps * amps * r20 * alpha / g_per_m
    if denominator <= 0:
        raise ValueError("Wire model has no stable constant-h steady state at this current")
    watts_per_m = amps * amps * r20 * (1 + alpha * (ambient - 20)) / denominator
    return conductance, ambient + watts_per_m / g_per_m, watts_per_m * length


def node_balance(power, board_temperature, ambient, parameters, amps=0):
    """Return Gb, Ga, ambient-referenced external forcing, and wire generated heat."""
    gb = 1 / parameters["r_board_k_w"]
    ga = 0.0 if parameters.get("r_air_k_w") is None else 1 / parameters["r_air_k_w"]
    forcing = 0.0
    wire_w = 0.0
    if parameters.get("wire"):
        gw, sink, wire_w = wire_fin(parameters["wire"], amps, ambient)
        ga += gw
        forcing += gw * (sink - ambient)
    return gb, ga, forcing, wire_w


class PadAreas:
    """Area-overlap weights on actual outer-layer pad copper, excluding drill voids."""

    def __init__(self, model, snap):
        self.model, self.snap, self.cache = model, snap, {}

    def weight(self, pad_ids):
        import numpy as np
        from kipi.core.geometry.copper import poly_to_shapely
        import shapely

        key = tuple(sorted(pad_ids))
        if key in self.cache:
            return self.cache[key]
        m = self.model
        result = m.empty_heat()
        selected = [p for p in self.snap.pads if p.id in key]
        outer_ids = {m.layers[0], m.layers[-1]}
        for p in selected:
            for lid, polys in p.shapes.items():
                if lid not in outer_ids:
                    continue
                shapes = [poly_to_shapely(poly) for poly in polys]
                geometry = shapely.union_all([g for g in shapes if g is not None])
                if geometry.is_empty:
                    continue
                # KiPI pad shapes may include the drill as solid copper. Do not put heat there.
                if p.pad_type == "pth" and min(p.drill_mm) > 0:
                    hole = shapely.Point(*p.position).buffer(min(p.drill_mm) / 2, quad_segs=24)
                    geometry = geometry.difference(hole)
                minx, miny, maxx, maxy = geometry.bounds
                js = np.flatnonzero((m.x + m.d / 2 > minx) & (m.x - m.d / 2 < maxx))
                ii = np.flatnonzero((m.y + m.d / 2 > miny) & (m.y - m.d / 2 < maxy))
                layer_index = m.layers.index(lid)
                for i in ii:
                    for j in js:
                        if not m.inside[i, j]:
                            continue
                        cell = shapely.box(m.x[j]-m.d/2, m.y[i]-m.d/2,
                                           m.x[j]+m.d/2, m.y[i]+m.d/2)
                        result[layer_index, i, j] += geometry.intersection(cell).area
        total = float(result.sum())
        if total <= 0:
            raise ValueError(f"No outer-layer copper area for thermal attachment {key}")
        result /= total
        self.cache[key] = result
        return result


class CompactBoard:
    """Couple component nodes to a linear board Green's function using a small solve."""

    def __init__(self, board_model, snap):
        self.board = board_model
        self.pads = PadAreas(board_model, snap)
        self.responses = {}

    def solve(self, board_heat, nodes, tolerance=.01, max_iterations=100):
        import numpy as np
        m = self.board
        ambient = m.settings.ambient_c
        base = m.solve(board_heat)
        if not nodes:
            return base, []
        weights = [self.pads.weight(n["pad_ids"]) for n in nodes]
        vectors = [w[:, m.inside].T.ravel() for w in weights]
        responses = []
        for n, w in zip(nodes, weights):
            key = tuple(sorted(n["pad_ids"]))
            if key not in self.responses:
                self.responses[key] = (m.solve(w) - ambient)[:, m.inside].T.ravel()
            responses.append(self.responses[key])
        W = np.column_stack(vectors)
        U = np.column_stack(responses)
        influence = W.T @ U
        u0 = (base - ambient)[:, m.inside].T.ravel()
        tb0 = W.T @ u0
        old = np.full(len(nodes), ambient)
        for iteration in range(max_iterations):
            powers, gbs, gas, forces, wire_powers = [], [], [], [], []
            for node, temp in zip(nodes, old):
                power = node["power_w"]
                if node.get("coil"):
                    coil = node["coil"]
                    resistance = coil["cold_ohm"] * (1 + coil["tcr_per_c"] * (temp-coil["reference_c"]))
                    power = coil["voltage_v"]**2 / resistance
                gb, ga, forcing, wire_w = node_balance(power, ambient, ambient,
                                                       node["thermal"], node.get("amps", 0))
                powers.append(power); gbs.append(gb); gas.append(ga)
                forces.append(forcing); wire_powers.append(wire_w)
            p, gb, ga, forcing = map(np.asarray, (powers, gbs, gas, forces))
            beta = gb / (gb + ga)
            effective_g = gb * ga / (gb + ga)
            # Positive Qb heats the board; negative Qb is component/wire cooling of the board.
            q = np.linalg.solve(np.eye(len(nodes)) + effective_g[:, None] * influence,
                                beta * (p+forcing) - effective_g * tb0)
            tb = ambient + tb0 + influence @ q
            temperatures = ambient + (p+forcing+gb*(tb-ambient)) / (gb+ga)
            if np.max(np.abs(temperatures-old)) < tolerance:
                break
            old = .5 * (old + temperatures)
        else:
            raise ValueError("Compact thermal network failed to converge")
        result = np.full_like(base, np.nan)
        result[:, m.inside] = (ambient + u0 + U @ q).reshape(-1, len(m.layers)).T
        rows = []
        for index, node in enumerate(nodes):
            external = ga[index] * (temperatures[index]-ambient) - forcing[index]
            error = p[index] - q[index] - external
            if abs(error) > 1e-8 * max(1, abs(p[index])):
                raise ValueError("Compact thermal network energy imbalance")
            rows.append({"name": node["name"], "category": node["category"],
                         "component_node_c": float(temperatures[index]),
                         "attachment_mean_c": float(tb[index]),
                         "generated_w": float(p[index]), "to_board_w": float(q[index]),
                         "to_external_w": float(external), "wire_generated_w": wire_powers[index],
                         "energy_error_w": float(error),
                         "parameter_status": node["thermal"].get("status", "uncalibrated")})
        return result, rows
