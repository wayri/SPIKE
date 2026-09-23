# SPDX-License-Identifier: MIT
"""Frozen entry point for the dedicated layout scoring process."""

from pathlib import Path
import sys


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from python.spike_core.layout_scoring_process import main


if __name__ == "__main__":
    raise SystemExit(main())
