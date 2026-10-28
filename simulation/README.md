# Hub PCB simulation

Edit [config.json](config.json), save/refill the PCB in KiCad (**B**, then save), and run:

```bash
# Linux, from the project root
./simulation/run.sh
```

```bat
:: Windows, from the project root (or double-click simulation\run.bat)
simulation\run.bat
```

The default uses your **29 A all-loads component case**, the saved PCB's physical
stackup (currently six layers), compact component/DT thermal networks, and selective
**1.5 mm bottom-side solder reinforcement**. Source PCB files are not changed.
Component thermal resistances and several material properties remain uncalibrated
sensitivity inputs; absolute temperatures are not validated hardware predictions.

## Files and configuration

| Location | Purpose |
| --- | --- |
| `config.json` | Shared editable operating case and model parameters |
| [`cases/`](cases/README.md) | Comparison presets inheriting the shared config |
| `run.sh`, `run.bat`, `run.py`, `launch_kipi.py` | Snapshot preparation and cross-platform launch |
| Other root `*.py` files | Runtime thermal/electrical model adapters and headless checker |
| `tests/` | Launcher, config, energy-conservation, and model integration checks |
| `docs/` | Component datasheet review and historical model notes |
| `.tools/`, `.runtime/`, `runs/` | Ignored local downloads, environment, and generated results |

Presets use `"extends": "../config.json"`. Nested objects merge; arrays/scalars/null
replace inherited values. Changes to the default load estimates carry into presets
that do not override the loads. The saved run's `simulation-config.json` contains
the resolved settings. `config.local.json` is available for ignored personal overrides.

Install **Python 3.12** first (3.11–3.13 supported). Windows can use the `py` launcher
or `python` on PATH. Linux can use `python3.12`, `python3.13`, `python3.11`, or a
compatible `python3`. `SIMULATION_PYTHON` overrides interpreter discovery with an
executable path. On Debian/Ubuntu, KiPI's first-time installer may also need
`python3.12-venv` and `python3-tk`; use matching packages for your distribution.
Git and a separate KiCad Python installation are not required.

Each launch:

1. Copies the **saved** PCB, project, schematics, library tables, and local symbol,
   footprint, and 3D libraries into a fresh `runs/<UTC timestamp>-<id>/` folder.
   Files matched by `copy_patterns` retain their paths. Backups and machine-local
   KiCad state are not selected by the default patterns.
2. Checks configured terminals against the copied PCB and writes
   `Hub-2.0.kipi-setup.yml` beside it, plus the input config and a SHA-256 manifest.
