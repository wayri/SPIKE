# SPDX-License-Identifier: Apache-2.0
"""Single-run eBrake layered exact/coarse/fuzzy diagnostic; not qualification."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.board_thermal import run_board_thermal
from python.spike_core.kicad_importer import import_kicad_design


def main() -> int:
    source = ROOT / "examples/thermal/ebrake1_layered_thermal.json"
    target = ROOT / "docs/validation/ebrake1-layered-fuzzy-benchmark.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    board_path = ROOT / payload["source"]["board_path"]
    digest = hashlib.sha256(board_path.read_bytes()).hexdigest()
    if digest != payload["source"]["board_sha256"]:
        raise ValueError("Pinned eBrake board digest changed.")
    design = import_kicad_design(str(board_path))
    cases = [("fine_unsmoothed", 1.5, 0.0), ("fine_fuzzy", 1.5, 1.5),
             ("coarse_unsmoothed", 3.0, 0.0), ("coarse_fuzzy", 3.0, 1.5)]
    rows = []
    for name, step, sigma in cases:
        request = copy.deepcopy(payload["request"])
        request["board"]["grid_step_mm"] = step
        request["board"]["fuzzy_sigma_mm"] = sigma
        start = time.perf_counter()
        result = run_board_thermal(design, request)
        elapsed = time.perf_counter() - start
        if result["status"] != "completed":
            raise ValueError(f"{name}: {result['issues']}")
        rows.append({"name": name, "grid_step_mm": step, "fuzzy_sigma_mm": sigma,
                     "cells_per_layer": result["grid"]["shape"][0] * result["grid"]["shape"][1],
                     "depth_layers": len(result["layer_grids"]), "solver_elapsed_s": elapsed,
                     "maximum_board_temperature_c": result["summary"]["maximum_board_temperature_c"],
                     "maximum_junction_temperature_c": result["summary"]["maximum_junction_temperature_c"],
                     "junction_temperatures_c": {part["component_ref"]: part["junction_temperature_c"]
                                                 for part in result["components"]},
                     "energy_balance_error_w": result["summary"]["energy_balance_error_w"],
                     "linear_relative_residual": result["summary"]["linear_relative_residual"]})
    baseline = rows[0]["junction_temperatures_c"]
    for row in rows:
        row["max_abs_junction_delta_vs_fine_unsmoothed_c"] = max(
            abs(value - baseline[ref]) for ref, value in row["junction_temperatures_c"].items())
    report = {"board_sha256": digest, "model_status": "approximate", "production_qualified": False,
              "timing_scope": "Single sequential local run after one import; rasterization and linear solve included, image rendering excluded; timing is hardware-dependent.",
              "warning": "Differences against the fine unsmoothed approximation are not error bounds or measured accuracy.",
              "cases": rows}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
