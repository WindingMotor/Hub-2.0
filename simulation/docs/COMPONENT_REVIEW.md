# Relay, fuse, and control-circuit thermal inputs

This is a historical component-data review. Its four-layer and all-to-board model
descriptions below have been superseded by the saved six-layer stackup, compact
component networks, and selective solder model. Use the [current simulation guide](../README.md)
and [`config.json`](../config.json) for active behavior. Datasheet values below
remain reference inputs; older temperature examples do not describe the current case.

Reviewed 2026-10-28. Source PCB/schematics were not edited. Original simulation
cases and the running KiPI process are preserved. The new cases use the current
named `PWR_*_BEFORE_FUSE` nets.

## Historical four-layer model and fixes

The default `config.json` now contains the populated 29 A component case.
All current case configs use the user-specified **35 / 17.5 / 17.5 / 35 µm**
copper stack (1 oz outer, 0.5 oz inner). The saved PCB currently still says
35 µm for both inner layers; the simulation explicitly overrides it and says so
on launch. FR4 gaps are provisionally **0.1 / 1.295 / 0.1 mm**, maintaining
1.6 mm copper+laminate thickness in KiPI. These dielectric dimensions are an
assumption, not an approved fabrication stackup. Confirm with the board house.

The earlier 48.9 °C report did **not** contain coil/control heat: the adapter used
KiPI's `file` field, which is empty for native PCB reads. The adapter now resolves
`project_dir / board_name`, checks heat conservation, and logs the heat actually
applied on each iteration. Regression checks use the real native reader with
its naturally empty `file` field. Previous snapshots/reports are unchanged.

The warning about empty zone definitions now filters out mask/rule layers. A
zone definition without its own fill is not proof of missing copper if another
filled zone of the same net already covers it.

## DT connector and 16 AWG interface model

