# Working on Hub 2.0 with Prism

[Open Hub 2.0 in Prism](https://ramracing-prism.larkspurindustries.com/project/prj_d483e5fd3cd7).
Prism fetches Git about every five minutes. Commit and push saved KiCad files
before asking teammates to review them. Unsaved desktop edits are not uploaded.

## Review a change

Use a branch for each change. Coordinate ownership of schematic sheets; coordinate
PCB edits as a whole board. Prism provides review and comparison tools, but does
not merge simultaneous KiCad edits or remove the need to resolve Git conflicts.

Open the exact commit in Prism, compare it with its parent, and attach review
comments to the affected symbols, components or nets. Share the revision URL so
reviewers see the same design. Check schematic-to-PCB differences and exclusions
before treating a BOM or assembly view as a manufacturing instruction.

## Documentation and assembly

`.prism.json` maps the root schematic, subsheets, PCB, README and documentation.
On relevant pushes to `main`, the **Prism design documentation** GitHub workflow
exports schematic PDF/PNGs and regenerates `Design-Outputs/ibom.html`. Its bot
commit is then fetched by Prism. The Assembly Assistant uses that committed HTML;
wait for the docs commit and select that revision to see updated generated files.
A historical revision keeps the HTML that was committed at that revision.

The workflow intentionally refuses a non-fast-forward output push. If someone
pushes a design change during generation, run the workflow again from the latest
`main`; older generated files must not be rebased onto a newer board.

To regenerate the assembly view locally with KiCad installed:

```bash
./scripts/generate-assembly.sh
```

Or use Docker (the same path as CI):

```bash
ASSEMBLY_USE_DOCKER=1 ./scripts/generate-assembly.sh
```

The default Docker image is `kicad/kicad:10.0`; `KICAD_IMAGE` overrides it. Commit
the generated HTML with the corresponding PCB when updating it locally. The
InteractiveHtmlBom source is pinned to a commit in the script.

## KiCad library and BOM settings

Keep the existing `${KIPRJMOD}` EasyEDA library tables and model paths: teammates
can still open a clone independently of Prism. Do not replace them with absolute
paths or credentials. Imported Library Manager parts remain drafts until reviewed
and released; import alone is not library QA.

For **new** shared parts, review and release them in Library Manager, then add
`https://ramracing-prism.larkspurindustries.com` as a Remote Symbols provider in
KiCad 10 and sign in with your own account. The provider exposes released parts.
Prism records component/revision identifiers on parts placed through the provider.
Commit any project-local library files created by placement. Existing EasyEDA
parts are not automatically converted to catalog-managed placements.

The KiCad project now includes a **Ram Racing Review** BOM preset. Select it in
KiCad or Prism Release Studio to include manufacturer, MPN and both existing LCSC
field names. It deliberately shows DNP and exclusion fields, including schematic
interface symbols; it is a review BOM, not a filtered procurement list. Empty
metadata stays empty rather than being guessed.

## Simulation and traceability

Keep using the [KiPI launcher](https://github.com/WindingMotor/Hub-2.0/blob/main/simulation/README.md)
for the existing electro-thermal, connector, component and solder models. Prism's
experimental Simulation Studio currently offers DC IR drop, and does not import
this project's KiPI JSON cases or provide equivalent custom thermal models.
Enabling that studio would require a separate setup and validation.

Each new KiPI snapshot's `manifest.json` records the Git commit, branch and dirty
state if Git is available. A dirty run includes local changes and cannot be
reproduced from the commit alone; the saved input hashes/snapshot are authoritative.
Git remains optional: source revision is `null` when it cannot be read.
Save/refill before running; an input snapshot is not a completed solver run.

The **Simulation input checks** GitHub workflow runs the available standard-library
checks and prepares the default plus every saved case. Its downloadable manifests
record inputs only. KiPI-dependent physics checks are skipped without the KiPI
runtime; CI does not solve the board, test thermal performance or approve hardware.

To share a reviewed result in Prism's Documents view, commit a report and its
manifest under `documentation/simulation/<case>-<source-commit>/`. Include the
resolved simulation config, operating assumptions, and whether the source was
dirty. Keep bulky run folders and downloaded runtimes ignored. For a clean run,
open its board revision with:

```text
https://ramracing-prism.larkspurindustries.com/project/prj_d483e5fd3cd7?commit=<full-source-commit>
```

## Release Studio

Choose a saved commit, board, schematic and **Ram Racing Review** BOM preset.
Build and inspect the documents, DRC/ERC results and fabrication views. Resolve
issues and complete designer/QA review before publishing a manufacturing release.
The board's saved stackup remains the source of truth; these integration changes
do not alter electrical constraints, copper geometry or fabrication settings.

Publishing to GitHub additionally requires a server-side forge token. Keep that
token out of Git and use an account with only the necessary repository access.
No publishing credentials or automatic manufacturing-release publication are
configured by these project changes.

Prism's 3D and Stackup views also require WebGPU in the reviewer's browser; a
successful server build cannot enable a disabled browser graphics adapter.
