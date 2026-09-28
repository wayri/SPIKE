# SPDX-License-Identifier: Apache-2.0
"""Exercise the available volume PEEC backend on bounded source-board slices.

The saved results are exploratory: source copper is local, returns and ports
are provisional, and the PEEC capacitance model is approximate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python import spike_peec_native
from python.spike_core.contracts import AnalysisSpec
from python.spike_core.peec_plugin import solve_peec_2_5d


SOURCES = {
    "hforsten": ROOT / "build/pi-ten-board-evaluation-20260924/corpus/hforsten-vna2/hw/vna2.kicad_pcb",
    "marble": ROOT / "build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", choices=tuple(SOURCES))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/validation/internal-comparison")
    args = parser.parse_args()
    source = SOURCES[args.board].resolve(strict=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.board == "hforsten":
        from scripts.run_openems_provisional_hforsten import build_case
    else:
        from scripts.run_openems_provisional_marble_pi import build_case
    design, _, assumptions = build_case(source)
    if args.board == "hforsten":
        pads = {pad["component_pad"]: pad for pad in design.pads}
        signal, reference = "/filter_bank/RF_IN", "GND"
        terminal = lambda name, field: {"id": name, "position_mm": pads[name]["at"],
                                        "layer": pads[name]["layer"], "net": signal, field: 1.0}
        sources = [terminal("C5.1", "voltage_v")]
        loads = [terminal("U13.8", "current_a")]
        band = (1e9, 3e9)
        max_zone_cells, max_conductors = 1000, 2000
    else:
        pads = {pad["component_pad"]: pad for pad in design.pads}
        signal, reference = "+1V0", "GND"
        def terminal(name: str, field: str, role: str) -> dict:
            return {"id": name, "position_mm": pads[name]["at"], "layer": "F.Cu",
                    "net": signal, "terminal_role": role, "pair_id": "loop", field: 1.0}
        sources = [terminal("U4.6", "voltage_v", "source_positive")]
        loads = [terminal("C53.1", "current_a", "load_positive")]
        band = (1e8, 1e9)
        max_zone_cells, max_conductors = 5000, 12000
    spec = AnalysisSpec(
        mode="ac", solver_id="spike.peec_2_5d", net_names=[signal],
        sources=sources, loads=loads,
        return_path={"mode": "explicit", "net": reference},
        frequency_start_hz=band[0], frequency_stop_hz=band[1], frequency_points=11,
        mesh={"target_size_mm": 0.2, "zone_cell_mm": 0.2,
              "max_zone_cells": max_zone_cells, "max_conductors": max_conductors,
              "memory_budget_mb": 512},
        options={"peec_volume_extraction": "enabled"},
    )
    result = solve_peec_2_5d(design, spec).to_dict()
    native_path = Path(spike_peec_native.__file__).resolve(strict=True)
    record = {
        "contract": "spike/provisional-volume-peec-run/v1",
        "board": args.board, "source_board": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "native_module": str(native_path),
        "native_module_sha256": hashlib.sha256(native_path.read_bytes()).hexdigest(),
        "assumptions": assumptions,
        "terminal_scope": "one signal-net source-to-load driving-point extraction; not a 50-ohm two-port S matrix",
        "result": result,
    }
    output = args.output_dir / f"{args.board}-volume-peec.json"
    output.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": result["status"],
                      "model_status": result["model_status"],
                      "issues": [item["code"] for item in result["issues"]],
                      "networks": list(result["networks"])}))


if __name__ == "__main__":
    main()
