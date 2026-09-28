# SPDX-License-Identifier: Apache-2.0
"""Run an explicitly provisional HForsten RF_IN board slice through openEMS.

The selected signal geometry comes from KiCad. The local return plane, FR-4
stackup, and lumped port are modeling assumptions, not fabrication evidence.
This is an integration experiment and must not be used as board validation.
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

from extensions.openems_suite.engine import prepare_openems_case, run_openems_case, _validate_openems_case
from python.spike_core.cli import load_design
from python.spike_core.contracts import AnalysisSpec, DesignIR


SIGNAL = "/filter_bank/RF_IN"
RETURN = "GND"
PORT_XY = (174.27, 44.09)  # Source pad C5.1, checked below.


def build_case(board: Path, start_hz: float = 1e9, stop_hz: float = 3e9,
               two_port: bool = False, excite_port: int = 1) -> tuple[DesignIR, AnalysisSpec, dict]:
    original = DesignIR(**load_design(board))
    signal_tracks = [item for item in original.tracks if item.get("net_name") == SIGNAL]
    signal_pads = [item for item in original.pads if item.get("net_name") == SIGNAL]
    if len(signal_tracks) != 3 or len(signal_pads) != 2:
        raise ValueError("RF_IN source geometry changed; review this provisional recipe")
    contact = [item for item in signal_pads if item.get("component_pad") == "C5.1"]
    if len(contact) != 1 or any(abs(float(a)-b) > 1e-5 for a, b in zip(contact[0]["at"], PORT_XY)):
        raise ValueError("C5.1 port pad moved; review the port definition")
    receiver = [item for item in signal_pads if item.get("component_pad") == "U13.8"]
    if len(receiver) != 1 or any(abs(float(a)-b) > 1e-5 for a, b in zip(receiver[0]["at"], (172.399, 44.646))):
        raise ValueError("U13.8 port pad moved; review the port definition")
    if excite_port not in (1, 2) or (excite_port == 2 and not two_port):
        raise ValueError("Excited port must be one of the modeled ports")
    # A local 5 x 4 mm plane is assumed on In1.Cu. It is not copied from the
    # large, detailed source-filled GND plane; its size and edges are arbitrary.
    x, y = PORT_XY
    plane = {"id": "provisional-local-return", "net_name": RETURN,
             "layer": "In1.Cu", "source_kind": "provisional_reference_plane",
             "points": [[x-2.5, y-2], [x+2.5, y-2], [x+2.5, y+2], [x-2.5, y+2]]}
    # The source declares a nominal 1.6 mm four-copper board, without its
    # dielectric table. These numbers are deliberately explicit assumptions.
    stackup = [
        {"name": "F.Cu", "type": "copper", "thickness": .035},
        {"name": "dielectric 1", "type": "prepreg", "thickness": .2, "epsilon_r": 4.3, "loss_tangent": .02},
        {"name": "In1.Cu", "type": "copper", "thickness": .018},
        {"name": "dielectric 2", "type": "core", "thickness": 1.2, "epsilon_r": 4.3, "loss_tangent": .02},
        {"name": "In2.Cu", "type": "copper", "thickness": .018},
        {"name": "dielectric 3", "type": "prepreg", "thickness": .2, "epsilon_r": 4.3, "loss_tangent": .02},
        {"name": "B.Cu", "type": "copper", "thickness": .035},
    ]
    assumptions = {
        "status": "provisional_exploratory_only",
        "source_board": str(board),
        "source_sha256": hashlib.sha256(board.read_bytes()).hexdigest(),
        "source_signal_net": SIGNAL,
        "source_signal_tracks": len(signal_tracks),
        "source_signal_pads": len(signal_pads),
        "assumed_return": "5 x 4 mm local In1.Cu GND rectangle",
        "assumed_stackup": "1.6 mm dielectric total, Dk 4.3, Df 0.02, 35/18/18/35 um Cu",
        "assumed_port": "50 ohm vertical lumped port at C5.1 to local In1.Cu GND; uncalibrated",
        "limitations": ["not a full-board geometry", "no measured port plane or de-embedding",
                        "no fabricated dielectric or copper certificate", "no accuracy comparison to SPIKE"],
    }
    if two_port:
        assumptions["assumed_port_2"] = "50 ohm vertical lumped port at U13.8 to local In1.Cu GND; uncalibrated"
        assumptions["excited_port"] = excite_port
    design = DesignIR(design_id="provisional-hforsten-rf-in", name="HForsten RF_IN exploratory slice",
                      source_format="derived", source_path=str(board),
                      layers=original.layers, nets=[{"id": "signal", "name": SIGNAL}, {"id": "return", "name": RETURN}],
                      tracks=signal_tracks, pads=signal_pads, zones=[plane], stackup=stackup,
                      metadata={"provisional_openems_model": assumptions})
    ports = [{"name": "C5.1 assumed launch", "start": [x, y, 0.0],
              "stop": [x, y, -.2], "direction": "z",
              "impedance_ohm": 50, "excite": excite_port == 1}]
    if two_port:
        rx, ry = 172.399, 44.646
        ports.append({"name": "U13.8 assumed receive plane", "start": [rx, ry, 0.0],
                      "stop": [rx, ry, -.2], "direction": "z",
                      "impedance_ohm": 50, "excite": excite_port == 2})
    spec = AnalysisSpec(mode="si", solver_id="external.openems", net_names=[SIGNAL, RETURN],
                        frequency_start_hz=start_hz, frequency_stop_hz=stop_hz, frequency_points=11,
                        options={"ports": ports})
    return design, spec, assumptions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--run", action="store_true", help="execute FDTD after successful preflight")
    parser.add_argument("--run-prepared", action="store_true", help="execute an authenticated case prepared by this recipe")
    parser.add_argument("--mesh-mm", type=float, default=.2)
    parser.add_argument("--max-timesteps", type=int, default=30000)
    parser.add_argument("--solver-time-s", type=int, default=300)
    parser.add_argument("--start-hz", type=float, default=1e9)
    parser.add_argument("--stop-hz", type=float, default=3e9)
    parser.add_argument("--two-port", action="store_true", help="include a second assumed 50 ohm port at U13.8")
    parser.add_argument("--excite-port", type=int, default=1, choices=(1, 2))
    args = parser.parse_args()
    board = args.board.resolve(strict=True)
    case_dir = args.case_dir.resolve()
    os.environ.setdefault("SPIKE_STATE_HOME", str((ROOT / "build" / "openems-private-state").resolve()))
    if args.run_prepared:
        result = run_openems_case(case_dir, timeout_seconds=960)
        output = case_dir.parent / (case_dir.name + "-execution.json")
        output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        print(json.dumps({"report": str(output), "execution_status": result.get("status")}, indent=2))
        return 0 if result.get("status") == "completed" else 1
    design, spec, assumptions = build_case(board, args.start_hz, args.stop_hz,
                                           args.two_port, args.excite_port)
    options = {"mesh_resolution_mm": args.mesh_mm, "air_padding_mm": 5,
               "max_timesteps": args.max_timesteps, "max_solver_time_s": args.solver_time_s}
    validation = _validate_openems_case(design, spec, options)
    report = {"contract": "spike/provisional-openems-board-slice/v1",
              "assumptions": assumptions, "preflight": validation, "case_dir": str(case_dir)}
    if validation["can_prepare"]:
        case = prepare_openems_case(design, spec, case_dir, options)
        report["prepared"] = case["status"]
        report["execution"] = run_openems_case(case_dir, setup_only=not args.run,
                                                 timeout_seconds=960)
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
