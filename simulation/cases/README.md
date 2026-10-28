# Comparison presets

Edit shared settings in [`../config.json`](../config.json). Every preset uses a
relative `extends` and overrides only the settings needed for that comparison.
Nested objects merge; arrays, scalar values, and `null` replace the inherited value.
Arrays such as `setup.loads` must contain the complete desired list when overridden.

| Preset | Difference from the default |
| --- | --- |
| `all-loads-components.json` | Alias of the current default component+solder case |
| `solder-disabled.json` | Same case with solder disabled; use for a controlled solder comparison |
| `all-loads.json` | Copper-only electrical reference: ideal relays/fuses, no component/contact heat or solder |
| `board-reference.json` | Copper and fuse losses only; no component/contact heat or solder |
| `all-loads-components-contact-max.json` | Relay contact maximum-resistance sensitivity case; solder disabled |
| `all-to-board-stress.json` | All component/contact generation deposited into finite board-pad areas; solder disabled |
| `compact-weak-board-coupling.json` | Weaker component/board thermal coupling sensitivity; solder disabled |
| `compact-strong-board-coupling.json` | Stronger component/board thermal coupling sensitivity; solder disabled |

From the repository root:

```bash
./simulation/run.sh --config simulation/cases/solder-disabled.json
```

Windows:

```bat
simulation\run.bat --config simulation\cases\solder-disabled.json
```

Old commands naming `simulation/<preset>.json` still resolve to this directory.
The run snapshot stores the fully resolved config, so subsequent changes to shared
settings do not alter historical runs. For an untracked personal variant, create
`simulation/config.local.json` with `"extends": "config.json"` and your overrides.
