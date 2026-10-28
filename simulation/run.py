#!/usr/bin/env python3
"""Snapshot the saved project, prepare its KiPI setup, and open KiPI standalone."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import urllib.request
import uuid
import zipfile

from component_heat import source_path, validate as validate_component_heat
from connector_model import validate as validate_connectors
from solder_reinforcement import validate as validate_solder
from fabrication_model import validate as validate_fabrication

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
KIPI_COMMIT = "177fa8e4f97d43f85cd06cb2f64a0235558f0819"
KIPI_SHA256 = "8e212c08847b786faf82a6abed47659b5782894216488ee49a0b5c265d56f4fe"
KIPI_URL = f"https://codeload.github.com/drewsum/KiPI/zip/{KIPI_COMMIT}"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_config(path, _parents=()):
    """Read a case, merging optional relative `extends` before its overrides.

    Objects merge recursively; arrays/scalars/null replace the inherited value.
    Existing commands naming a moved root preset still resolve into cases/.
    """
    path = Path(path).resolve()
    if not path.exists() and path.parent == HERE and (HERE / "cases" / path.name).is_file():
        path = HERE / "cases" / path.name
    if path in _parents:
        raise ValueError(f"Circular config inheritance: {path}")
    def duplicate_check(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate config key: {key}")
            result[key] = value
        return result

    config = json.loads(path.read_text(encoding="utf-8-sig"),
                        object_pairs_hook=duplicate_check)
    if not isinstance(config, dict):
        raise ValueError("Simulation config must be a JSON object")
    parent = config.pop("extends", None)
    if parent is not None:
        if not isinstance(parent, str) or not parent or Path(parent).is_absolute():
            raise ValueError("extends must be a relative config filename")
        config = merge_config(read_config(path.parent / parent, (*_parents, path)), config)
    if config.get("config_version") != 1:
        raise ValueError("Expected config_version: 1")
    return config


def merge_config(base, overrides):
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def board_tree(path):
    """Read S-expressions for terminal checks; KiPI handles the simulation geometry."""
    stack, root = [], None
    for match in re.finditer(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+',
                             path.read_text(encoding="utf-8")):
        token = match.group()
        if token == "(":
            node = []
            if stack:
                stack[-1].append(node)
            elif root is not None:
                raise ValueError("Multiple PCB roots")
            else:
                root = node
            stack.append(node)
        elif token == ")":
            if not stack:
                raise ValueError("Unbalanced PCB file")
            stack.pop()
        else:
            if not stack:
                raise ValueError("Invalid PCB file")
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if stack or not root or root[0] != "kicad_pcb":
        raise ValueError("Incomplete or invalid KiCad PCB file")
    return root


def children(node, tag):
    return [item for item in node if isinstance(item, list) and item and item[0] == tag]


def number(value, label, minimum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    if (minimum is not None and value < minimum) or (positive and value <= 0):
        raise ValueError(f"Invalid {label}: {value}")


def validate_setup(setup, tree):
    pads = {}
    for fp in children(tree, "footprint"):
        ref = next((p[2] for p in children(fp, "property") if p[1] == "Reference"), None)
        for pad in children(fp, "pad"):
            nets = children(pad, "net")
            if nets:
                pads.setdefault((ref, nets[0][-1]), set()).add(pad[1])

    nets = setup.get("nets", [])
    if not nets or len(nets) != len(set(nets)):
        raise ValueError("setup.nets must be a nonempty list without duplicates")
    available = {net for _, net in pads}
    if set(nets) - available:
        raise ValueError(f"Nets missing from PCB: {sorted(set(nets) - available)}")

    def pin(value):
        if not isinstance(value, dict):
            raise ValueError("Every terminal needs ref, net, and pins")
        key = (value.get("ref"), value.get("net"))
        selected = value.get("pins", [])
        if not isinstance(selected, list) or any(not isinstance(p, str) for p in selected):
            raise ValueError(f"Pad numbers must be strings: {value}")
        if key not in pads or set(selected) - pads.get(key, set()):
            raise ValueError(f"Terminal does not match the current PCB: {value}")
        if key[1] not in nets:
            raise ValueError(f"Terminal net is missing from setup.nets: {value}")

    warnings = []
    if len(setup.get("vrms", [])) != 1 or setup["vrms"][0].get("kind") != "source":
        raise ValueError("This launcher expects one ideal battery source (vrms.kind = source)")
    source = setup["vrms"][0]
    pin(source["output"])
    pin(source["ground"])
    number(source["voltage"], "source voltage", positive=True)
    names = set()
    for kind in ("loads", "links"):
        for item in setup.get(kind, []):
            name = item["name"]
            if name in names:
                raise ValueError(f"Duplicate load/link name: {name}")
            names.add(name)
            if kind == "loads":
                pin(item["supply"])
                if item.get("ground"):
                    pin(item["ground"])
                number(item["current"], f"{name} current (A)", minimum=0)
                if item.get("groups"):
                    raise ValueError("Use separate loads instead of pin groups in this config")
            else:
                pin(item["side_a"])
                pin(item["side_b"])
                number(item["resistance"], f"{name} resistance (ohms)", minimum=0)
                if item["resistance"] == 0:
                    warnings.append(f"{name}: ideal 0-ohm link; its contact/fuse heating is omitted.")
    if not any(item["current"] > 0 for item in setup.get("loads", [])):
        warnings.append("All load currents are zero. Enter measured/design currents before solving.")
    thermal = setup["thermal"]
    number(thermal["ambient_c"], "ambient temperature", minimum=-273.15)
    number(thermal["airflow_m_s"], "airflow", minimum=0)
    number(thermal["grid_mm"], "thermal grid", minimum=0)
    iterations = thermal["iterations"]
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 1:
        raise ValueError("thermal.iterations must be an integer >= 1")
    if not isinstance(thermal["enabled"], bool) or not isinstance(thermal["load_power"], bool):
        raise ValueError("thermal.enabled and thermal.load_power must be true or false")
    if thermal["load_power"]:
        warnings.append("load_power=true deposits external loads' delivered power on the PCB.")
    for key in ("max_temp_c", "max_rise_c"):
        if thermal.get(key) is not None:
            number(thermal[key], key, minimum=0 if key == "max_rise_c" else -273.15)
    for key in ("max_edge_mm", "plating_mm"):
        number(setup["settings"][key], key, positive=True)
    stackup = setup.get("stackup")
    if stackup:
        layers = children(tree, "layers")[0]
        copper = [layer[1] for layer in layers[1:] if layer[1].endswith(".Cu")]
        if set(stackup["copper_mm"]) != set(copper):
            raise ValueError("Configured stackup does not match the PCB copper layers")
        if len(stackup["dielectric_mm"]) != len(copper) - 1:
            raise ValueError("Expected one dielectric thickness between each pair of copper layers")
        for value in [*stackup["copper_mm"].values(), *stackup["dielectric_mm"]]:
            number(value, "stackup thickness (mm)", positive=True)
    empty = []
    for zone in children(tree, "zone"):
        layers = children(zone, "layer") or children(zone, "layers")
        is_copper = layers and any(str(name).endswith(".Cu") for name in layers[0][1:])
        if is_copper and not children(zone, "filled_polygon") and not (
                children(zone, "keepout") or children(zone, "rule_area")):
            empty.append(zone)
    if empty:
        warnings.append(f"{len(empty)} copper zone definitions have no saved fill; overlapping "
                        "same-net zones may already cover them. Refill/save before comparison.")
    if stackup:
        imported = children(children(tree, "setup")[0], "stackup")
        if imported:
            for layer in children(imported[0], "layer"):
                thickness = children(layer, "thickness")
                if layer[1] in stackup["copper_mm"] and thickness:
                    actual = float(thickness[0][1])
                    wanted = stackup["copper_mm"][layer[1]]
                    if abs(actual - wanted) > 1e-6:
                        warnings.append(f"Simulation override {layer[1]}: {wanted*1000:g} um "
                                        f"(saved PCB says {actual*1000:g} um).")
    warnings.append("Only saved files are copied. Save and refill the board before every launch.")
    return warnings


def snapshot(config, config_path):
    board_rel = Path(config["board"])
    if board_rel.is_absolute() or ".." in board_rel.parts:
        raise ValueError("board must be a relative path inside the project")
    runs = HERE / "runs"
    runs.mkdir(exist_ok=True)
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:6]
    destination = runs / label
    with tempfile.TemporaryDirectory(prefix=".preparing-", dir=runs) as temporary:
        stage = Path(temporary)
        selected = set()
        for pattern in config["copy_patterns"]:
            if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
                raise ValueError(f"Copy pattern must stay within the project: {pattern}")
            for path in PROJECT.glob(pattern):
                if path.is_dir():
                    selected.update(p for p in path.rglob("*") if p.is_file())
                elif path.is_file():
                    selected.add(path)
        for path in sorted(selected):
            # Never recurse into generated data, backups, or follow links outside the project.
            relative = path.relative_to(PROJECT)
            if relative.parts[0] == "simulation" or not path.resolve().is_relative_to(PROJECT):
                raise ValueError(f"Copy pattern includes generated data or an external symlink: {path}")
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        board = stage / board_rel
        tree = board_tree(board)
        setup = config["setup"]
        if config.get("stackup_source") == "board":
            setup["stackup"] = None
            native_stack = children(children(tree, "setup")[0], "stackup")
            if not native_stack:
                raise ValueError("Board-driven stackup requires a saved physical stackup in KiCad")
            names = {layer[1] for layer in children(native_stack[0], "layer")
                     if str(layer[1]).endswith(".Cu")}
            board_names = {layer[1] for layer in children(tree, "layers")[0][1:]
                           if str(layer[1]).endswith(".Cu")}
            if names != board_names:
                raise ValueError("Saved physical stackup does not cover all board copper layers")
        warnings = validate_setup(setup, tree)
        if config.get("stackup_source") == "board":
            warnings.append(f"Using saved PCB stackup directly: {len(board_names)} copper layers.")
        sources = config.get("component_heat", [])
        pads_by_ref = {}
        for footprint in children(tree, "footprint"):
            ref = next((p[2] for p in children(footprint, "property") if p[1] == "Reference"), None)
            pads_by_ref[ref] = {p[1] for p in children(footprint, "pad")}
        validate_component_heat(sources, pads_by_ref)
        connectors = config.get("connectors", [])
        validate_connectors(connectors, setup["loads"])
        solder = config.get("solder_reinforcement")
        fabrication = config.get("fabrication")
        validate_fabrication(fabrication)
        if fabrication:
            warnings.append(f"Laminate: {fabrication['laminate']['name']}; "
                            f"{fabrication['laminate']['status']}. Epoxy-filled/capped vias use nonconductive fill.")
        board_nets = {n[-1] for fp in children(tree, "footprint")
                      for pad in children(fp, "pad") for n in children(pad, "net")}
        validate_solder(solder, board_nets,
                        {l[1] for l in children(tree, "layers")[0][1:]})
        if solder and solder["enabled"]:
            if not setup.get("thermal", {}).get("enabled"):
                raise ValueError("Solder reinforcement requires Solve all with electro-thermal enabled")
            if config.get("thermal_model", {}).get("mode") not in (
                    "compact", "finite_area_stress", "board_reference"):
                raise ValueError("Solder reinforcement requires a supported thermal_model mode")
            for region in solder["regions"]:
                warnings.append(f"Added solder: {region['thickness_mm']:g} mm, "
                                f"coverage {region['coverage_fraction']:.0%}, {region['layer']}, "
                                + ", ".join(region["nets"]))
        if sources or connectors or solder or fabrication:
            model = {"format_version": 2, "sources": sources, "connectors": connectors,
                     "thermal_model": config.get("thermal_model", {}),
                     "solder_reinforcement": solder, "fabrication": fabrication}
            mode = model["thermal_model"].get("mode")
            if mode and mode not in ("compact", "finite_area_stress", "board_reference"):
                raise ValueError(f"Unsupported thermal model mode: {mode}")
            source_path(board).write_text(json.dumps(model, indent=2, allow_nan=False) + "\n",
                                          encoding="utf-8")
            watts = sum(s["power_w"] * s["board_fraction"] for s in sources)
            warnings.append(f"Nominal component generation: {watts:.4f} W. "
                            f"Thermal mode: {mode or 'legacy point source'}. "
                            "Compact mode solves heat partition; these watts are not all forced into the PCB.")
            for connector in connectors:
                load = next(l for l in setup["loads"] if l["name"] == connector["load"])
                heat = load["current"]**2 * (connector["supply_contact_ohm"]
                                            + connector["return_contact_ohm"])
                warnings.append(f"{load['name']}: DT contact-loss estimate {heat:.4f} W "
                                "(both contacts); recomputed from solved current each iteration.")
        # JSON is valid YAML 1.2; KiPI's YAML loader accepts it without bootstrap dependencies.
        setup_file = board.with_name(board.stem + ".kipi-setup.yml")
        setup_file.write_text(f"# Generated from {config_path.name}; edit the source config for future runs.\n"
                              + json.dumps(setup, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (stage / "simulation-config.json").write_text(
            json.dumps(config, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        manifest = {
            "created_utc": label, "source_project": str(PROJECT),
            "config_source": str(config_path), "board": board_rel.as_posix(),
            "kipi_commit": KIPI_COMMIT, "kipi_archive_sha256": KIPI_SHA256,
            "warnings": warnings, "assumptions": config.get("notes", []),
            "sha256": {p.relative_to(stage).as_posix(): digest(p)
                       for p in sorted(stage.rglob("*")) if p.is_file()},
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        stage.rename(destination)
    print(f"Snapshot: {destination}")
    print(f"KiPI setup: {destination / setup_file.relative_to(stage)}")
    for warning in warnings:
        print(f"NOTE: {warning}")
    return destination / board_rel


def fetch_kipi():
    tools = HERE / ".tools"
    target = tools / f"KiPI-{KIPI_COMMIT}"
    if (target / "kipi_launcher.py").is_file():
        return target
    tools.mkdir(exist_ok=True)
    print(f"Downloading pinned KiPI {KIPI_COMMIT[:12]} ...", flush=True)
    with tempfile.TemporaryDirectory(prefix="download-", dir=tools) as temporary:
        work = Path(temporary)
        archive = work / "kipi.zip"
        with urllib.request.urlopen(KIPI_URL, timeout=60) as response, archive.open("wb") as out:
            shutil.copyfileobj(response, out)
        if digest(archive) != KIPI_SHA256:
            raise ValueError("KiPI archive checksum mismatch; download was not installed")
        with zipfile.ZipFile(archive) as zipped:
            for info in zipped.infolist():
                extracted = (work / info.filename).resolve()
                if not extracted.is_relative_to(work.resolve()):
                    raise ValueError("Unsafe path in KiPI archive")
            zipped.extractall(work)
        extracted = work / f"KiPI-{KIPI_COMMIT}"
        if not (extracted / "kipi_launcher.py").is_file():
            raise ValueError("KiPI archive does not contain its launcher")
        extracted.rename(target)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE / "config.json",
                        help="alternate JSON config (relative paths use the current directory)")
    parser.add_argument("--prepare-only", action="store_true",
                        help="copy and validate without downloading or opening KiPI")
    parser.add_argument("--fetch-only", action="store_true",
                        help="download/verify pinned KiPI only; no snapshot or GUI")
    args = parser.parse_args(argv)
    if args.fetch_only and args.prepare_only:
        parser.error("choose --fetch-only or --prepare-only")
    if args.fetch_only:
        print(fetch_kipi())
        return 0
    config = read_config(args.config.resolve())
    board = snapshot(config, args.config.resolve())
    if args.prepare_only:
        return 0
    kipi = fetch_kipi()
    env = os.environ.copy()
    env["KIPI_HOME"] = str(HERE / ".runtime")
    env["KIPI_HOST"] = "standalone"
    # The upstream launcher treats an inherited API socket as plugin mode even when
    # KIPI_HOST says standalone. This workflow always uses the isolated file copy.
    env.pop("KICAD_API_SOCKET", None)
    print("Opening KiPI. First launch installs dependencies in this terminal; then click Solve all.", flush=True)
    return subprocess.call([sys.executable, str(HERE / "launch_kipi.py"), str(kipi), str(board)],
                           cwd=board.parent, env=env)


if __name__ == "__main__":
    if not (3, 11) <= sys.version_info[:2] <= (3, 13):
        print("Use Python 3.11, 3.12, or 3.13 (3.12 recommended).", file=sys.stderr)
        sys.exit(2)
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print(f"Simulation setup failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
