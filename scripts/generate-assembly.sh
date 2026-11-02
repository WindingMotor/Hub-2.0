#!/usr/bin/env bash
set -euo pipefail

# Requires KiCad's pcbnew module in /usr/bin/python3, curl, and tar.
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ibom_revision=d1eb5b79a52a2ddc1ce270b63920346463c19b05
ibom_tmp="$(mktemp -d)"
trap 'rm -rf -- "$ibom_tmp"' EXIT

/usr/bin/python3 -c 'import pcbnew' >/dev/null
curl --fail --silent --show-error --location --retry 2 \
  "https://codeload.github.com/openscopeproject/InteractiveHtmlBom/tar.gz/$ibom_revision" \
  --output "$ibom_tmp/source.tar.gz"
tar -xzf "$ibom_tmp/source.tar.gz" -C "$ibom_tmp"
INTERACTIVE_HTML_BOM_NO_DISPLAY=1 /usr/bin/python3 \
  "$ibom_tmp/InteractiveHtmlBom-$ibom_revision/InteractiveHtmlBom/generate_interactive_bom.py" \
  "$project_dir/Hub-2.0.kicad_pcb" \
  --no-browser --dark-mode --include-tracks --include-nets \
  --dest-dir "$ibom_tmp/output" --name-format ibom
test -s "$ibom_tmp/output/ibom.html"
mkdir -p "$project_dir/Design-Outputs"
cp -- "$ibom_tmp/output/ibom.html" "$project_dir/Design-Outputs/ibom.html"
printf 'Updated Design-Outputs/ibom.html. Commit it with the PCB changes.\n'
