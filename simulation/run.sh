#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${SIMULATION_PYTHON:-}" ]]; then
    exec "$SIMULATION_PYTHON" "$script_dir/run.py" "$@"
fi
for candidate in python3.12 python3.13 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(not ((3, 11) <= sys.version_info[:2] <= (3, 13)))'; then
        exec "$candidate" "$script_dir/run.py" "$@"
    fi
done
echo "Install Python 3.12, or set SIMULATION_PYTHON to a Python 3.11-3.13 executable." >&2
exit 2
