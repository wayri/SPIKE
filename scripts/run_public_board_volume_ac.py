# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded Marble C383-net finite-volume AC probe on routed copper."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.contracts import DesignIR  # noqa: E402
from python.spike_core.service import _design_from_kicad, handle  # noqa: E402


def run(
    board: Path,
    mesh_size_mm: float,
    inferred_ports: bool = False,
    original_disconnected_ports: bool = False,
) -> dict:
    design = _design_from_kicad(str(board))
    net = "Net-(C383-Pad1)"
    copper = {
        field: [item for item in getattr(design, field)
                if str(item.get("net_name", item.get("net", ""))) == net]
        for field in ("tracks", "vias", "pads", "zones")
    }
    pads = {str(item.get("component_pad")): item for item in copper["pads"]}
    # C383.1 has the selected net assignment but is an unrouted B.Cu island in
    # Marble v1.4.4.  R195.1 is the opposite pad endpoint that is physically
    # connected to U37.18 through the retained track/via/zone topology.
    source = pads["U37.18"]
    load_name = "C383.1" if original_disconnected_ports else "R195.1"
    load = pads[load_name]
    slice_design = DesignIR(
        design_id="marble-v1.4.4-C383-volume-ac", name="Marble C383 volume AC probe",
        source_format="kicad", source_path="Marble-v1.4.4/design/Marble.kicad_pcb",
        layers=design.layers, nets=[item for item in design.nets if item.get("name") == net],
        stackup=design.stackup, **copper,
    )
    spec = {
        "mode": "ac", "solver_id": "spike.peec_2_5d", "net_names": [net],
        "mesh": {"target_size_mm": mesh_size_mm, "zone_cell_mm": mesh_size_mm,
                 "max_zone_cells": 1000, "max_conductors": 2000,
                 "memory_budget_mb": 512},
        "frequency_start_hz": 1000.0, "frequency_stop_hz": 1000000.0,
        "frequency_points": 5,
        "options": {"peec_volume_extraction": "enabled"},
        "sources": [] if inferred_ports else [{"id": "U37.18",
            "position_mm": source["at"], "layer": source.get("layer", "F.Cu"),
            "net": net, "geometry_anchor": {"id": source["id"], "type": "pad"},
            "voltage_v": 1.0}],
        "loads": [] if inferred_ports else [{"id": load_name,
            "position_mm": load["at"], "layer": load.get("layer", "F.Cu"),
            "net": net, "geometry_anchor": {"id": load["id"], "type": "pad"},
            "current_a": 0.1}],
    }
    response = handle({"id": "marble-volume-ac", "method": "run_preflighted_analysis",
                       "params": {"design": slice_design.to_dict(), "spec": spec}})
    result = response.get("result") or {}
    analysis = result.get("analysis_result") or {}
    return {
        "contract": "spike/public-board-volume-ac-probe/v1",
        "board_sha256": hashlib.sha256(board.read_bytes()).hexdigest(),
        "native_sha256": _native_hash(),
        "mesh_size_mm": mesh_size_mm,
        "assumption": (
            "C383-named net, inferred connected endpoints"
            if inferred_ports else
            "C383-named net, original physically disconnected U37.18/C383.1 pad endpoints"
            if original_disconnected_ports else
            "C383-named net, routed U37.18/R195.1 pad endpoints, 1V/0.1A sensitivity"
        ),
        "terminals": ({"source": "inferred", "load": "inferred"}
                      if inferred_ports else {"source": "U37.18", "load": load_name}),
        "geometry_counts": {key: len(items) for key, items in copper.items()},
        "worker_ok": response.get("ok"),
        "preflight_can_solve": (result.get("preflight") or {}).get("can_solve"),
        "status": analysis.get("status"),
        "model_status": analysis.get("model_status"),
        "issues": [{key: issue.get(key) for key in ("code", "severity", "message")}
                   for issue in analysis.get("issues", [])][:16],
        "summary": {key: analysis.get("summary", {}).get(key) for key in
                    ("partial_inductance_h", "resistance_start_ohm", "geometry_counts")},
        "volume_quality": ((analysis.get("provenance") or {}).get("numerical_quality") or {}).get(
            "volume_extraction"),
        "zone_basis_support": (analysis.get("provenance") or {}).get("zone_basis_support"),
        "inductance_passivity": ((analysis.get("provenance") or {}).get("numerical_quality") or {}).get(
            "inductance_passivity"),
        "worker_error": response.get("error"),
    }


def _native_hash() -> str | None:
    from python.spike_core.peec_plugin import native
    return hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest() if native else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument("--mesh-size-mm", type=float, default=1.0)
    parser.add_argument("--inferred-ports", action="store_true")
    parser.add_argument(
        "--original-disconnected-ports", action="store_true",
        help="Reproduce the physically disconnected U37.18-to-C383.1 terminal selection.",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = run(
        args.board, args.mesh_size_mm, args.inferred_ports,
        args.original_disconnected_ports,
    )
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, allow_nan=False))
