"""Selective solder sheets, perfectly bonded to existing outer-layer copper.

No vendor files or board geometry are changed. Electrical assembly adds a parallel
sheet to selected triangles; thermal assembly adds k*t to selected outer cells.
Coverage is a homogenized thickness multiplier, not a spatial mask or bead shape.
"""

from contextlib import contextmanager
from contextvars import ContextVar
import math

_active = ContextVar("hub_solder_reinforcement", default=None)


def validate(config, nets, layers):
    if config is None:
        return
    if not isinstance(config, dict) or not isinstance(config.get("enabled"), bool):
        raise ValueError("solder_reinforcement needs a boolean enabled")
    material = config.get("material", {})
    for key in ("rho_ohm_mm_20c", "thermal_k_w_mk", "tcr_per_c"):
        value = material.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Solder {key} must be a finite number")
        if value < 0 or (key != "tcr_per_c" and value == 0):
            raise ValueError(f"Invalid solder {key}")
    regions = config.get("regions")
    if not isinstance(regions, list) or not regions:
        raise ValueError("Solder regions must be a nonempty list")
    seen = set()
    for region in regions:
        layer = region.get("layer")
        if layer not in ("F.Cu", "B.Cu") or layer not in layers:
            raise ValueError(f"Solder requires an existing outer copper layer: {layer}")
        selected = region.get("nets")
        if not isinstance(selected, list) or not selected:
            raise ValueError("Solder region needs explicit net names")
        for net in selected:
            if not isinstance(net, str) or net not in nets:
                raise ValueError(f"Solder net does not match the board: {net}")
            if (layer, net) in seen:
                raise ValueError(f"Duplicate solder layer/net: {layer} {net}")
            seen.add((layer, net))
        for key, lower, upper in (("thickness_mm", 0, None), ("coverage_fraction", 0, 1)):
            value = region.get(key)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < lower or (upper is not None and value > upper)):
                raise ValueError(f"Invalid solder {key}")


class Reinforcement:
    def __init__(self, snap, config):
        import shapely
        from kipi.core.geometry.copper import net_layer_copper

        validate(config, {n.name for n in snap.nets}, {c.name for c in snap.stackup.copper})
        self.config = config or {}
        self.material = self.config.get("material", {})
        self.regions = []
        if not self.config.get("enabled", False):
            return
        for region in self.config["regions"]:
            lid = next(c.id for c in snap.stackup.copper if c.name == region["layer"])
            geometries = [net_layer_copper(snap, net, lid) for net in region["nets"]]
            if any(g.is_empty for g in geometries):
                raise ValueError(f"Solder region has no saved copper on {region['layer']}")
            geometry = shapely.union_all(geometries)
            shapely.prepare(geometry)
            self.regions.append((lid, geometry, region["thickness_mm"] * region["coverage_fraction"]))

    def thickness(self, xy, layers):
        import numpy as np
        import shapely

        out = np.zeros(len(xy))
        for lid, geometry, thickness in self.regions:
            selected = np.broadcast_to(layers, (len(xy),)) == lid
            if np.any(selected):
                out[selected] += thickness * shapely.intersects_xy(geometry, xy[selected, 0], xy[selected, 1])
        return out

    def electrical(self, snap, mesh, problem, assembled):
        import numpy as np
        import scipy.sparse as sp
        from kipi.core.temperature import at
        from kipi.dc.solver.fem import triangle_geometry

        xy = mesh.points[mesh.tris].mean(axis=1)
        thickness = self.thickness(xy, mesh.tri_layer)
        if not np.any(thickness):
            return assembled
        K, merged, nm, sheet_g, barrels, pads, series, factor = assembled
        copper_factor = np.broadcast_to(1.0 if factor is None else factor, (len(xy),)).copy()
        temp = at(problem.temperature, xy, mesh.tri_layer) if problem.temperature is not None else 20.0
        solder_factor = np.maximum(1 + self.material["tcr_per_c"] * (temp - 20), .05)
        extra_g = thickness / (self.material["rho_ohm_mm_20c"] * solder_factor)
        base_g = np.array([sheet_g[lid] for lid in mesh.tri_layer])
        # Native postprocessing uses base_g/factor: preserve exact total Joule loss.
        effective_factor = base_g / (base_g / copper_factor + extra_g)
        b, c, two_a = triangle_geometry(mesh.points, mesh.tris)
        coefficient = extra_g / (2 * np.abs(two_a))
        ke = coefficient[:, None, None] * (b[:, :, None]*b[:, None, :] + c[:, :, None]*c[:, None, :])
        m = merged[mesh.tris]
        delta = sp.coo_matrix((ke.ravel(), (np.repeat(m, 3, axis=1).ravel(),
                                           np.tile(m, (1, 3)).ravel())), shape=(nm, nm)).tocsr()
        problem._hub_solder_fields = {"copper_factor": copper_factor, "extra_g": extra_g,
                                     "thickness_mm": thickness}
        return K + delta, merged, nm, sheet_g, barrels, pads, series, effective_factor

    def thermal(self, model, progress):
        import numpy as np
        import scipy.sparse as sp
        from kipi.core.solver import direct

        if not self.regions:
            return
        X, Y = np.meshgrid(model.x, model.y)
        xy = np.column_stack([X.ravel(), Y.ravel()])
        for li, lid in enumerate(model.layers):
            t = self.thickness(xy, lid).reshape(X.shape)
            model.g[li] += t * self.material["thermal_k_w_mk"] * 1e-3
        # Rebuild the native matrix with amended in-plane conductances. Vertical
        # laminate, plating, outer surface area and convection stay as imported.
        nl, ny, nx = model.g.shape
        idx = np.full((ny, nx), -1, dtype=int)
        idx[model.inside] = np.arange(model.inside.sum())
        n = int(model.inside.sum()) * nl
        rows, cols, values = [], [], []
        diagonal = model.g_conv[:, model.inside].T.ravel().copy()

        def couple(a, b, g):
            rows.extend([a, b]); cols.extend([b, a]); values.extend([-g, -g])
            np.add.at(diagonal, a, g)
            np.add.at(diagonal, b, g)

        for li, gl in enumerate(model.g):
            for di, dj in ((0, 1), (1, 0)):
                a, b = idx[:ny-di, :nx-dj], idx[di:, dj:]
                ga, gb = gl[:ny-di, :nx-dj], gl[di:, dj:]
                ok = (a >= 0) & (b >= 0)
                couple(a[ok]*nl+li, b[ok]*nl+li, (2*ga*gb/(ga+gb))[ok])
        cells = idx[model.inside]
        for li, gv in enumerate(model.g_vertical):
            couple(cells*nl+li, cells*nl+li+1, gv[model.inside])
        matrix = sp.coo_matrix((np.concatenate(values+[diagonal]),
                               (np.concatenate(rows+[np.arange(n)]),
                                np.concatenate(cols+[np.arange(n)]))), shape=(n, n)).tocsc()
        model._solve = direct.factorize(matrix, progress.warn)
        progress.info("Solder reinforcement: selective outer-layer k*t added; "
                      "perfect bond, uniform effective thickness, original surface cooling retained")


