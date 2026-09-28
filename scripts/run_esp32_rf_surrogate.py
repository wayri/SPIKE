#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build and optionally solve a disclosed two-conductor ESP32 RF surrogate.

The imported four-copper-layer KiCad board remains the source of geometry.
Internal copper is replaced by dielectric in this *separate* RF approximation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from extensions.emerge_suite.board_adapter import compile_board  # noqa: E402
from python.spike_core.extension_analysis_results import design_binding  # noqa: E402
from python.spike_core.extensions import ExtensionRegistry  # noqa: E402
from python.spike_core.kicad_importer import import_kicad_design  # noqa: E402

SOURCE = ROOT / "examples/esp32/source/iot-esp-eth-ind.kicad_pcb"
OUTPUT = ROOT / "examples/esp32/evidence"
SOURCE_SHA256 = "3199ce0a25f8987020e716d82a4a35d9b6b04541d33b2f2e46406376713eab33"
RADIATOR_GRAPHICS = {
    "817c03f8-f9e8-4029-897c-528a2659f8a0",
    "b3e2ed36-ac4c-4dfe-8147-1d61b463a2a2",
}
SHORT_VIA = "9959768f-ffca-4046-a521-ffad7c2dfe13"
SIGNAL_PAD = "b5ad6d18-4cc2-4549-b974-4a0148c79d01"
RETURN_PAD = "surrogate-bcu-return-at-feed"


def _inside(point: tuple[float, float], polygon: list[list[float]]) -> bool:
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


