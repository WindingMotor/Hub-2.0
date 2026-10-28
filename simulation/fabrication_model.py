"""Explicit fabrication assumptions, applied to a runtime copy of the snapshot."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
import math

_material = ContextVar("hub_laminate", default=None)


def validate(config):
    if config is None:
        return
    for key in ("k_in_plane_w_mk", "k_through_w_mk"):
        value = config["laminate"].get(key)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Fabrication laminate {key} must be finite and positive")
    via = config["vias"]
    if not isinstance(via.get("epoxy_filled_capped"), bool):
        raise ValueError("Fabrication epoxy_filled_capped must be boolean")
    if via.get("fill") != "nonconductive":
        raise ValueError("This fabrication model supports nonconductive epoxy only")
    for key in ("max_filled_drill_mm", "cap_minimum_mm"):
        value = via.get(key)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Fabrication {key} must be finite and positive")


@contextmanager
def activated(snap, config):
    if not config:
        yield snap
        return
    validate(config)
    from kipi.dc.thermal import materials
    if not getattr(materials.lookup, "_hub_fabrication", False):
        original = materials.lookup

        def lookup(name):
            spec = _material.get()
            if spec and name == spec["name"]:
                return materials.Dielectric(name, spec["status"], spec["k_in_plane_w_mk"],
                                             True, 0.0, spec["k_through_w_mk"])
            return original(name)

        lookup._hub_fabrication = True
        materials.lookup = lookup
    laminate = config["laminate"]
    # Thicknesses and electrical permittivity remain the saved board values.
    stackup = replace(snap.stackup, dielectrics=[replace(d, material=laminate["name"], k_w_mk=0.0)
                                               for d in snap.stackup.dielectrics])
    via_spec = config["vias"]
    vias = [replace(v, filled=True) if via_spec["epoxy_filled_capped"]
            and v.drill_mm <= via_spec["max_filled_drill_mm"] else v for v in snap.vias]
    adjusted = replace(snap, stackup=stackup, vias=vias)
    token = _material.set(laminate)
    try:
        yield adjusted
    finally:
        _material.reset(token)