def install():
    """Install once; ContextVar limits assembly changes to the current solve."""
    from kipi.dc.solver import fem, post
    import kipi.dc.solver as solver
    from kipi.dc.pi import tree
    if getattr(fem.assemble, "_hub_solder", False):
        return
    original_assemble, original_solve = fem.assemble, fem.LinearSystem.solve
    original_fields = post.compute_fields

    def assemble(snap, mesh, problem):
        problem.__dict__.pop("_hub_solder_fields", None)
        result = original_assemble(snap, mesh, problem)
        active = _active.get()
        return active.electrical(snap, mesh, problem, result) if active else result

    def solve(self, *args, **kwargs):
        result = original_solve(self, *args, **kwargs)
        result.solder_reinforcement = getattr(self.problem, "_hub_solder_fields", None)
        return result

    def fields(sol, *args, **kwargs):
        import numpy as np
        result = original_fields(sol, *args, **kwargs)
        extra = getattr(sol, "solder_reinforcement", None)
        if extra:
            rho = np.array([sol.layer_rho.get(l, sol.problem.settings.rho_ohm_mm)
                            for l in sol.mesh.tri_layer])
            # The map means COPPER A/mm², not total current divided by copper area.
            result.j_density = np.linalg.norm(result.grad, axis=1) / (rho * extra["copper_factor"])
            result.summary["j_max"] = float(result.j_density.max())
            power = extra["extra_g"] * (result.grad**2).sum(axis=1) * result.tri_area
            result.solder_power = power
            result.solder_j_density = np.divide(
                np.linalg.norm(result.grad, axis=1)*extra["extra_g"], extra["thickness_mm"],
                out=np.zeros_like(power), where=extra["thickness_mm"] > 0)
            result.summary["power_solder"] = float(power.sum())
            result.summary["power_copper_only"] = float(result.tri_power.sum()-power.sum())
        return result

    assemble._hub_solder = True
    fem.assemble = assemble
    fem.LinearSystem.solve = solve
    post.compute_fields = solver.compute_fields = tree.compute_fields = fields


@contextmanager
def activated(snap, config):
    install()
    reinforcement = Reinforcement(snap, config)
    token = _active.set(reinforcement)
    try:
        yield reinforcement
    finally:
        _active.reset(token)
