# SPDX-License-Identifier: Apache-2.0
"""Export a reviewed finite sampled constraint manifest from JSON files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.solvers.signal_integrity.networks.si_candidate_constraints import export_candidate_constraints


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_result", type=Path)
    parser.add_argument("review_selection", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output must be a new path")
    source = json.loads(args.source_result.read_text(encoding="utf-8"))
    selection = json.loads(args.review_selection.read_text(encoding="utf-8"))
    result = export_candidate_constraints(source, selection)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
