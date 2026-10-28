"""Allow unittest discovery without installing the local simulation adapters."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
