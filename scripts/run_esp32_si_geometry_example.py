#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Run the bounded board-derived ESP32 SI geometry-channel example."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = ROOT / "examples/esp32/source/iot-esp-eth-ind.kicad_pcb"
REQUEST = ROOT / "examples/esp32/si_geometry_request.json"
EVIDENCE = ROOT / "examples/esp32/evidence"
DESIGN_OUTPUT = EVIDENCE / "si_geometry_design.json"
RESULT_OUTPUT = EVIDENCE / "si_geometry_result.json"
EVIDENCE_OUTPUT = EVIDENCE / "si_geometry_evidence.json"

SOURCE_SHA256 = "3199ce0a25f8987020e716d82a4a35d9b6b04541d33b2f2e46406376713eab33"
SIGNAL_NET = "/network/ERXD0"
REFERENCE_NET = "GND"
REFERENCE_LAYER = "In1.Cu"
REFERENCE_ZONE_ID = "80733dce-c2c6-5804-89dd-5511566386b8"
COPPER_CONDUCTIVITY_S_PER_M = 5.8e7


def _build_slice() -> dict:
    from python.spike_core.design_ir_v2 import DesignIRV2
    from python.spike_core.kicad_importer import import_kicad_design

    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("ESP32 source board changed; review the selected SI path and reference zone.")
    source = DesignIRV2.from_v1(import_kicad_design(str(SOURCE)))
    nets = {net.name: net for net in source.nets}
    signal = nets.get(SIGNAL_NET)
    reference = nets.get(REFERENCE_NET)
    if signal is None or reference is None:
        raise ValueError("The selected signal or reference net is absent from the pinned source board.")
    tracks = [track for track in source.tracks if track.net_id == signal.id]
    if (len(tracks) != 4 or any(track.width_mm != 0.254 for track in tracks)
            or any(track.layer_id != "1da98068-7c2c-5bba-b01e-eeec4ec094ce" for track in tracks)):
        raise ValueError("The selected ERXD0 path no longer has the expected four 0.254 mm F.Cu segments.")
    if any(arc.net_id == signal.id for arc in source.arcs) or any(via.net_id == signal.id for via in source.vias):
        raise ValueError("The selected ERXD0 path now includes an unsupported arc or via.")
    reference_zones = [
        zone for zone in source.zones
        if zone.id == REFERENCE_ZONE_ID and zone.net_id == reference.id
    ]
    if len(reference_zones) != 1:
        raise ValueError("The selected In1.Cu GND reference polygon is absent or no longer belongs to GND.")
    if reference_zones[0].layer_ids != ["9981ee33-dbaa-5267-9888-57221d486a65"]:
        raise ValueError("The selected GND reference polygon is no longer an In1.Cu-only polygon.")
    copper = [material for material in source.materials if material.name == "copper"]
    if len(copper) != 1:
        raise ValueError("The imported source no longer has one identifiable copper material.")
    materials = [
        replace(material, conductivity_s_per_m=COPPER_CONDUCTIVITY_S_PER_M)
        if material.id == copper[0].id else material
        for material in source.materials
    ]
    slice_design = replace(
        source,
        design_id=f"{source.design_id}-si-geometry-erxd0",
        name=f"{source.name} SI geometry slice: {SIGNAL_NET}",
        nets=[signal, reference],
        tracks=tracks,
        arcs=[],
        zones=reference_zones,
        pads=[],
        vias=[],
        drills=[],
        castellations=[],
        pins=[],
        components=[],
        component_bonds=[],
        connectors=[],
        regions=[],
        bends=[],
        models=[],
        constraints=[],
        variants=[],
        simulation_models=[],
        retained_padstack_occurrence_groups=[],
        retained_nonregular_padstack_geometry=None,
        retained_standard_contour_land_geometry=None,
        materials=materials,
        issues=[],
        metadata={
            "source_board": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
            "source_board_sha256": digest,
            "selection": {
                "signal_net": SIGNAL_NET,
                "reference_net": REFERENCE_NET,
                "reference_layer": REFERENCE_LAYER,
                "reference_zone_id": REFERENCE_ZONE_ID,
                "purpose": "bounded board-derived SI geometry channel",
            },
            "assumptions": {
                "copper_conductivity_s_per_m": COPPER_CONDUCTIVITY_S_PER_M,
                "reason": "the pinned KiCad stackup supplies copper thickness but no conductivity",
            },
        },
    )
    return slice_design.to_dict()


def main() -> int:
    if not REQUEST.is_file():
        raise FileNotFoundError(f"Missing example request: {REQUEST}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    design = _build_slice()
    DESIGN_OUTPUT.write_text(json.dumps(design, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    subprocess.run([
        sys.executable, "-m", "python.spike_core.cli", "--quiet", "--output", str(RESULT_OUTPUT),
        "si-geometry-channel", str(DESIGN_OUTPUT), str(REQUEST),
    ], cwd=ROOT, check=True)
    result = json.loads(RESULT_OUTPUT.read_text(encoding="utf-8"))
    if result.get("status") != "completed" or result.get("model_status") != "experimental":
        raise RuntimeError("The SI geometry workflow did not complete with its expected experimental status.")
    extraction = result["extraction"]
    checks = result["network"]["checks"]
    if checks["passivity"]["status"] != "pass" or checks["reciprocity"]["status"] != "pass":
        raise RuntimeError("The geometry channel failed its passive reciprocal-network checks.")
    evidence = {
        "source_board": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "source_board_sha256": SOURCE_SHA256,
        "generated_design": str(DESIGN_OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        "request": str(REQUEST.relative_to(ROOT)).replace("\\", "/"),
        "result": str(RESULT_OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        "selection": design["metadata"]["selection"],
        "assumptions": design["metadata"]["assumptions"],
        "status": result["status"],
        "model_status": result["model_status"],
        "production_qualified": result["production_qualified"],
        "compliance_status": result["compliance_status"],
        "geometry_digest": extraction["geometry_digest"],
        "geometry": extraction["geometry"],
        "rlgc_per_m": extraction["rlgc_per_m"],
        "limitations": (
            extraction["limitations"]
            + result["time_domain"]["limitations"]
            + (result["eye"] or {}).get("limitations", [])
        ),
    }
    EVIDENCE_OUTPUT.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "model_status": result["model_status"],
        "length_mm": extraction["geometry"]["length_m"] * 1e3,
        "z0_ohm": extraction["derived"]["lossless_characteristic_impedance_ohm"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
