#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Run the bounded ESP32 ERXD0/ERXD1 NEXT/FEXT geometry example."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE = ROOT / "examples/esp32/source/iot-esp-eth-ind.kicad_pcb"
EXAMPLE = ROOT / "examples/esp32"
EVIDENCE = EXAMPLE / "evidence"
DESIGN_OUTPUT = EVIDENCE / "si_crosstalk_design.json"
REQUEST_OUTPUT = EXAMPLE / "si_crosstalk_request.json"
RESULT_OUTPUT = EVIDENCE / "si_crosstalk_result.json"
EVIDENCE_OUTPUT = EVIDENCE / "si_crosstalk_evidence.json"
SOURCE_SHA256 = "3199ce0a25f8987020e716d82a4a35d9b6b04541d33b2f2e46406376713eab33"
AGGRESSOR = "/network/ERXD0"
VICTIM = "/network/ERXD1"
REFERENCE = "GND"
REFERENCE_LAYER = "In1.Cu"
REFERENCE_ZONE_ID = "80733dce-c2c6-5804-89dd-5511566386b8"


def build_slice() -> dict:
    from python.spike_core.design_ir_v2 import DesignIRV2
    from python.spike_core.kicad_importer import import_kicad_design

    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("ESP32 source board changed; re-review the selected coupled routes.")
    source = DesignIRV2.from_v1(import_kicad_design(str(SOURCE)))
    nets = {net.name: net for net in source.nets}
    selected = [nets[name] for name in (AGGRESSOR, VICTIM, REFERENCE)]
    route_ids = {nets[AGGRESSOR].id, nets[VICTIM].id}
    route_tracks = [track for track in source.tracks if track.net_id in route_ids]
    if len(route_tracks) != 8 or any(track.width_mm != 0.254 for track in route_tracks):
        raise ValueError("The pinned ERXD0/ERXD1 selection no longer has eight 0.254 mm segments.")
    if any(arc.net_id in route_ids for arc in source.arcs) or any(via.net_id in route_ids for via in source.vias):
        raise ValueError("The selected coupled routes now contain an unsupported arc or via.")
    # The complete routes bend away from each other. Retain only their exact
    # parallel overlap, clipped to the shorter source segment, so the solver's
    # coextensive-pair admission is explicit rather than inferred.
    horizontal = [track for track in route_tracks if abs(track.start_mm[1] - track.end_mm[1]) < 1e-12
        and min(track.start_mm[0], track.end_mm[0]) == 65.659]
    if len(horizontal) != 2:
        raise ValueError("The pinned parallel ERXD0/ERXD1 trace pair changed.")
    overlap_end_x = min(max(track.start_mm[0], track.end_mm[0]) for track in horizontal)
    tracks = [replace(track, id=f"{track.id}-overlap", start_mm=(65.659, track.start_mm[1]),
        end_mm=(overlap_end_x, track.start_mm[1])) for track in horizontal]
    zones = [zone for zone in source.zones if zone.id == REFERENCE_ZONE_ID and zone.net_id == nets[REFERENCE].id]
    if len(zones) != 1:
        raise ValueError("The pinned In1.Cu GND reference zone is absent.")
    copper = next(material for material in source.materials if material.name == "copper")
    materials = [replace(material, conductivity_s_per_m=5.8e7) if material.id == copper.id else material for material in source.materials]
    return replace(source, design_id=f"{source.design_id}-si-crosstalk-erxd",
        name=f"{source.name} SI crosstalk slice: ERXD0/ERXD1", nets=selected,
        tracks=tracks, arcs=[], zones=zones, pads=[], vias=[], drills=[], castellations=[], pins=[],
        components=[], component_bonds=[], connectors=[], regions=[], bends=[], models=[], constraints=[],
        variants=[], simulation_models=[], retained_padstack_occurrence_groups=[],
        retained_nonregular_padstack_geometry=None, retained_standard_contour_land_geometry=None,
        materials=materials, issues=[], metadata={"source_board": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "source_board_sha256": digest, "selection": {"aggressor_net": AGGRESSOR, "victim_net": VICTIM,
        "reference_net": REFERENCE, "reference_layer": REFERENCE_LAYER, "reference_zone_id": REFERENCE_ZONE_ID},
        "assumptions": {"copper_conductivity_s_per_m": 5.8e7,
        "coupled_geometry": "only the exact 0.7874 mm coextensive parallel overlap is retained; bends and remaining routes are excluded",
        "clipped_overlap_x_mm": [65.659, overlap_end_x]}}).to_dict()


def request() -> dict:
    waveform = [0.0] * 16 + [3.3] * 128 + [0.0] * 112
    return {"contract": "spike/si-uniform-channel-request/v1", "channel_id": "esp32-erxd0-erxd1-crosstalk",
        "signal_net": AGGRESSOR, "victim_net": VICTIM, "reference_net": REFERENCE,
        "reference_layer": REFERENCE_LAYER, "path_mode": "piecewise_planar", "reference_impedance_ohm": 50.0,
        "frequencies_hz": [index * 7_812_500.0 for index in range(257)], "cross_section_vertical_cells": 24,
        "coupled_separation_tolerance_mm": 0.30, "coupled_skew_tolerance_mm": 0.15, "trace_limit": 257,
        "crosstalk_model": {"port_map": {"aggressor_near": 0, "victim_near": 1,
        "aggressor_far": 2, "victim_far": 3}, "termination_ohm": [50.0, 50.0, 50.0, 50.0],
        "waveform_v": waveform, "trace_limit": 257}}


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    design, model = build_slice(), request()
    DESIGN_OUTPUT.write_text(json.dumps(design, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    REQUEST_OUTPUT.write_text(json.dumps(model, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "python.spike_core.cli", "--quiet", "--output", str(RESULT_OUTPUT),
        "si-geometry-channel", str(DESIGN_OUTPUT), str(REQUEST_OUTPUT)], cwd=ROOT, check=True)
    result = json.loads(RESULT_OUTPUT.read_text(encoding="utf-8"))
    loaded = result["crosstalk"]["loaded"]
    if result.get("status") != "completed" or loaded["time_domain"]["status"] != "completed":
        raise RuntimeError("ESP32 crosstalk example did not complete its frequency and transient stages.")
    evidence = {"source_board": design["metadata"]["source_board"], "source_board_sha256": SOURCE_SHA256,
        "generated_design": str(DESIGN_OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        "request": str(REQUEST_OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        "result": str(RESULT_OUTPUT.relative_to(ROOT)).replace("\\", "/"), "selection": design["metadata"]["selection"],
        "status": result["status"], "model_status": result["model_status"], "production_qualified": False,
        "compliance_status": "not_evaluated", "geometry": result["extraction"]["geometry"],
        "peak_abs_next_v": loaded["time_domain"]["peak_abs_next_v"],
        "peak_abs_fext_v": loaded["time_domain"]["peak_abs_fext_v"],
        "worst_matched_next_db": result["crosstalk"]["next"]["worst_transfer_db"],
        "worst_matched_fext_db": result["crosstalk"]["fext"]["worst_transfer_db"],
        "limitations": result["extraction"]["limitations"] + loaded["limitations"]}
    EVIDENCE_OUTPUT.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: evidence[key] for key in ("status", "model_status", "peak_abs_next_v", "peak_abs_fext_v",
        "worst_matched_next_db", "worst_matched_fext_db")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
