# SPDX-License-Identifier: Apache-2.0
"""Run explicit finite 3-D land patches and verify retained physical witnesses."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from python.spike_core.dc_land_transition import solve_land_transition
from python.spike_core.dc_land_transition_evidence import validate_land_result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, default=Path(__file__).with_name("three-patch.request.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Select a fresh result path")
    if args.request.stat().st_size > 1024*1024:
        parser.error("Request exceeds 1 MiB")
    result = solve_land_transition(json.loads(args.request.read_text(encoding="utf-8")))
    validate_land_result(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"model_status": result["model_status"], "heat_w": result["joule_heat_w"],
                      "cells": len(result["cells"]), "production_qualified": False}))
