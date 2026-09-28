# SPDX-License-Identifier: Apache-2.0
"""Run a source-trace Marble +1V0 PI slice with explicit provisional ports.

The two signal pads, connecting tracks, and adjacent dielectric dimensions are
imported from the Marble board. The local GND rectangle and lumped port planes
are assumptions. This is not a full-board or fabrication-validated PDN model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from extensions.openems_suite.engine import _validate_openems_case, prepare_openems_case, run_openems_case
from python.spike_core.cli import load_design
from python.spike_core.contracts import AnalysisSpec, DesignIR


SIGNAL = "+1V0"
RETURN = "GND"
PORTS = (("U4.6", 289.36726, 98.21742), ("C53.1", 290.7, 98.20962))
SEGMENTS = (
    ((289.36726, 98.21742), (290.6922, 98.21742)),
    ((290.6922, 98.21742), (290.7, 98.20962)),
)


def near(a: object, b: tuple[float, float]) -> bool:
    return isinstance(a, (tuple, list)) and len(a) == 2 and all(
        abs(float(x)-y) < 1e-5 for x, y in zip(a, b))


def build_case(board: Path, excite_port: int = 1) -> tuple[DesignIR, AnalysisSpec, dict]:
    if excite_port not in (1, 2):
        raise ValueError("Exactly one of the two ports must be excited")
    original = DesignIR(**load_design(board))
    pads = []
    for name, x, y in PORTS:
        matching = [pad for pad in original.pads if pad.get("net_name") == SIGNAL
                    and pad.get("component_pad") == name and near(pad.get("at"), (x, y))]
        if len(matching) != 1 or matching[0].get("layer") != "F.Cu":
            raise ValueError(f"Marble source pad {name} changed; review recipe")
        pads.append(matching[0])
    tracks = []
    for start, end in SEGMENTS:
        matching = [track for track in original.tracks if track.get("net_name") == SIGNAL
                    and track.get("layer") == "F.Cu" and
                    ((near(track.get("start"), start) and near(track.get("end"), end)) or
                     (near(track.get("start"), end) and near(track.get("end"), start)))]
        if len(matching) != 1:
            raise ValueError("Marble +1V0 source route changed; review recipe")
        tracks.append(matching[0])
    names = [row.get("name") for row in original.stackup]
    begin, finish = names.index("F.Cu"), names.index("In1.Cu")
    stackup = original.stackup[begin:finish+1]
    if [row.get("name") for row in stackup] != ["F.Cu", "dielectric 1", "In1.Cu"]:
        raise ValueError("Marble near-surface stackup changed; review recipe")
    spacing = float(stackup[1]["thickness"])
    if not 0 < spacing < 1:
        raise ValueError("Invalid imported F.Cu to In1.Cu spacing")
    plane = {"id": "provisional-local-gnd", "net_name": RETURN, "layer": "In1.Cu",
             "source_kind": "provisional_reference_plane",
             "points": [[288.5, 97.2], [291.5, 97.2], [291.5, 99.2], [288.5, 99.2]]}
    assumptions = {
        "status": "provisional_exploratory_only",
        "source_board": str(board), "source_sha256": hashlib.sha256(board.read_bytes()).hexdigest(),
        "source_signal_net": SIGNAL,
        "source_pads": [name for name, _, _ in PORTS],
        "source_track_ids": [track.get("id") for track in tracks],
        "source_stackup_layers": [row.get("name") for row in stackup],
        "assumed_return": "3 x 2 mm local In1.Cu GND rectangle, not copied from source fill",
        "assumed_ports": "50 ohm vertical lumped ports at U4.6 and C53.1, uncalibrated",
        "excited_port": excite_port,
        "limitations": ["not the full Marble PDN", "unreviewed GND plane and port planes",
                        "stackup design values have fabrication discrepancies", "no via or drilled pad modeled"],
    }
    design = DesignIR(design_id="provisional-marble-pi-u4-c53",
                      name="Marble +1V0 local PI slice", source_format="derived",
                      source_path=str(board), layers=original.layers,
                      nets=[{"id": "power", "name": SIGNAL}, {"id": "return", "name": RETURN}],
                      tracks=tracks, pads=pads, zones=[plane], stackup=stackup,
                      metadata={"provisional_openems_model": assumptions})
    ports = [{"name": name, "start": [x, y, 0.0], "stop": [x, y, -spacing],
              "direction": "z", "impedance_ohm": 50, "excite": index == excite_port}
             for index, (name, x, y) in enumerate(PORTS, 1)]
    spec = AnalysisSpec(mode="pi", solver_id="external.openems", net_names=[SIGNAL, RETURN],
                        frequency_start_hz=1e8, frequency_stop_hz=1e9,
                        frequency_points=11, options={"ports": ports})
    return design, spec, assumptions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--excite-port", type=int, choices=(1, 2), default=1)
    parser.add_argument("--mesh-resolution-mm", type=float, default=.15)
    parser.add_argument("--air-padding-mm", type=float, default=5)
    parser.add_argument("--max-solver-time-s", type=int, default=300)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-prepared", action="store_true")
    args = parser.parse_args()
    board = args.board.resolve(strict=True)
    case_dir = args.case_dir.resolve()
    os.environ.setdefault("SPIKE_STATE_HOME", str((ROOT / "build" / "openems-private-state").resolve()))
    if args.run_prepared:
        result = run_openems_case(case_dir, timeout_seconds=360)
        output = case_dir.parent / (case_dir.name + "-execution.json")
        output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        print(json.dumps({"report": str(output), "status": result.get("status")}))
        return 0 if result.get("status") == "completed" else 1
    design, spec, assumptions = build_case(board, args.excite_port)
    options = {"mesh_resolution_mm": args.mesh_resolution_mm,
               "air_padding_mm": args.air_padding_mm,
               "max_timesteps": 30000, "max_solver_time_s": args.max_solver_time_s}
    validation = _validate_openems_case(design, spec, options)
    report = {"contract": "spike/provisional-openems-board-slice/v1",
              "assumptions": assumptions, "preflight": validation, "case_dir": str(case_dir)}
    if validation["can_prepare"]:
        prepared = prepare_openems_case(design, spec, case_dir, options)
        report["prepared"] = prepared["status"]
        report["execution"] = run_openems_case(case_dir, setup_only=not args.run, timeout_seconds=360)
    output = case_dir.parent / (case_dir.name + "-report.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"report": str(output), "can_run": validation["can_run"],
                      "errors": validation["errors"], "run_blockers": validation["run_blockers"],
                      "execution_status": report.get("execution", {}).get("status")}, indent=2))
    return 0 if (validation["can_run"] and report.get("execution", {}).get("status") in
                 {"completed", "setup_completed"}) else 1


if __name__ == "__main__":
    raise SystemExit(main())
