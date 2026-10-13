# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Yawar B and SPIKE contributors.
"""Original straight two-wire geometry -> four-port network reference.

Run from checkout: .venv/Scripts/python.exe examples/harness/run_multiconductor_reference.py
No board/CAD, measured fan data or externally copied fixture is involved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy
import scipy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from python.spike_core.harness_mtl import run_harness_mtl
from python.spike_core.harness_rlgc_geometry import extract_parallel_round_rlgc


def requests():
    geometry = {"contract": "spike/harness-round-wire-rlgc/v1", "reference_plane": {"kind": "ideal_infinite_ground_plane"},
                "wires": [{"wire_id": w, "x_m": x, "height_m": .01, "radius_m": .0002,
                           "conductivity_s_m": 5.8e7, "relative_permeability": 1, "role": "signal", "occurrence_id": "assembly/harness"}
                          for w, x in (("positive", -.005), ("negative", .005))],
                "dielectric": {"relative_permittivity": 2.25, "loss_tangent": .01},
                "frequency_hz": [0, 1e6, 10e6], "provenance": {"source": "Original synthetic round-wire harness; assumed constant material values"}}
    derived = extract_parallel_round_rlgc(geometry)
    if derived["status"] != "completed":
        raise ValueError(derived["issues"])
    nodes = [{"id": end+wire, "wire_id": wire, "occurrence_id": "board-"+end}
             for end in ("a", "b") for wire in ("positive", "negative")]
    ports = [{"id": node["id"], "positive_node": node["id"], "negative_node": "ideal-reference",
              "reference_impedance_ohm": 50, "occurrence_id": node["occurrence_id"], "wire_id": node["wire_id"]}
             for node in nodes]
    network = {"contract": "spike/harness-mtl-request/v1", "reference_node": "ideal-reference", "nodes": nodes,
               "frequency_hz": geometry["frequency_hz"], "segments": [{"id": "straight-cable", "wire_ids": ["positive", "negative"],
                "from_nodes": ["apositive", "anegative"], "to_nodes": ["bpositive", "bnegative"], "length_m": 1,
                "model": derived["model"]}], "ports": ports, "contacts": [], "terminations": [],
               "mixed_mode_pairs": [["apositive", "anegative"], ["bpositive", "bnegative"]],
               "provenance": {"source": "Original geometry-derived synthetic harness", "geometry_request_digest": derived["request_digest"]}}
    return geometry, derived, network


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    geometry, derived, network = requests()
    result = run_harness_mtl(network)
    artifacts = {"geometry-request.json": geometry, "geometry-result.json": derived,
                 "network-request.json": network, "network-result.json": result}
    hashes = {}
    for name, value in artifacts.items():
        encoded = json.dumps(value, allow_nan=False, indent=2)+"\n"
        hashes[name] = hashlib.sha256(encoded.encode()).hexdigest()
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            destination = args.output_dir / name
            if destination.exists():
                raise ValueError("Use a fresh evidence directory; refusing to overwrite " + str(destination))
            destination.write_text(encoded, encoding="utf-8", newline="\n")
    source_paths = ["python/spike_core/harness_mtl.py", "python/spike_core/harness_rlgc_geometry.py",
                    "python/spike_core/sparameters.py", "examples/harness/run_multiconductor_reference.py",
                    "schemas/harness-mtl-request-v1.schema.json", "schemas/harness-round-wire-rlgc-request-v1.schema.json"]
    evidence = {"status": result["status"], "model_status": derived["model_status"], "artifact_sha256": hashes,
                "source_sha256": {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_paths},
                "runtime": {"python": platform.python_version(), "platform": platform.platform(),
                            "numpy": numpy.__version__, "scipy": scipy.__version__},
                "quality": result["quality"], "production_qualified": False}
    if args.output_dir:
        evidence_path = args.output_dir / "evidence.json"
        if evidence_path.exists():
            raise ValueError("Refusing to overwrite evidence manifest")
        evidence_path.write_text(json.dumps(evidence, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