User confirmed DEUTSCH DT contacts and 16 AWG power wiring, but contact type is
unknown. Both solid and stamped contacts are crimped. The
[TE contact catalog](https://www.te.com/content/dam/te-com/documents/channel/global/ts-ict-tccat-01-catalog.pdf)
lists size-16 test values of 60 mV (solid) and 100 mV (stamped) at 13 A, excluding
wire drop. We use **100 mV / 13 A = 7.6923 mΩ per mated connection** as a
constant-resistance specification-limit sensitivity proxy. This is not measured
typical resistance, nor a guarantee of behavior at every current/temperature.
The [TE DT FAQ](https://www.te.com/en/faqs/deutsch-dt-connectors.html) specifies
13 A contacts and compatibility with 14–20 AWG wire. Wire gauge does not itself
raise the connector current rating.

Each power circuit has a supply and return connection. At the four load estimates,
the DT model contributes **3.984615 W total** (1.3 W per radiator connection,
2.6 W for its supply and return together). Contact losses are recomputed using
the solved load current on every thermal pass. Turning a load off in the GUI
turns off its contact heat. This constant-current model does not change the
PCB current boundary conditions; additional contact drops occur beyond the PCB.

Native KiPI load voltages remain **at the PCB pads**. Exported HTML/PDF reports
now include a separate **Component model audit and DT interface estimates**
table for the estimated voltage after the contacts, and a companion
`.interfaces.json` file recording model inputs and actual thermal heat totals.
An at/over-current flag is a catalog comparison, not connector qualification.

The `connectors` config entries expose:

- `supply_contact_ohm` / `return_contact_ohm`: each mated connection's resistance.
- `board_fraction`: fraction of contact heat deposited at the PCB pad; initially
  **1.0** as a bounding assumption. This does not predict the metal pin temperature.
- `supply_wire_m` / `return_wire_m`: optional 16 AWG harness lengths, currently
  **0** because lengths were not provided; `wire_length_known` is false.
- `wire_ohm_per_m_20c`: **0.01317 Ω/m**, an approximate 16 AWG copper value.
- `wire_temperature_c`: wire-resistance temperature correction, initially 25 °C.

When lengths are known, enter both lengths and set `wire_length_known` true.
Wire voltage drop and power are then included in the supplemental estimates.
Wire heat is external and is **not** deposited into the PCB. Heat carried away
through the wire, contact-body convection, individual solder joints, and finite
3D pin/barrel geometry remain outside this model. KiPI's terminal nodes remain
equipotential; the explicit lumped contact model adds the otherwise missing
interface loss without changing the vendor FEM kernel.

The nominal fixed heat is **7.1776 W**, and the DT sensitivity case adds
**3.984615 W**, giving **11.162215 W** of extra board-deposited heat before
native copper/fuse/contact losses. Verify the session log includes
`Additional board heat actually applied` with relay coils and DT contacts.

Relay-contact resistance and fuse-holder resistance are still unknown physical
inputs. The distinct relay-contact maximum case remains available; no typical
resistance has been invented. These unresolved material inputs are not software
faults and must eventually be replaced with measurements/verified part data.

## Standard MINI fuses

Use Littelfuse **297 MINI, 32 V** as the explicit simulation reference, not a
claim about the resistance of every brand of MINI fuse.

| Reference | Load | Estimated continuous A | Provisional fuse A | Typical cold resistance Ω | Calculated cold loss W |
| --- | --- | ---: | ---: | ---: | ---: |
| F0 | Main at CN1 | 4 | 7.5 | 0.01085 | 0.17360 |
| F1 | Fuel pump | 7 | 10 | 0.00742 | 0.36358 |
| F2 | Radiator | 13 | 20 | 0.00321 | 0.54249 |
| F3 | Lights | 5 | 7.5 | 0.01085 | 0.27125 |

These give **1.35092 W** total using `P = I²R`. Resistance is held constant;
hot fuse elements and holder contacts can add losses. The referenced fuse
datasheet provides resistance, derating and time-current curves. It does not
establish the correct fuse for your harness without startup and fault data.
[Littelfuse 297 datasheet, pp. 2–3](https://www.littelfuse.com/assetdocs/littelfuse_datasheet_297_mini32v.pdf?assetguid=42c9dd21-a88e-4328-8e67-2f832444faf1).

Ratings are preliminary engineering choices with continuous-current headroom.
Check fan/pump inrush against the curves and ensure wiring, connector contacts,
and PCB paths survive the fuse's clearing time. A 20 A fuse does not limit
current to 20 A. No melting, nuisance-trip, pulse-life or protection coordination
simulation is included here.

The `FUSE_3568` footprint resembles the Keystone 3568 holder, but the project
does not identify the purchased holder. Its [manufacturer catalog](https://www.keyelco.com/pdfs/Keystone-NPB2010.pdf)
lists a 20 A rating; that rating is not a contact-resistance value. Holder contact
losses remain unmodeled. Measure the installed fuse-plus-holder voltage drop
at operating current to replace the element-only model with an assembly model;
do not add both and count the fuse twice.

## Relays U1–U4

The project identifies YONGNENG **YQ506-S-112DM**. The
[manufacturer YQ506 family specification](https://ynrelay.com/products/automotive-relay-yq506)
gives a 12 V coil with 90 Ω ±10% resistance at 23 °C, approximately 1.6 W,
and 50 mΩ maximum contact resistance. The exact LCSC-linked variant PDF did not
render during this review; confirm the ordered variant against its supplied sheet.

At an assumed constant 12 V across each coil, `P = 12²/90 = 1.6 W`:
**6.4 W for four energized relays**. The model uses this fixed nominal value;
it does not iterate coil resistance with temperature or solve the external
control-driver wiring. Cold nominal coil current is about 0.133 A each and is
not included in the 29 A external-load electrical solve.

No typical contact resistance was found. Two deliberately different cases avoid
inventing one:

| Case | Contact model | Interpretation |
| --- | --- | --- |
| `all-loads-components.json` | 0 Ω | Contacts still omitted; lower-loss electrical reference |
| `all-loads-components-contact-max.json` | 0.050 Ω each | Datasheet-maximum sensitivity case, not expected normal operation |

At your loads, the latter adds **12.95 W** in contact losses: U1 2.45 W,
U2 8.45 W, U3 0.80 W, U4 1.25 W, before copper feedback. This is a stress
assumption, not a prediction that your relays normally dissipate that much.
The initial specification is not a guarantee for every aged/loaded contact.
Four-wire voltage-drop measurements at representative current are the best next
input for the installed relays.

## Supporting parts on each relay channel

These inputs follow the actual PCB terminal connections and schematic values:

| Parts | Model at assumed 12 V control input | Added fixed heat |
| --- | --- | ---: |
| R7, R8, R9, R11 | `(12 − 2.1)² / 660` | 0.1485 W each |
| D7, D8, D9, D11 | `2.1 × (12 − 2.1) / 660` | 0.0315 W each |
| R4, R5, R6, R10 | `12² / 10000` | 0.0144 W each |
| D4, D5, D6, D10 | Coil flyback paths; no forward conduction assumed while held on | omitted in steady state |
| D12–D15 | Load-output suppression paths; no forward conduction assumed in normal operation | omitted in steady state |
| C1–C15 as populated | DC decoupling | no ripple/leakage heat assigned |

The **0.7776 W** supporting-circuit heat is an estimate. LED optical output is
also counted as heat here. Actual control voltage, LED Vf and resistor value
need confirmation. Switching diode losses require inductance, switching rate,
clamp behavior, and actual diode manufacturer data; they are not constant 0.7 V
drops in the main 29 A path.

Component-data discrepancies found:

- R7/R8/R9/R11 say **660 Ω** in the schematic; LCSC C1369260 identifies
  **YAGEO MFR-25FBF52-665R (665 Ω)**. This model retains the schematic value.
  The [YAGEO MFR family datasheet](https://www.yageogroup.com/content/Resource%20Library/Datasheet/YAGEO-MFR_DATASHEET.pdf)
  confirms the MFR-25 quarter-watt family and its temperature derating. Confirm
  the BOM value; the exact linked resistor PDF could not be retrieved.
- The 10 kΩ parts' schematic power field says 100 mW; the listed C57436
  catalog identity is MFR0W4F1002A50 (quarter-watt family). Use the purchased part
  for the final rating; no exact resistor thermal-body model is assigned.
- LED C779430 identifies TUOZHAN TZ-L2-03YYBY2YDJ30-001. Its linked PDF viewer
  was accessible but the PDF content could not be retrieved; **2.1 V remains
  the schematic estimate**, not a newly verified typical datasheet value.
- The 1N5399 parts are described as “Zener diode” in project metadata.
  Manufacturer [1N539x rectifier data](https://www.vishay.com/docs/88514/1n5391.pdf)
  identifies a rectifier/freewheeling device. No exact diode manufacturer is
  recorded in the project; the reference document is not proof of the fitted part.
- Capacitor identifiers are C254085 (100 nF) and C2761740
  (CD1H106KC9IER2F100, 10 µF). Supplier PDFs did not yield readable specification
  content. Capacitor ESR/ripple heating has not been reviewed quantitatively.

At 14.4 V control voltage, the same cold 90 Ω coil calculation becomes
2.304 W per relay, while each 660 Ω resistor dissipates approximately 0.229 W
using the same 2.1 V LED assumption. Do not reuse fixed 12 V heat inputs for a
charging-voltage case without updating them.

## How fixed component heat enters KiPI

`component_heat` is an explicit extension in our config. Each source has `ref`,
string `pins`, `power_w`, and `board_fraction`. The launcher writes a
`<board>.component-heat.json` sidecar into that run. Our application wrapper adds
the selected wattage to KiPI's board thermal solve at those pads, sharing it
between the pads and their copper layers. The pinned upstream files are untouched.

All fractions initially equal **1.0**, meaning the full nominal component heat
is deposited into the PCB. This is a board heat-input bounding assumption, not
measured package-to-board coupling. Some real heat leaves component bodies
directly into the air. Resulting local temperatures and heat spreading remain
approximate. Native fuse/contact losses are likewise deposited at their pads.

The fixed sources total **7.1776 W**. Together with the cold fuse model, the
reference adds approximately **8.52852 W** before PCB copper losses. The contact
stress case adds a further 12.95 W at the nominal branch currents.

External `load_power` remains **false**, so pump/fan/light delivered power is
not incorrectly deposited into the hub. The thermal report's heat breakdown
identifies the extra coil, resistor, and indicator contributions. Control nets
not selected for electrical solving still participate in the thermal board model.

Use the provided launcher for these cases. Opening the PCB directly with the
stock KiPI launcher will not apply the sidecar. The wrapper chooses heat inputs
from each opened board's adjacent sidecar, so opening another baseline board
does not inherit the previous board's heat inputs. KiPI GUI edits do not edit the
sidecar; use the JSON case config to change fixed heat. Regenerate a run after
updates. If using About → Manage dependencies, relaunch through `run.sh`/`run.bat`
afterward to ensure the component extension is active.

## Connector limit found during this review

CN1 is TE **DT15-12PA**. TE specifies a **13 A maximum contact current** on its
[product page](https://www.te.com/en/product-DT15-12PA.html). The radiator estimate
already reaches that catalog maximum. Earlier 15 A pump tests exceed it and
must be treated as PCB-copper stress cases, not connector qualification.
Check the mated terminal, wire size, simultaneous-contact loading and applicable
derating. Connector contact heat and lug interface losses are absent from this
board-only model.

## Run

After the present run finishes, close KiPI, refill/save the source board, and run:

```bash
./simulation/run.sh --config simulation/cases/all-loads-components.json
# Then compare the distinct maximum-contact-resistance stress case:
./simulation/run.sh --config simulation/cases/all-loads-components-contact-max.json
```

On Windows, use `simulation\run.bat --config simulation\cases\<case>.json`.
Click **Solve all**, inspect the **Thermal** heat breakdown and compare all runs
at the same ambient, mesh, and temperature color scale. Neither new case is a
complete enclosure/component temperature prediction or a finalized protection design.
