# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Execute reproducible internal generation, adaptation and smoothing examples."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SOURCE_FILES = (
    "python/spike_core/solvers/geometry_meshing/preparation/internal_tetra_generation.py",
    "python/spike_core/solvers/geometry_meshing/preparation/dynamic_tetra_adaptation.py",
    "python/spike_core/solvers/geometry_meshing/preparation/internal_meshing_engine.py",
    "python/spike_core/service_meshing.py",
    "python/spike_core/solvers/geometry_meshing/preparation/tetra_mesh_refinement.py",
    "python/spike_core/solvers/geometry_meshing/preparation/tetra_mesh_optimization.py",
    "python/spike_core/service.py",
    "schemas/internal-mesh-request-v1.schema.json",
    "examples/internal_meshing/run_examples.py",
    "examples/internal_meshing/noncuboidal.json",
)

from python.spike_core.solvers.geometry_meshing.preparation.internal_meshing_engine import run_internal_meshing
from python.spike_core.service_meshing import handle_meshing_request
from python.spike_core.solvers.geometry_meshing.preparation.tetra_mesh_refinement import _det


def _envelope(operation, parameters):
    return {"contract": "spike/internal-mesh-request/v1", "operation": operation,
            "parameters": parameters}


def _integral(mesh, field):
    return sum(_det(mesh["vertices"], cell["vertices"])/6*value
               for cell, value in zip(mesh["cells"], field))


def _source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def run_case_corpus():
    request = json.loads((Path(__file__).parent / "noncuboidal.json").read_text(encoding="utf-8"))
    raw = {**request, "parameters": {**request["parameters"], "optimize": False}}
    raw["parameters"].pop("iterations")
    generated = run_internal_meshing(raw)
    automatic = run_internal_meshing(request)
    cube = run_internal_meshing(_envelope("generate", {
        "points": [list(p) for p in itertools.product((0, 1), repeat=3)], "optimize": False}))
    source = automatic["candidate"]
    mesh = source["mesh"]
    common = {"mesh": mesh, "boundary_triangles": source["boundary_triangles"], "optimize": False}
    affine = [2 + p[0] - 3*p[1] + .5*p[2] for p in mesh["vertices"]]
    manual = run_internal_meshing(_envelope("adapt", {**common,
        "manual_edges": [mesh["cells"][0]["vertices"][:2]],
        "nodal_fields": {"potential": affine}, "cell_fields": {"density": [7.] * len(mesh["cells"])}}))
    indicator = run_internal_meshing(_envelope("adapt", {**common, "cell_indicators": {
        cell["id"]: float(i+1) for i, cell in enumerate(mesh["cells"])}, "marking_fraction": .5}))
    sized = run_internal_meshing(_envelope("adapt", {**common, "target_edge_length": 1.0}))
    protected = run_internal_meshing(_envelope("optimize", {"mesh": generated["candidate"]["mesh"],
        "boundary_triangles": generated["candidate"]["boundary_triangles"], "protected_vertices": [4]}))
    probe = handle_meshing_request("internal_mesh_capabilities", {})
    if not probe["ok"] or probe["result"]["external_mesher_required"]:
        raise RuntimeError("Internal capability probe failed.")
    cases = {"noncuboidal_generation": generated, "automatic_quality": automatic,
             "cospherical_cube": cube, "manual_field_transfer": manual,
             "error_indicator": indicator, "edge_sizing": sized, "protected_vertex": protected}
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New output directory; existing artifacts are not overwritten.")
    args = parser.parse_args()
    sources = _source_hashes()
    # One warm-up and five measured complete-corpus runs.
    run_case_corpus()
    durations = []
    for _ in range(5):
        start = time.perf_counter()
        cases = run_case_corpus()
        durations.append(time.perf_counter()-start)
    report = {"contract": "spike/internal-mesh-example-evidence/v1",
              "machine": {"python": sys.version.split()[0], "platform": platform.platform(),
                          "compiler": platform.python_compiler(), "architecture": platform.machine()},
              "source_sha256": sources, "runtime_dependencies": "Python standard library only",
              "warmups": 1, "measured_runs": 5, "median_seconds": statistics.median(durations),
              "measured_seconds": durations, "cases": {}}
    for name, result in cases.items():
        candidate = result["candidate"]
        report["cases"][name] = {"counts": candidate["mesh"]["counts"],
                                  "candidate_sha256": result["candidate_sha256"],
                                  "quality": candidate["quality"]}
    before = cases["noncuboidal_generation"]["candidate"]["quality"]["minimum_mean_ratio"]
    after = cases["automatic_quality"]["candidate"]["quality"]["after"]["minimum_mean_ratio"]
    if not after > before:
        raise RuntimeError("Quality fixture did not improve.")
    original = cases["automatic_quality"]["candidate"]["mesh"]
    transferred = cases["manual_field_transfer"]["candidate"]
    error = max(abs(value - (2 + p[0] - 3*p[1] + .5*p[2]))
                for p, value in zip(transferred["mesh"]["vertices"], transferred["nodal_fields"]["potential"]))
    old_integral = _integral(original, [7.] * len(original["cells"]))
    new_integral = _integral(transferred["mesh"], transferred["cell_fields"]["density"])
    if error > 1e-13 or not math.isclose(old_integral, new_integral, rel_tol=1e-12):
        raise RuntimeError("Analytical scalar transfer fixture failed.")
    report["affine_transfer_max_error"] = error
    report["density_integral_absolute_error"] = abs(old_integral-new_integral)
    report["quality_improvement_factor"] = after/before
    report["production_qualified"] = False
    if _source_hashes() != sources:
        raise RuntimeError("Meshing source changed during qualification; evidence is rejected.")
    if args.output:
        destination = args.output.resolve()
        destination.mkdir(parents=True, exist_ok=False)
        for name, result in cases.items():
            (destination / (name + ".json")).write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        (destination / "evidence.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(destination.glob("*.json"))}
        (destination / "sha256.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
