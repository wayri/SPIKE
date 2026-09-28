# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Run an entity-bound PCB port through the actual optional openEMS workflow.

Defaults to preparation; --run executes FDTD plus NF2FF. This is an integration
example, not an independent field-accuracy or compliance qualification.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.openems_benchmarks import patch_antenna_fixture
from python.spike_core.pcb_entity_ports import CONTRACT, prepare_entity_port_case
from python.spike_core.external_engines import run_openems_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New case directory (must not exist)")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--experimental-compact-edge-grid", action="store_true",
                        help="Opt in to reduced sheet-edge mesh lines; requires case-specific convergence")
    args = parser.parse_args()
    design, spec = patch_antenna_fixture()
    # Overlapping same-net metal exercises exact rotation without changing the patch contour.
    design.pads = [{"id": "rotated-land", "shape": "rect", "at": [0, 0], "size": [4, 1],
                    "rotation": 37, "layer": "F.Cu", "net_name": "PATCH"}]
    ports = {"contract": CONTRACT, "ports": [{"id": "patch-feed",
        "signal": {"entity_id": "patch", "layer": "F.Cu", "at_mm": [-6., 0.]},
        "reference": {"entity_id": "ground", "layer": "B.Cu", "at_mm": [-6., 0.]},
        "impedance_ohm": 50., "excite": True}]}
    prepared = prepare_entity_port_case(design, spec, ports, output_dir=args.output,
        options={"mesh_resolution_mm": 3., "air_padding_mm": 30., "threads": 2,
                 "max_timesteps": 50000, "max_solver_time_s": 120, "timeout_s": 180,
                 "experimental_compact_edge_grid": args.experimental_compact_edge_grid})
    print(json.dumps({"prepared_status": prepared["status"], "case_dir": prepared.get("case_dir")}, allow_nan=False))
    if args.run and prepared["status"] == "ready_to_run":
        result = run_openems_case(args.output)
        print(json.dumps({"status": result.get("status"), "model_status": result.get("model_status"),
            "message": result.get("message"), "frequency_points": len(result.get("frequency_hz", [])),
            "far_field_shape": result.get("far_field", {}).get("shape"),
            "result": str(Path(args.output) / "engine-output" / "normalized-result.json")}, allow_nan=False))
        return 0 if result.get("status") == "completed" else 2
    return 0 if prepared["status"] == "ready_to_run" else 2


if __name__ == "__main__":
    raise SystemExit(main())