def build_surrogate() -> tuple[dict, dict, dict]:
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("ESP32 source board changed; inspect antenna graphics, short and stackup before rebuilding.")
    source = json.loads(json.dumps(import_kicad_design(str(SOURCE)).to_dict(), allow_nan=False))
    stack = [layer for layer in source["stackup"] if layer.get("type") in {"copper", "prepreg", "core", "dielectric"}]
    if [layer["name"] for layer in stack if layer["type"] == "copper"] != ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]:
        raise ValueError("The source copper order changed; review the reduction.")
    # Series-capacitance equivalent for the dielectric slabs. Each removed
    # internal copper sheet is replaced by dielectric between its neighbours.
    media = []
    for index, layer in enumerate(stack[1:-1], 1):
        thickness = float(layer["thickness"])
        if layer["type"] == "copper":
            epsilon = (float(stack[index - 1]["epsilon_r"]) + float(stack[index + 1]["epsilon_r"])) / 2
        else:
            epsilon = float(layer["epsilon_r"])
        media.append((thickness, epsilon))
    thickness = sum(item[0] for item in media)
    epsilon_effective = thickness / sum(t / epsilon for t, epsilon in media)
    graphics = [zone for zone in source["zones"] if zone["id"] in RADIATOR_GRAPHICS]
    if {zone["id"] for zone in graphics} != RADIATOR_GRAPHICS or any(zone.get("source_kind") != "graphic_polygon" or zone.get("net_name") for zone in graphics):
        raise ValueError("Expected unnetted source antenna copper graphics were not found.")
    for zone in graphics:
        zone.update(net_name="/cpu/ANT", source_original_net_name="",
                    source_kind="attributed_graphic_polygon",
                    attribution_reason="KiCad F.Cu radiator graphic touching the /cpu/ANT feed in the pinned board")
    ground_zones = [zone for zone in source["zones"] if zone.get("net_name") == "GND"
                    and zone.get("layer") == "B.Cu" and zone.get("source_kind") == "filled_zone"]
    signal_pads = [pad for pad in source["pads"] if pad.get("net_name") == "/cpu/ANT" and "F.Cu" in pad.get("layers", [])]
    signal = next((pad for pad in signal_pads if pad["id"] == SIGNAL_PAD), None)
    if signal is None:
        raise ValueError("The pinned antenna feed pad was not found.")
    feed_xy = tuple(signal["at"])
    if not any(_inside(feed_xy, zone["points"]) for zone in ground_zones):
        raise ValueError("No source-filled B.Cu GND copper exists below the surrogate port.")
    plane_bounds = [min(point[0] for zone in ground_zones for point in zone["points"]),
                    min(point[1] for zone in ground_zones for point in zone["points"]),
                    max(point[0] for zone in ground_zones for point in zone["points"]),
                    max(point[1] for zone in ground_zones for point in zone["points"])]
    left, top, right, bottom = plane_bounds
    reference_plane = {"id": "surrogate-bcu-reference-plane", "net_name": "GND", "layer": "B.Cu",
                       "source_kind": "idealized_reference_plane", "attribution_reason":
                       "Rectangle bounded by pinned source-filled B.Cu GND extents; source voids omitted",
                       "points": [[left, top], [right, top], [right, bottom], [left, bottom]]}
    for pad in signal_pads:
        pad["layers"] = ["F.Cu"]
        pad["layer"] = "F.Cu"
    return_pad = {"id": RETURN_PAD, "net_name": "GND", "layer": "B.Cu", "layers": ["B.Cu"],
                  "shape": "rect", "at": list(feed_xy), "size": [0.5, 0.5], "rotation": 0}
    vias = [via for via in source["vias"] if via.get("id") == SHORT_VIA]
    if len(vias) != 1 or vias[0].get("net_name") != "GND" or tuple(vias[0]["at"]) != (78.232, 123.317):
        raise ValueError("The pinned source ground shorting via was not found.")
    design = {"contract": "spike/v1", "units": "mm", "design_id": source["design_id"] + "-rf-two-conductor",
              "stackup": [dict(stack[0]), {"name": "equivalent dielectric", "type": "core", "thickness": thickness,
                                            "epsilon_r": epsilon_effective, "loss_tangent": 0.02}, dict(stack[-1])],
              "tracks": [track for track in source["tracks"] if track.get("net_name") == "/cpu/ANT" and track.get("layer") == "F.Cu"],
              "pads": signal_pads + [return_pad], "zones": graphics + [reference_plane],
              "vias": vias, "metadata": {"board_bounds_mm": source["metadata"]["board_bounds_mm"],
                                         "source_sha256": digest, "surrogate": True}}
    parameters = {"signal_net": "/cpu/ANT", "return_net": "GND", "signal_pad_id": SIGNAL_PAD,
                  "return_pad_id": RETURN_PAD, "shorting_via_ids": [SHORT_VIA],
                  "fragment_copper": False,
                  "frequency_start_hz": 2.3e9, "frequency_stop_hz": 2.6e9,
                  "frequency_points": 3, "mesh_resolution_mm": 1.5}
    assumptions = {"source_board_sha256": digest, "conductors": ["F.Cu antenna and feed", "idealized B.Cu GND reference bounded by source fill"],
                   "removed_copper": ["In1.Cu", "In2.Cu"], "dielectric_thickness_mm": thickness,
                   "effective_epsilon_r": epsilon_effective, "effective_epsilon_method": "series-capacitance slab reduction; internal copper thickness replaced with adjacent dielectric average",
                   "attributed_antenna_graphics": sorted(RADIATOR_GRAPHICS),
                   "reference_plane_bounds_mm": plane_bounds,
                   "return_port": "0.5 mm synthetic B.Cu pad marker inside source-filled GND at the antenna feed; vertical 50 ohm lumped port",
                   "short": "one pinned source GND via represented as a solid PEC cylinder",
                   "omissions": "Source GND plane voids, other nets, matching components, shield, extra ground vias, internal copper, solder mask, copper loss, dielectric loss and nonrectangular board outline",
                   "qualification": "illustrative surrogate; not a validated radiation prediction"}
    return design, parameters, assumptions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="Run the EMerge radiation extension after preflight")
    parser.add_argument("--python-executable", type=Path)
    parser.add_argument("--mesh-resolution-mm", type=float, default=1.5)
    parser.add_argument("--output-prefix", default="rf_surrogate")
    args = parser.parse_args()
    if not args.output_prefix.isidentifier():
        raise ValueError("Output prefix must be a simple identifier.")
    design, parameters, assumptions = build_surrogate()
    parameters["mesh_resolution_mm"] = args.mesh_resolution_mm
    case = compile_board(design, parameters)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / f"{args.output_prefix}_design.json").write_text(json.dumps(design, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / f"{args.output_prefix}_case.json").write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / f"{args.output_prefix}_assumptions.json").write_text(json.dumps(assumptions, indent=2) + "\n", encoding="utf-8")
    print(f"Preflight: {len(case['polygons'])} polygons, {len(case['shorting_vias'])} short, {case['planar_cell_estimate']} planar cells")
    if not args.run:
        return
    if args.python_executable:
        parameters["python_executable"] = str(args.python_executable.resolve())
    registry = ExtensionRegistry()
    diagnostics = registry.discover([ROOT / "extensions"], trusted_roots=[ROOT / "extensions"])
    if not any(row["id"] == "spike.emerge-suite" and row["status"] == "loaded" for row in diagnostics):
        raise RuntimeError("The bundled EMerge extension was not admitted by SPIKE.")
    result = registry.invoke("spike.emerge-suite", "emerge-radiation", {"design": design, "parameters": parameters})["data"]["analysis_result"]
    (OUTPUT / f"{args.output_prefix}_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    evidence = {"status": result["status"], "model_status": result["model_status"],
                "design_binding": design_binding(design), "solver": result["provenance"]["solver"],
                "issue_codes": [issue["code"] for issue in result["issues"]],
                "parameters": parameters, "assumptions": assumptions}
    (OUTPUT / f"{args.output_prefix}_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"EMerge: {result['status']} ({result['model_status']})")


if __name__ == "__main__":
    main()