3. Downloads [upstream KiPI](https://github.com/drewsum/KiPI) at commit
   `177fa8e4f97d43f85cd06cb2f64a0235558f0819` into `.tools/` on first use and
   verifies the pinned archive checksum. Subsequent launches reuse that version.
4. Opens that snapshot in KiPI standalone with the prepared setup. KiPI's first
   launch offers to install dependencies into `.runtime/` **in the terminal**,
   showing installation progress. The upstream GUI's blocking download-size
   check is skipped; its bundled size estimate is used instead. Internet access is
   needed for the download and first dependency installation. KiPI controls its
   package versions; only its source archive is pinned here.

In KiPI, review the setup, click **Solve all**, select **Temperature** or
**Current density**, then **Report** to export results. Launching does not start
the solver automatically. Close an existing KiPI window before starting a new
run: KiPI allows only one running instance.

## Edit the operating case

The saved `all-loads.json` case uses your simultaneous current estimates: lights
5 A, radiator 13 A, fuel pump 7 A, and main output at CN1 4 A (29 A total), at
25 °C ambient. Run it with `./simulation/run.sh --config simulation/cases/all-loads.json`
from the project root, or on Windows:
`simulation\run.bat --config simulation\cases\all-loads.json`.
Relay/fuse resistances are still ideal zero-ohm placeholders.

For fuse and component heating, see [component research](docs/COMPONENT_REVIEW.md).
`all-loads-components.json` adds chosen MINI fuse cold resistances and explicit
relay coil/control-circuit heat; relay contacts remain an unknown, ideal reference.
`all-loads-components-contact-max.json` adds the relay family's maximum specified
contact resistance as a separate stress case. Use the launcher for these cases;
the adjacent `.component-heat.json` heat-input file requires our application wrapper.
The current compact network solves how much component heat enters the PCB versus
air and the self-heated harness. The separate stress case forces heat into the board.

## Configurable solder reinforcement

`config.json` and `all-loads-components.json` enable `solder_reinforcement`.
The default coats **B.Cu only** on these exact saved net names:

- `+12V_BATT`
- `PWR_RADIATOR`
- `PWR_FUEL_PUMP`
- `/LOW_POWER_RELAYS/PWR_RADIATOR_BEFORE_FUSE`
- `/LOW_POWER_RELAYS/PWR_FUEL_PUMP_BEFORE_FUSE`

Lights/main-output branch copper and GND are not coated by default. Add their exact
names to `regions[].nets` to include them. Split regions to use different thicknesses
on different nets; duplicate layer/net pairs are rejected to prevent double counting.

```json
"solder_reinforcement": {
  "enabled": true,
  "material": {
    "name": "Sn63Pb37",
    "rho_ohm_mm_20c": 0.00014991304347826087,
    "thermal_k_w_mk": 50.0,
    "tcr_per_c": 0.0
  },
  "regions": [{
    "layer": "B.Cu",
    "nets": ["+12V_BATT", "PWR_RADIATOR"],
    "thickness_mm": 1.5,
    "coverage_fraction": 1.0
  }]
}
```

`enabled: false` disables reinforcement. Zero thickness or zero coverage also adds
nothing. Coverage from 0 to 1 scales the effective thickness **uniformly**; it does
not describe isolated patches, an incomplete bridge, or the shape of a solder bead.
The 1.5 mm means added solder thickness over the selected copper's full width, not
the diameter of feed wire or the peak height of a rounded bead.

Electrical sheet conductance is the sum of `t_copper/rho_copper(T)` and
`thickness_mm*coverage_fraction/rho_solder(T)`. Thermal spreading separately adds
`k_solder*thickness_mm*coverage_fraction`. Barrels, PTH contacts and series-part
resistances do not become thicker. Copper and solder are assumed perfectly bonded
and at the same local temperature. No extra cooling area, contact improvement,
solder-filled holes, thermal mass/transient response, or visible 3D solder is added.
Actual mask openings are ignored: the configuration represents the proposed exposed
copper coverage even before you change mask openings in KiCad.

The material proxy assumes 63/37 leaded solder. [Indium's alloy data](https://www.indium.com/wp-content/uploads/2025/01/Solder-Ribbon-and-Foil-PDS-97621-A4-R9.pdf)
lists 11.5% of copper's electrical conductivity and 50 W/mK thermal conductivity
at 85 °C. The configured resistivity maps that ratio to KiPI's 20 °C copper reference;
constant thermal conductivity and **TCR = 0** are explicit approximations, not
measured temperature-dependent alloy properties. Edit these for your actual solder.

Use **Solve all (electro-thermal)** through the launcher. Native individual electrical
solves outside this wrapper do not apply reinforcement. Current-density maps show
current density **in the copper**, excluding the solder's parallel share. Native
sheet-loss tables include copper+solder; the thermal heat breakdown lists `Added
solder` separately. The report and `.interfaces.json` record the applied settings.

For a direct comparison with the same fabrication/component assumptions:

```bash
./simulation/run.sh --config simulation/cases/solder-disabled.json
```

That preset inherits the current case and changes only `enabled` to false, so
changes to currents and other shared inputs carry through automatically. Other preexisting stress presets do not enable
solder unless explicitly configured.

## Laminate and epoxy-filled/capped vias

All case configs record JLCPCB **Nan Ya NP-155F** under `fabrication.laminate`.
Saved board copper/dielectric thicknesses and electrical permittivity are retained.
[JLCPCB's Nan Ya datasheet](https://rs.jlcpcb.com/static/file/nan-ya-np-155f-datasheet.pdf)
does not specify thermal conductivity; configurable `k_in_plane_w_mk: 0.8` and
`k_through_w_mk: 0.3` remain generic FR4 estimates. They are not NP-155F measurements.
The override applies to all dielectric gaps; exact core/prepreg weave differences
remain unresolved. Tg is not used as a thermal conductivity or an operating limit.

`fabrication.vias.epoxy_filled_capped` marks existing vias up to
`max_filled_drill_mm` (default 0.5 mm) filled in a runtime copy. Component PTH holes
are excluded. Fill must be **nonconductive**, leaving electrical barrel copper area
unchanged. Conflicting conductive/copper fill rules are rejected.
[JLCPCB specifies nonconductive epoxy with copper caps and a 5 µm minimum cap thickness](https://jlcpcb.com/help/article/pcb-via-covering).
The minimum cap is recorded as `cap_minimum_mm`; it is **metadata**, not an extra
thickness applied to finished 1 oz foil. Exact cap-disk current spreading and the
epoxy core's thermal correction are not resolved by this adapter. No resin thermal
conductivity was found in that specification, so no invented copper-equivalent
fill or thermal improvement is credited. The native grid still homogenizes the
laminate around via barrels. Via-in-pad availability is recorded; only vias actually
present in the saved board participate, with native terminal-pad idealizations.

`config.json` is standard JSON (no comments or trailing commas). Its `notes`
record the initial assumptions. `setup` uses KiPI's native setup fields:

| Setting | Meaning |
| --- | --- |
| `setup.loads[].current` | External load current in **A**: pump 7, radiator 13, lights 5, main 4 |
| `setup.loads[].supply` / `ground` | Connector reference, net, and string pad numbers |
| `setup.links[].resistance` | Resistance in **ohms**; fuse cold values are populated, relay contacts remain unknown/ideal |
| `setup.vrms[0].voltage` | Battery supply voltage |
| `setup.vrms[0].output` / `ground` | Positive and negative supply connection points |
| `setup.thermal.ambient_c` | Temperature of the surrounding air, °C |
| `setup.thermal.airflow_m_s` | Airflow, m/s; zero uses KiPI's natural-cooling approximation |
| `setup.thermal.iterations` | Electrical/thermal feedback passes |
| `setup.thermal.grid_mm` | Thermal grid size, mm; zero selects automatically |
| `setup.settings.max_edge_mm` | Electrical mesh size, mm |
| `setup.settings.plating_mm` | Via plating thickness, mm |
| `stackup_source` | `board` reads the saved physical stackup on every launch |
| `setup.stackup` | `null` with board-driven stackup; explicit overrides require matching layers |
| `setup.thermal.max_temp_c` / `max_rise_c` | Optional temperature limits; `null` disables checks |

The initial four external loads are:

| Load | Closed contact → fuse | CN1 supply / return pads |
| --- | --- | --- |
| Fuel pump | U1 30→87 → F1 1→2 | 5 / 6 |
| Radiator | U2 30→87 → F2 1→2 | 3 / 4 |
| Lights | U4 30→87 → F3 1→2 | 1 / 2 |
| Main output at CN1 | U3 30→87 → F0 1→2 | 7 / 8 |

For example, change the fuel-pump load's `current` from `7.0` to your measured
current in amperes. Set its relay and fuse `resistance` values from measurements
or datasheets: **5 mΩ is 0.005 Ω**. Zero resistance omits that part's heat.
Set a load's current to zero to leave it unloaded. All configured relay links
remain closed; remove a link to model an open contact.

These are **starting assumptions**, not vehicle specifications: 12 V supply,
25 °C air, the saved board's physical stackup, 25 µm via plating, battery
positive at LUG1 and return at LUG2. Verify them against the board fabrication
order and harness. LUG3/chassis and starter-lug currents are not preconfigured.
The main load is specifically at CN1; add separate loads for ECU/dash connectors
with their actual return paths. Do not add their currents to CN1 if they leave
the board through other connectors.

`load_power` is deliberately **false**: pumps, fans, and external electronics
dissipate their delivered power outside the hub. Turning it on puts their full
power onto the board. The default includes copper/via and configured fuse losses,
plus temperature-dependent relay-coil heat, fixed control heat and current-dependent DT-contact heat. KiPI's steady-state
board model does not resolve the enclosure or full component package heating.

## Other commands

```bash
# Offline snapshot + terminal validation, without downloading or opening KiPI
python3 simulation/run.py --prepare-only

# Download/check the pinned KiPI source only
python3 simulation/run.py --fetch-only

# A separate operating case; relative config paths use your working directory
python3 simulation/run.py --config simulation/hot-idle.json

# Launcher tests (standard library only)
python3 -m unittest discover -s simulation/tests -t .
```

To include the KiPI-dependent physics checks on Linux after dependency installation:

```bash
PYTHONPATH="simulation/.tools/KiPI-177fa8e4f97d43f85cd06cb2f64a0235558f0819:simulation" \
  simulation/.runtime/venv/bin/python -m unittest discover -s simulation/tests -t .
```

On Windows PowerShell, set the same two paths in `$env:PYTHONPATH`, separated by
`;`, and use `simulation\.runtime\venv\Scripts\python.exe`.

On Windows use `py -3.12` in place of `python3`, or pass the same options to
`run.bat`. The wrappers work from any directory, including paths with spaces.

Saved KiPI GUI edits and reports stay with that run. Future launches use
`config.json` again; they do not overwrite previous runs or automatically import
GUI edits. Copy deliberate changes back to the config. `manifest.json` hashes
the original run inputs; KiPI may subsequently change its run-local setup.

External system libraries referenced by absolute paths are not copied; add any
needed project-local files to `copy_patterns`. Standard KiCad libraries remain
on the machine. No files are written back to the source PCB or schematics.

`runs/`, `.tools/`, `.runtime/`, and Python caches are ignored by Git. You can
remove old run folders when their results are no longer needed. Remove `.tools/`
to redownload KiPI or `.runtime/` to repeat dependency setup (close KiPI first).

Sources for the integration: [KiPI launcher and installation](https://github.com/drewsum/KiPI#standalone),
[setup schema](https://github.com/drewsum/KiPI/blob/177fa8e4f97d43f85cd06cb2f64a0235558f0819/kipi/dc/pi/model.py),
and [thermal model](https://github.com/drewsum/KiPI/blob/177fa8e4f97d43f85cd06cb2f64a0235558f0819/kipi/dc/thermal/model.py).
