# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Reimport pinned real boards and attempt explicit, unmodified SI admission.

Not a new channel extraction model. Unsupported geometry remains a failed
numerical admission rather than a fabricated substitute or compliance pass.
"""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BOARDS = {
    "marble": {
        "path": "build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb",
        "sha256": "3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512",
        "signal_net": "/WhiteRabbit/SI570_CLK_N", "reference_net": "GND", "reference_layer": "In1.Cu",
        "conversion_losslessness_verified": None,
    },
    "white_rabbit": {
        "path": "build/white-rabbit-qualification-20260920/core-converted-bounded/board.kicad_pcb",
        "sha256": "6ae6d75d44c89200ec358ad9f43403ff6b8bea4a3580758f160588fa91502aff",
        "signal_net": "SYNC_DATA_P", "reference_net": "GND", "reference_layer": "In1.Cu",
        "conversion_losslessness_verified": False,
    },
}


def evaluate(name, spec, *, copper_scenario=None, reference_zone_id=None):
    from python.spike_core.service_project import import_design
    from python.spike_core.spider_v2 import SpiDeRV2
    from python.spike_core.solvers.signal_integrity.channels.si_channel import extract_uniform_path_rlgc, uniform_rlgc_network, SiChannelError
    path = ROOT / spec["path"]
    identity = sha256(path.read_bytes()).hexdigest()
    if identity != spec["sha256"]:
        raise ValueError(f"{name}: pinned source identity mismatch")
    imported = import_design(str(path.resolve()), with_report=True)
    design = imported["design"]
    if design["source"]["source_digest"] != identity:
        raise ValueError(f"{name}: importer lost source identity")
    row = {"source": spec["path"], "sha256": identity,
           "conversion_losslessness_verified": spec["conversion_losslessness_verified"],
           "import_status": imported["report"]["status"],
           "counts": {key: len(design[key]) for key in ("tracks", "arcs", "pads", "vias", "zones", "nets")},
           "import_solver_readiness": imported["report"]["solver_readiness"]}
    if copper_scenario is not None:
        from python.spike_core.solvers.signal_integrity.channels.si_material_scenario import prepare_si_material_scenario
        from python.spike_core.spider_v2_schema import content_digest
        copper = [item for item in design["materials"] if item["material_class"] == "copper"]
        scenario_request = {
            "contract": "spike/si-material-scenario-request/v1", "design_digest_sha256": content_digest(design),
            "source_digest": identity,
            "material_overrides": [{"material_id": item["id"], "material_type": "copper",
                "conductivity_s_per_m": copper_scenario["conductivity_s_per_m"],
                "provenance": {"source": copper_scenario["source"], "temperature_k": copper_scenario["temperature_k"],
                    "model": "Explicit constant nominal bulk copper conductivity; not measured PCB foil",
                    "assumption_status": "assumed"}} for item in copper],
        }
        if not copper:
            row["material_scenario"] = {"status": "rejected",
                "reason": "No retained material has explicit class 'copper'; no material name or geometry is reclassified."}
        else:
            prepared = prepare_si_material_scenario(design, scenario_request)
            row["material_scenario"] = prepared["provenance"]
            design = prepared["design"]
    request = {"contract": "spike/si-uniform-channel-request/v1", "channel_id": name + "-si-admission",
               **{key: spec[key] for key in ("signal_net", "reference_net", "reference_layer")},
               "reference_impedance_ohm": 50, "frequencies_hz": [i * 1e6 for i in range(65)]}
    if reference_zone_id is not None:
        request["reference_zone_id"] = reference_zone_id
    row["request"] = request
    reference_net_ids = {item["id"] for item in design["nets"] if item["name"] == spec["reference_net"]}
    reference_layer_ids = {item["id"] for item in design["layers"] if item["name"] == spec["reference_layer"]}
    row["reference_zone_candidates"] = [
        {"id": zone["id"], "source_id": zone["source_id"], "outline_count": len(zone["outlines_mm"]),
         "hole_count": len(zone["holes_mm"]), "boundary_ring_count": len(zone.get("boundary_rings", []))}
        for zone in design["zones"] if zone["net_id"] in reference_net_ids
        and reference_layer_ids.intersection(zone["layer_ids"])]
    row["path_modes"] = {}
    for mode in ("strict_uniform", "piecewise_planar"):
        selected = {**request, "path_mode": mode}
        try:
            extraction = extract_uniform_path_rlgc(SpiDeRV2.from_dict(design), selected)
            network = uniform_rlgc_network(extraction, selected["frequencies_hz"], 50)
        except SiChannelError as error:
            row["path_modes"][mode] = {"status": "rejected", "reason": str(error)}
        else:
            import numpy as np
            matrices = network.s_parameters()
            singular = np.linalg.svd(matrices, compute_uv=False)
            reciprocity = float(np.max(np.abs(matrices - matrices.transpose(0, 2, 1))))
            maximum_gain = float(np.max(singular))
            geometry, physical = extraction["geometry"], extraction["rlgc_per_m"]
            tracks = {item["id"]: item for item in design["tracks"]}
            length_m = sum(math.dist(tracks[key]["start_mm"], tracks[key]["end_mm"]) for key in geometry["track_ids"]) * .001
            expected_r = length_m / (physical["conductivity_s_per_m"] * geometry["width_m"] * geometry["thickness_m"])
            expected_dc_s21 = 100 / (100 + expected_r)
            dc_error = float(abs(matrices[0, 1, 0] - expected_dc_s21))
            if maximum_gain > 1 + 1e-10 or reciprocity > 1e-10 or dc_error > 1e-12:
                raise RuntimeError(f"{name}: independent passive/reciprocal/DC network checks failed")
            row["path_modes"][mode] = {"status": "admitted", "extraction": extraction,
                                      "network_frequency_count": len(network.frequencies_hz),
                                      "network_port_count": network.port_count,
                                      "network_checks": {"maximum_sampled_singular_value": maximum_gain,
                                          "reciprocity_max_abs": reciprocity, "dc_s21_absolute_error": dc_error,
                                          "independent_dc_trace_resistance_ohm": expected_r},
                                      "network_sha256_complex128_le": sha256(matrices.astype("<c16").tobytes()).hexdigest()}
    row["channel_admission"] = row["path_modes"]["piecewise_planar"]
    row["production_qualified"] = False
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--copper-conductivity-s-per-m", type=float,
                        help="Explicit nominal scenario for retained copper-class materials only; no default")
    parser.add_argument("--conductivity-source", help="Required provenance locator for supplied conductivity")
    parser.add_argument("--temperature-k", type=float, help="Required Kelvin temperature for the supplied value")
    parser.add_argument("--reference-zone", action="append", default=[], metavar="BOARD=CANONICAL_ID")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("A fresh output file is required")
    copper_scenario = None
    if args.copper_conductivity_s_per_m is not None:
        if not args.conductivity_source or args.temperature_k is None:
            parser.error("Explicit conductivity requires --conductivity-source and --temperature-k")
        copper_scenario = {"conductivity_s_per_m": args.copper_conductivity_s_per_m,
                           "source": args.conductivity_source, "temperature_k": args.temperature_k}
    elif args.conductivity_source or args.temperature_k is not None:
        parser.error("Provenance must accompany an explicit conductivity")
    selected_zones = {}
    for pair in args.reference_zone:
        board, separator, zone_id = pair.partition("=")
        if not separator or board not in BOARDS or not zone_id or board in selected_zones:
            parser.error("Each --reference-zone must identify one known board and exact nonempty ID")
        selected_zones[board] = zone_id
    rows = {name: evaluate(name, spec, copper_scenario=copper_scenario,
                          reference_zone_id=selected_zones.get(name)) for name, spec in BOARDS.items()}
    result = {"contract": "spike/si-real-board-admission-evidence/v1", "boards": rows,
              "all_channel_admissions_passed": all(row["channel_admission"]["status"] == "admitted"
                  and row.get("material_scenario", {}).get("status") != "rejected" for row in rows.values()),
              "production_qualified": False, "generation_specific_qualification": "not_evaluated",
              "assumptions": ["Explicit named diagnostic paths, not board nominal operating modes.",
                              "50 ohm and DC-64 MHz are diagnostic inputs, not standard limits.",
                              "No missing stackup, return geometry, device model or measurement is invented.",
                              "Any material scenario is explicitly supplied and is not source-board or measurement evidence."],
              "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in (
                  "scripts/verify_si_real_boards.py", "python/spike_core/solvers/signal_integrity/channels/si_channel.py",
                  "python/spike_core/solvers/signal_integrity/channels/si_material_scenario.py", "python/spike_core/service_project.py",
                  "python/spike_core/spider_v2.py")}}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"boards": {name: row["channel_admission"]["status"] for name, row in rows.items()},
                      "all_channel_admissions_passed": result["all_channel_admissions_passed"]}))
    return 0 if result["all_channel_admissions_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
