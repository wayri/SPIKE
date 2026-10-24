# SPDX-License-Identifier: Apache-2.0
"""Exercise unchanged coupled-path admission on pinned real SERDES board nets.

This is a prerequisite experiment, not protocol qualification. It neither drops
vias/arcs nor substitutes clock traces, and never asserts physical compliance.
Run with the source Python environment; no KiCad installation is required.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.si_channel import SiChannelError
from python.spike_core.si_coupled_channel import extract_coupled_path_rlgc
from python.spike_core.si_material_scenario import prepare_si_material_scenario
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.spider_v2_schema import content_digest
from scripts.verify_si_real_boards import BOARDS as PREVIOUS_BOARDS
from scripts.verify_wren_si_scenario import BOARD_PATH, BOARD_SHA256, COPPER_SCENARIO

BOARDS = {
    "marble": {
        "path": PREVIOUS_BOARDS["marble"]["path"],
        "sha256": PREVIOUS_BOARDS["marble"]["sha256"],
        "pairs": [f"/QSFP{connector}/QSFP_{direction}_{lane}"
                  for connector in (1, 2) for direction in ("TX", "RX")
                  for lane in (1, 2, 3, 4)],
    },
    "wren_ie_native": {
        "path": BOARD_PATH, "sha256": BOARD_SHA256,
        "pairs": ["/SFP0.TX", "/SFP0.RX"],
    },
}
HASHED_OWNERS = (
    "scripts/verify_si_board_protocol_readiness.py",
    "scripts/verify_si_real_boards.py", "scripts/verify_wren_si_scenario.py",
    "python/spike_core/si_channel.py", "python/spike_core/si_coupled_channel.py",
    "python/spike_core/si_material_scenario.py", "python/spike_core/service_project.py",
    "python/spike_core/kicad_importer.py", "python/spike_core/spider_v2.py",
)


def prepare_nominal_copper(design: dict) -> dict:
    """Apply only the explicitly labelled previous nominal copper scenario."""
    copper = [item for item in design["materials"] if item["material_class"] == "copper"]
    if not copper:
        raise ValueError("No explicit copper-class material; reclassification is forbidden")
    request = {
        "contract": "spike/si-material-scenario-request/v1",
        "design_digest_sha256": content_digest(design),
        "source_digest": design["source"]["source_digest"],
        "material_overrides": [{
            "material_id": item["id"], "material_type": "copper",
            "conductivity_s_per_m": COPPER_SCENARIO["conductivity_s_per_m"],
            "provenance": {
                "source": COPPER_SCENARIO["source"],
                "temperature_k": COPPER_SCENARIO["temperature_k"],
                "model": "Explicit constant nominal bulk copper; not measured PCB foil",
                "assumption_status": "assumed",
            },
        } for item in copper],
    }
    return prepare_si_material_scenario(design, request)


def net_inventory(design: SpiDeRV2, name: str) -> dict:
    matches = [net for net in design.nets if net.name == name]
    if len(matches) != 1:
        raise ValueError(f"Exact SERDES net {name!r} resolved to {len(matches)} records")
    net = matches[0]
    components = {component.id: component for component in design.components}
    layers = {layer.id: layer.name for layer in design.layers}
    tracks = [track for track in design.tracks if track.net_id == net.id]
    return {
        "name": name, "id": net.id,
        "track_count": len(tracks),
        "arc_count": sum(arc.net_id == net.id for arc in design.arcs),
        "via_count": sum(via.net_id == net.id for via in design.vias),
        "track_layers": sorted({layers[track.layer_id] for track in tracks}),
        "track_widths_mm": sorted({track.width_mm for track in tracks}),
        "assigned_pads": sorted([{
            "pad_id": pad.id, "pad_number": pad.name,
            "component": components[pad.component_id].reference,
            "component_value": components[pad.component_id].value,
            "footprint": components[pad.component_id].footprint,
        } for pad in design.pads if pad.net_id == net.id],
            key=lambda pad: (pad["component"], pad["pad_number"])),
        "connectivity_claim": "source_net_assignment_only_not_native_ratsnest_closure",
    }


def attempt_pair(design: SpiDeRV2, pair: str) -> dict:
    """Call the real extractor, preserving its first physical admission failure."""
    inventory = [net_inventory(design, pair + suffix) for suffix in ("_P", "_N")]
    request = {
        "contract": "spike/si-uniform-channel-request/v1",
        "channel_id": pair, "signal_net": pair + "_P", "victim_net": pair + "_N",
        "signaling": "differential", "path_mode": "strict_uniform",
        "reference_net": "GND", "reference_layer": "In1.Cu",
    }
    result = {"pair": pair, "nets": inventory, "request": request,
              "extractor_called": True, "production_qualified": False,
              "compliance_status": "not_evaluated", "path_modes": {}}
    for mode in ("strict_uniform", "piecewise_planar"):
        selected = {**request, "path_mode": mode}
        if mode == "piecewise_planar":
            # Explicit zero tolerances: an exact matched-segment prerequisite,
            # not fitted tolerances chosen to make a real board pass.
            selected.update(coupled_separation_tolerance_mm=0.0,
                            coupled_skew_tolerance_mm=0.0)
        try:
            extraction = extract_coupled_path_rlgc(design, selected)
        except SiChannelError as error:
            row = {"status": "rejected", "reason": str(error)}
        else:
            row = {"status": "admitted", "extraction": extraction}
        result["path_modes"][mode] = {**row, "request": selected}
    result["channel_admission"] = result["path_modes"]["piecewise_planar"]
    return result


def evaluate_board(name: str) -> dict:
    from python.spike_core.service_project import import_design

    spec = BOARDS[name]
    path = ROOT / spec["path"]
    identity = sha256(path.read_bytes()).hexdigest()
    if identity != spec["sha256"]:
        raise ValueError(f"{name}: pinned source identity mismatch")
    imported = import_design(str(path.resolve()), with_report=True)
    original = imported["design"]
    if original["source"]["source_digest"] != identity:
        raise ValueError(f"{name}: importer source identity mismatch")
    prepared = prepare_nominal_copper(original)
    design = SpiDeRV2.from_dict(prepared["design"])
    pairs = [attempt_pair(design, pair) for pair in spec["pairs"]]
    if sha256(path.read_bytes()).hexdigest() != identity:
        raise ValueError(f"{name}: source changed during evaluation")
    return {
        "source_path": spec["path"], "source_sha256": identity,
        "import_status": imported["report"]["status"],
        "counts": {key: len(original[key]) for key in ("tracks", "arcs", "vias", "pads", "nets")},
        "material_scenario": prepared["provenance"], "pairs": pairs,
        "all_pair_extractions_admitted": all(
            pair["channel_admission"]["status"] == "admitted" for pair in pairs),
        "production_qualified": False, "compliance_status": "not_evaluated",
    }


def build_evidence() -> dict:
    hashes = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in HASHED_OWNERS}
    boards = {name: evaluate_board(name) for name in BOARDS}
    if hashes != {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in HASHED_OWNERS}:
        raise ValueError("An inspected implementation source changed during evaluation")
    return {
        "contract": "spike/si-board-protocol-readiness-evidence/v1", "boards": boards,
        "source_sha256": hashes, "production_qualified": False,
        "protocol_pass_claimed": False, "compliance_status": "not_evaluated",
        "scope": "Real differential-net strict/piecewise geometry admission only; no broadband or Tx/Rx solve",
        "remaining_gates": [
            "Exact operating mode, firmware, module/cable and standards revision are unbound",
            "Complete package/via/connector/switch/return-path broadband channel is unavailable",
            "Board-specific frequency-dependent materials and independent correlation are unavailable",
            "Qualified Tx/Rx/CDR/jitter/BER and normative fixture comparisons are unavailable",
        ],
    }


def write_evidence(path: Path, result: dict) -> None:
    encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("A fresh output file is required")
    result = build_evidence()
    write_evidence(args.output, result)
    print(json.dumps({name: {pair["pair"]: pair["channel_admission"]["status"]
                            for pair in row["pairs"]}
                      for name, row in result["boards"].items()}))
    # A successful inventory/extraction is not a qualification success.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
