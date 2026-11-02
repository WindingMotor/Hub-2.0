#!/usr/bin/env bash
set -euo pipefail

# Requires curl/tar and either local KiCad Python or ASSEMBLY_USE_DOCKER=1.
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ibom_revision=d1eb5b79a52a2ddc1ce270b63920346463c19b05
ibom_tmp="$(mktemp -d)"
trap 'rm -rf -- "$ibom_tmp"' EXIT

if [[ "${ASSEMBLY_USE_DOCKER:-0}" != 1 ]]; then
  /usr/bin/python3 -c 'import pcbnew' >/dev/null
fi
curl --fail --silent --show-error --location --retry 2 \
  "https://codeload.github.com/openscopeproject/InteractiveHtmlBom/tar.gz/$ibom_revision" \
  --output "$ibom_tmp/source.tar.gz"
tar -xzf "$ibom_tmp/source.tar.gz" -C "$ibom_tmp"
ibom_root="$ibom_tmp"
ibom_project="$project_dir"
ibom_python=(/usr/bin/python3)
if [[ "${ASSEMBLY_USE_DOCKER:-0}" == 1 ]]; then
  ibom_root=/ibom
  ibom_project=/project
  ibom_python=(docker run --rm --user "$(id -u):$(id -g)"
    -e HOME=/tmp -e INTERACTIVE_HTML_BOM_NO_DISPLAY=1
    -v "$project_dir:/project:ro" -v "$ibom_tmp:/ibom"
    --entrypoint /usr/bin/python3 "${KICAD_IMAGE:-kicad/kicad:10.0}")
fi
INTERACTIVE_HTML_BOM_NO_DISPLAY=1 "${ibom_python[@]}" \
  "$ibom_root/InteractiveHtmlBom-$ibom_revision/InteractiveHtmlBom/generate_interactive_bom.py" \
  "$ibom_project/Hub-2.0.kicad_pcb" \
  --no-browser --dark-mode --include-tracks --include-nets \
  --dest-dir "$ibom_root/output" --name-format ibom
test -s "$ibom_tmp/output/ibom.html"
mkdir -p "$project_dir/Design-Outputs"
cp -- "$ibom_tmp/output/ibom.html" "$project_dir/Design-Outputs/ibom.html"
printf 'Updated Design-Outputs/ibom.html. Commit it with the PCB changes.\n'
